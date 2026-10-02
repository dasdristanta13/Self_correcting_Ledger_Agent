import chromadb
from job_store_contract import JobStoreContract, make_job

from ledger_agent.storage.chroma_store import ChromaJobStore


class TestChromaStoreContract(JobStoreContract):
    def make_store(self):
        # EphemeralClient shares one in-process system: give every store its own collections
        # by clearing them first so contract tests are isolated.
        client = chromadb.EphemeralClient()
        for name in ("jobs", "events"):
            try:
                client.delete_collection(name)
            except Exception:
                pass
        return ChromaJobStore(client)


def test_jobs_survive_a_new_client_on_the_same_directory(tmp_path):
    first = ChromaJobStore.persistent(tmp_path / "chroma")
    first.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
    first.append_events("a", [{"node": "ingest"}])
    first.update("a", state="DONE", result={"status": "RECONCILED"})
    del first
    try:  # force a genuinely new client/system rather than the cached shared one
        from chromadb.api.shared_system_client import SharedSystemClient
        SharedSystemClient.clear_system_cache()
    except Exception:
        pass
    second = ChromaJobStore.persistent(tmp_path / "chroma")
    got = second.get("a")
    assert got.state == "DONE" and got.result == {"status": "RECONCILED"}
    assert second.get_events("a") == [{"node": "ingest"}]


def test_chroma_store_is_thread_safe_for_concurrent_appends(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    store = ChromaJobStore.persistent(tmp_path / "chroma")
    store.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: store.append_events("a", [{"n": i}]), range(20)))
    assert sorted(e["n"] for e in store.get_events("a")) == list(range(20))


def test_two_store_instances_on_one_client_lose_no_events():
    from concurrent.futures import ThreadPoolExecutor

    client = chromadb.EphemeralClient()
    for name in ("jobs", "events"):
        try:
            client.delete_collection(name)
        except Exception:
            pass
    stores = [ChromaJobStore(client), ChromaJobStore(client)]
    stores[0].create(make_job("a", "2026-01-01T00:00:00.000+00:00"))

    def run(tag):
        for n in range(15):
            stores[tag].append_events("a", [{"tag": tag, "n": n}])

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(run, [0, 1]))
    events = stores[1].get_events("a")
    assert len(events) == 30
    for tag in (0, 1):
        assert [e["n"] for e in events if e["tag"] == tag] == list(range(15))
