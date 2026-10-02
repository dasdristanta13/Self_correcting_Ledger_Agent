import time
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.api.app import create_app
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps
from ledger_agent.storage.memory import InMemoryJobStore
from ledger_agent.testing.corrupt import corrupting_builder
from ledger_agent.testing.invoices import default_spec, render_invoice


class Inline:
    def submit(self, fn, *a, **kw):
        fn(*a, **kw)


def plain_deps(job_id):
    return Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer())


def corrupt_deps(job_id):
    return Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer(),
                ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00")))


@pytest.fixture()
def pdf_bytes(tmp_path):
    return render_invoice(default_spec(), tmp_path / "INV-001.pdf").read_bytes()


def make_client(tmp_path, deps_factory=plain_deps, **kw):
    store = InMemoryJobStore()
    app = create_app(store, deps_factory, upload_dir=tmp_path / "up", executor=Inline(), **kw)
    return TestClient(app), store


def upload(client, data, name="INV-001.pdf"):
    return client.post("/api/invoices", files={"file": (name, data, "application/pdf")})


def test_health(tmp_path):
    c, _ = make_client(tmp_path)
    assert c.get("/api/health").json() == {"status": "ok", "store": "memory"}


def test_upload_runs_the_job_and_returns_result(tmp_path, pdf_bytes):
    c, _ = make_client(tmp_path)
    r = upload(c, pdf_bytes)
    assert r.status_code == 202 and r.json()["status"] == "QUEUED"
    job = c.get(f"/api/invoices/{r.json()['job_id']}").json()
    assert job["state"] == "DONE" and job["result"]["status"] == "RECONCILED"
    assert job["filename"] == "INV-001.pdf" and job["result"]["invoice_id"] == "INV-001"


def test_correction_is_visible_with_provenance_and_string_money(tmp_path, pdf_bytes):
    c, _ = make_client(tmp_path, corrupt_deps)
    job = c.get(f"/api/invoices/{upload(c, pdf_bytes).json()['job_id']}").json()
    res = job["result"]
    assert res["iterations"] == 1 and res["corrections"][0]["new_value"] == "1014.00"
    assert res["corrections"][0]["source_table"] == "table_01"
    assert res["original_ledger"]["items"][0]["amount"] == "1040.00"


def test_text_file_named_pdf_is_rejected_415(tmp_path):                      # Review Focus 1
    c, store = make_client(tmp_path)
    r = upload(c, b"hello, definitely not a pdf", name="evil.pdf")
    assert r.status_code == 415 and r.json()["code"] == "not_a_pdf"
    assert store.list() == []


def test_empty_upload_is_415(tmp_path):
    c, _ = make_client(tmp_path)
    assert upload(c, b"").status_code == 415


def test_oversize_upload_is_413(tmp_path, pdf_bytes):
    c, store = make_client(tmp_path, max_upload_mb=0.0001)       # ~104 bytes
    r = upload(c, pdf_bytes)
    assert r.status_code == 413 and r.json()["code"] == "too_large"
    assert store.list() == []


def test_missing_file_is_422(tmp_path):
    c, _ = make_client(tmp_path)
    r = c.post("/api/invoices")
    assert r.status_code == 422 and r.json()["code"] == "missing_file"


def test_traversal_filename_is_neutralised(tmp_path, pdf_bytes):            # Review Focus 1
    c, _ = make_client(tmp_path)
    job = c.get(f"/api/invoices/{upload(c, pdf_bytes, name='../../evil.pdf').json()['job_id']}").json()
    assert job["state"] == "DONE" and job["result"]["invoice_id"] == "evil"
    assert not (tmp_path.parent / "evil.pdf").exists()
    assert list((tmp_path / "up").iterdir()) == []                          # uploads cleaned up


def test_unknown_job_404_for_job_and_trace(tmp_path):
    c, _ = make_client(tmp_path)
    assert c.get("/api/invoices/nope").status_code == 404
    assert c.get("/api/invoices/nope/trace").json()["code"] == "not_found"


def test_list_is_newest_first(tmp_path, pdf_bytes):
    c, _ = make_client(tmp_path)
    ids = [upload(c, pdf_bytes, name=f"A{i}.pdf").json()["job_id"] for i in range(3)]
    listed = [j["job_id"] for j in c.get("/api/invoices").json()]
    assert listed == ids[::-1]
    assert len(c.get("/api/invoices?limit=2").json()) == 2


def test_trace_endpoint_returns_stored_events(tmp_path, pdf_bytes):
    c, store = make_client(tmp_path)
    jid = upload(c, pdf_bytes).json()["job_id"]
    store.append_events(jid, [{"node": "ingest", "latency_ms": 1.0}])
    assert c.get(f"/api/invoices/{jid}/trace").json() == [{"node": "ingest", "latency_ms": 1.0}]


def test_deps_factory_crash_becomes_error_job_not_500(tmp_path, pdf_bytes, caplog):
    def boom(job_id):
        raise RuntimeError("no deps")

    c, _ = make_client(tmp_path, boom)
    r = upload(c, pdf_bytes)
    assert r.status_code == 202
    job = c.get(f"/api/invoices/{r.json()['job_id']}").json()
    assert job["state"] == "ERROR" and job["error"] == "Processing failed (RuntimeError). See server logs."
    assert "no deps" not in job["error"]
    assert any(r.exc_info and "no deps" in str(r.exc_info[1]) for r in caplog.records)


