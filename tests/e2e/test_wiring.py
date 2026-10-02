from fastapi.testclient import TestClient

from ledger_agent.api.main import build_app


def test_build_app_reports_chroma_store(tmp_path):
    c = TestClient(build_app(tmp_path / "data"))
    assert c.get("/api/health").json() == {"status": "ok", "store": "chroma"}
    assert (tmp_path / "data" / "chroma").is_dir()


def test_uploads_dir_is_under_data_dir(tmp_path):
    build_app(tmp_path / "data")
    assert (tmp_path / "data" / "uploads").is_dir()


def test_build_app_from_env_reads_environment(tmp_path, monkeypatch):
    from ledger_agent.api.main import build_app_from_env

    monkeypatch.setenv("LEDGER_DATA_DIR", str(tmp_path / "envdata"))
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    c = TestClient(build_app_from_env())
    assert c.get("/api/health").json()["store"] == "chroma"
    assert (tmp_path / "envdata" / "chroma").is_dir()


def test_deps_factory_makes_fresh_deps_with_job_bound_sink(tmp_path):
    from ledger_agent.api import main as m

    seen = []
    real = m.create_app

    def spy(store, deps_factory, **kw):
        seen.append(deps_factory)
        return real(store, deps_factory, **kw)

    m.create_app = spy
    try:
        m.build_app(tmp_path / "data")
    finally:
        m.create_app = real
    a, b = seen[0]("job-a"), seen[0]("job-b")
    assert a is not b and a.trace_sink is not b.trace_sink
    assert a.vector_factory is b.vector_factory          # one shared Chroma client
