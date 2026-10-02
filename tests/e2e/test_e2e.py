import gc
import threading
import time
from decimal import Decimal as D

import chromadb
from fastapi.testclient import TestClient

from ledger_agent.api.main import build_app
from ledger_agent.extraction.ledger import build_ledger
from ledger_agent.retrieval.chroma_vector import list_index_collections
from ledger_agent.storage.base import Job
from ledger_agent.storage.chroma_store import ChromaJobStore
from ledger_agent.testing.corrupt import corrupting_builder
from ledger_agent.testing.invoices import InvoiceSpec, ItemSpec, default_spec, render_invoice


def open_chroma(path):
    from chromadb.config import Settings
    return chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))


def wait_done(client, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        resp = client.get(f"/api/invoices/{job_id}")
        assert resp.status_code == 200, f"GET job {job_id}: {resp.status_code} {resp.text}"
        job = resp.json()
        if job["state"] in ("DONE", "ERROR"):
            return job
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def upload(client, path, name):
    resp = client.post("/api/invoices", files={"file": (name, path.read_bytes(), "application/pdf")})
    assert resp.status_code == 202, f"upload {name}: {resp.status_code} {resp.text}"
    return resp.json()["job_id"]


def test_upload_correct_trace_and_no_leftover_collections(tmp_path):
    data = tmp_path / "data"
    app = build_app(data, ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00")))
    c = TestClient(app)
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    job = wait_done(c, upload(c, pdf, "INV-001.pdf"))
    assert job["state"] == "DONE" and job["result"]["status"] == "RECONCILED"
    assert job["result"]["corrections"][0]["new_value"] == "1014.00"
    trace = c.get(f"/api/invoices/{job['job_id']}/trace").json()
    assert [e["node"] for e in trace][:4] == ["ingest", "extract", "build_index", "build_ledger"]
    assert trace[-1]["node"] == "finalize"
    client = open_chroma(data / "chroma")
    assert list_index_collections(client) == []                              # Review Focus 2


def test_failed_run_also_leaves_no_collection(tmp_path):
    data = tmp_path / "data"
    c = TestClient(build_app(data))
    spec = default_spec()
    spec.items[0].printed_amount = D("1040.00")                             # document itself wrong -> UNRESOLVED
    job = wait_done(c, upload(c, render_invoice(spec, tmp_path / "INV-002.pdf"), "INV-002.pdf"))
    assert job["result"]["status"] == "UNRESOLVED" and job["result"]["corrections"] == []
    assert list_index_collections(open_chroma(data / "chroma")) == []
    trace = c.get(f"/api/invoices/{job['job_id']}/trace").json()
    nodes = [e["node"] for e in trace]
    assert nodes[:4] == ["ingest", "extract", "build_index", "build_ledger"]
    assert "validate" in nodes and nodes[-1] == "failed" and "finalize" not in nodes


def test_jobs_survive_restart_and_interrupted_jobs_become_errors(tmp_path):  # Review Focus 4
    from chromadb.api.shared_system_client import SharedSystemClient

    data = tmp_path / "data"
    with TestClient(build_app(data)) as c1:                                  # lifespan runs; pool shut down on exit
        done_id = wait_done(c1, upload(c1, render_invoice(default_spec(), tmp_path / "A.pdf"), "A.pdf"))["job_id"]
        store = ChromaJobStore(open_chroma(data / "chroma"))
        store.create(Job(job_id="stuck", filename="stuck.pdf", state="RUNNING",
                         created_at="2026-01-01T00:00:00.000+00:00"))
    del c1, store
    gc.collect()
    SharedSystemClient.clear_system_cache()                                  # genuinely cold open
    with TestClient(build_app(data)) as c2:                                  # "restart"
        assert c2.get(f"/api/invoices/{done_id}").json()["state"] == "DONE"
        stuck = c2.get("/api/invoices/stuck").json()
        assert stuck["state"] == "ERROR" and stuck["error"] == "interrupted by restart"
        assert len(c2.get("/api/invoices").json()) >= 2


def test_orphan_collections_are_swept_at_startup(tmp_path):
    data = tmp_path / "data"
    (data / "chroma").mkdir(parents=True)
    client = open_chroma(data / "chroma")
    client.create_collection("idx-deadbeefdeadbeef", embedding_function=None)
    build_app(data)
    assert list_index_collections(client) == []


def test_concurrent_uploads_keep_invoices_apart(tmp_path):                  # Review Focus 3
    data = tmp_path / "data"
    barrier = threading.Barrier(2, timeout=30)
    lock = threading.Lock()
    arrived = []

    def overlapping_builder(doc):
        with lock:
            first_two = len(arrived) < 2
            arrived.append(doc)
        if first_two:
            barrier.wait()          # two jobs must be inside the pipeline at the same time
        return build_ledger(doc)

    c = TestClient(build_app(data, ledger_builder=overlapping_builder))
    pdfs = {}
    for name in ("ALPHA", "BRAVO", "CHARLIE"):
        spec = InvoiceSpec(name, [ItemSpec(f"{name} part", D("2"), D("5.00"))])
        pdfs[name] = render_invoice(spec, tmp_path / f"{name}.pdf")
    ids = {name: upload(c, p, f"{name}.pdf") for name, p in pdfs.items()}
    run_ids = set()
    for name, jid in ids.items():
        job = wait_done(c, jid)
        assert job["state"] == "DONE", job
        assert job["result"]["invoice_id"] == name
        assert job["result"]["ledger"]["items"][0]["description"] == f"{name} part"
        trace_run_ids = {e["run_id"] for e in c.get(f"/api/invoices/{jid}/trace").json()}
        assert len(trace_run_ids) == 1
        run_ids |= trace_run_ids
    assert len(run_ids) == 3                                                 # distinct run per job
    assert not barrier.broken
    assert list_index_collections(open_chroma(data / "chroma")) == []
