import logging
import time

import chromadb
import pytest
from chromadb.config import Settings
from fastapi.testclient import TestClient

from ledger_agent.api.main import build_app, build_app_from_env
from ledger_agent.retrieval.chroma_vector import list_index_collections
from ledger_agent.storage.base import Job
from ledger_agent.storage.chroma_store import ChromaJobStore
from ledger_agent.testing.invoices import default_spec, render_invoice


def _client(path):
    return chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))


def test_second_build_on_a_held_dir_raises_and_touches_nothing(tmp_path):
    data = tmp_path / "data"
    with TestClient(build_app(data)) as c1:
        client = _client(data / "chroma")
        ChromaJobStore(client).create(Job(job_id="live", filename="l.pdf", state="RUNNING",
                                          created_at="2026-01-01T00:00:00.000+00:00"))
        client.create_collection("idx-0123456789abcdef", embedding_function=None)
        stale = data / "uploads" / "inflight.pdf"
        stale.write_bytes(b"%PDF-1.4")
        with pytest.raises(RuntimeError, match="another ledger-agent process is using"):
            build_app(data)
        assert ChromaJobStore(client).get("live").state == "RUNNING"       # not marked interrupted
        assert list_index_collections(client) == ["idx-0123456789abcdef"]  # not swept
        assert stale.exists()                                              # uploads not swept
        assert c1.get("/api/health").status_code == 200


def test_lock_is_released_when_the_first_app_shuts_down(tmp_path):
    data = tmp_path / "data"
    with TestClient(build_app(data)):
        pass
    with TestClient(build_app(data)) as c:
        assert c.get("/api/health").json()["status"] == "ok"


def test_lock_can_be_disabled_and_a_failed_build_releases_it(tmp_path, monkeypatch):
    data = tmp_path / "data"
    a = build_app(data)
    b = build_app(data, lock=False)                  # opt-out for tests that deliberately build twice
    assert a is not b
    from ledger_agent.api import main as m

    other = tmp_path / "other"
    with monkeypatch.context() as mp:
        mp.setattr(m, "ChromaJobStore", lambda *_: (_ for _ in ()).throw(ValueError("boom")))
        with pytest.raises(ValueError):
            build_app(other)
    build_app(other)                                 # lock was released by the failed attempt


def test_data_dir_gets_a_gitignore_star(tmp_path):
    build_app(tmp_path / "data")
    assert (tmp_path / "data" / ".gitignore").read_text().strip() == "*"
    (tmp_path / "data" / ".gitignore").write_text("custom\n")
    build_app(tmp_path / "data", lock=False)
    assert (tmp_path / "data" / ".gitignore").read_text() == "custom\n"      # idempotent, never overwritten


def test_missing_frontend_dist_logs_a_warning(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        build_app(tmp_path / "data", frontend_dist=tmp_path / "nope")
    assert any("UI not served" in r.getMessage() for r in caplog.records)


def test_from_env_configures_json_trace_logging(tmp_path, monkeypatch):
    trace = logging.getLogger("ledger_agent.trace")
    saved = (trace.handlers[:], trace.level, trace.propagate)
    monkeypatch.setenv("LEDGER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LEDGER_LOG_LEVEL", "INFO")
    lines = []

    class Capture(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())

    try:
        app = build_app_from_env()
        assert trace.handlers and trace.propagate is False and trace.level == logging.INFO
        trace.addHandler(Capture())
        pdf = render_invoice(default_spec(), tmp_path / "L.pdf")
        with TestClient(app) as c:
            resp = c.post("/api/invoices", files={"file": ("L.pdf", pdf.read_bytes(), "application/pdf")})
            jid = resp.json()["job_id"]
            for _ in range(300):
                if c.get(f"/api/invoices/{jid}").json()["state"] in ("DONE", "ERROR"):
                    break
                time.sleep(0.1)
        assert any('"node": "ingest"' in line for line in lines)
    finally:
        trace.handlers[:] = saved[0]
        trace.setLevel(saved[1])
        trace.propagate = saved[2]