def test_concurrent_uploads_do_not_mix_invoices(tmp_path, pdf_bytes):       # Review Focus 3
    store = InMemoryJobStore()
    app = create_app(store, plain_deps, upload_dir=tmp_path / "up")          # real thread pool
    c = TestClient(app)
    names = ["ALPHA.pdf", "BRAVO.pdf", "CHARLIE.pdf", "DELTA.pdf"]
    jobs = {upload(c, pdf_bytes, name=n).json()["job_id"]: n for n in names}
    deadline = time.time() + 30
    while time.time() < deadline:
        states = [c.get(f"/api/invoices/{j}").json() for j in jobs]
        if all(s["state"] in ("DONE", "ERROR") for s in states):
            break
        time.sleep(0.1)
    for j, name in jobs.items():
        data = c.get(f"/api/invoices/{j}").json()
        assert data["state"] == "DONE" and data["result"]["invoice_id"] == name[:-4]


def test_cors_allows_the_dev_origin(tmp_path):
    c, _ = make_client(tmp_path)
    r = c.options("/api/invoices", headers={"Origin": "http://localhost:5173",
                                            "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_static_frontend_is_mounted_when_dist_exists(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>UI</body></html>", encoding="utf-8")
    c, _ = make_client(tmp_path, frontend_dist=dist)
    assert "UI" in c.get("/").text
    assert c.get("/api/health").status_code == 200


class BoomExecutor:
    def submit(self, fn, *a, **kw):
        raise RuntimeError("pool is shut down")


class BoomStore(InMemoryJobStore):
    def create(self, job):
        raise RuntimeError("db down")


UNAVAILABLE = {"code": "unavailable", "message": "The service could not queue this file. Try again."}


def test_submit_failure_is_503_cleans_upload_and_leaves_no_queued_job(tmp_path, pdf_bytes):
    store = InMemoryJobStore()
    c = TestClient(create_app(store, plain_deps, upload_dir=tmp_path / "up", executor=BoomExecutor()))
    r = upload(c, pdf_bytes)
    assert r.status_code == 503 and r.json() == UNAVAILABLE
    assert list((tmp_path / "up").iterdir()) == []
    assert all(j.state == "ERROR" for j in store.list())


def test_store_create_failure_is_503_and_cleans_upload(tmp_path, pdf_bytes):
    c = TestClient(create_app(BoomStore(), plain_deps, upload_dir=tmp_path / "up", executor=Inline()))
    r = upload(c, pdf_bytes)
    assert r.status_code == 503 and r.json() == UNAVAILABLE
    assert list((tmp_path / "up").iterdir()) == []


def test_oversize_content_length_is_rejected_before_reading_body(tmp_path):
    c, store = make_client(tmp_path, max_upload_mb=0.0001)
    r = c.post("/api/invoices", content=b"x", headers={
        "content-type": "multipart/form-data; boundary=zzz", "content-length": str(5 * 1024 * 1024)})
    assert r.status_code == 413 and r.json()["code"] == "too_large"
    assert store.list() == []


def test_stale_uploads_are_swept_at_startup(tmp_path):
    up = tmp_path / "up"
    up.mkdir()
    (up / "old.pdf").write_bytes(b"%PDF-stale")
    (up / "keep.txt").write_text("x")
    create_app(InMemoryJobStore(), plain_deps, upload_dir=up, executor=Inline())
    assert sorted(p.name for p in up.iterdir()) == ["keep.txt"]


def test_malformed_request_uses_error_shape(tmp_path):
    c, _ = make_client(tmp_path)
    r = c.post("/api/invoices", content=b"{}", headers={"content-type": "multipart/form-data"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"
    r = c.get("/api/invoices?limit=abc")
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"


def test_queue_failure_is_logged(tmp_path, pdf_bytes, caplog):
    c = TestClient(create_app(InMemoryJobStore(), plain_deps, upload_dir=tmp_path / "up",
                              executor=BoomExecutor()))
    with caplog.at_level("ERROR"):
        assert upload(c, pdf_bytes).status_code == 503
    assert any(r.levelname == "ERROR" and "pool is shut down" in (r.exc_text or r.getMessage())
               or (r.exc_info and "pool is shut down" in str(r.exc_info[1])) for r in caplog.records)


def test_failure_to_mark_job_error_is_logged(tmp_path, pdf_bytes, caplog):
    class UpdateBoom(InMemoryJobStore):
        def update(self, *a, **kw):
            raise RuntimeError("update down")

    c = TestClient(create_app(UpdateBoom(), plain_deps, upload_dir=tmp_path / "up", executor=BoomExecutor()))
    with caplog.at_level("ERROR"):
        assert upload(c, pdf_bytes).status_code == 503
    assert any("could not mark job" in r.getMessage() for r in caplog.records)


def test_early_413_carries_cors_headers(tmp_path):
    c, _ = make_client(tmp_path, max_upload_mb=0.0001)
    r = c.post("/api/invoices", content=b"x", headers={
        "origin": "http://localhost:5173",
        "content-type": "multipart/form-data; boundary=zzz", "content-length": str(5 * 1024 * 1024)})
    assert r.status_code == 413
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
