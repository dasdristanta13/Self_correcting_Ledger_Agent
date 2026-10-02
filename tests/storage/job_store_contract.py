import pytest

from ledger_agent.storage.base import Job


def make_job(job_id, created_at, **kw):
    return Job(job_id=job_id, filename=f"{job_id}.pdf", created_at=created_at, **kw)


class JobStoreContract:
    """Subclass as Test<Store> and implement make_store(self) -> JobStore."""

    def make_store(self):
        raise NotImplementedError

    def test_create_get_roundtrip(self):
        s = self.make_store()
        s.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
        got = s.get("a")
        assert got.job_id == "a" and got.state == "QUEUED" and got.result is None

    def test_get_unknown_is_none(self):
        assert self.make_store().get("nope") is None

    def test_update_changes_fields_and_returns_job(self):
        s = self.make_store()
        s.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
        out = s.update("a", state="RUNNING")
        assert out.state == "RUNNING" and s.get("a").state == "RUNNING"

    def test_update_unknown_raises_keyerror(self):
        with pytest.raises(KeyError):
            self.make_store().update("nope", state="DONE")

    def test_result_roundtrips_nested_strings(self):
        s = self.make_store()
        s.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
        result = {"status": "RECONCILED", "ledger": {"total": "1148.40", "items": [{"amount": "1014.00"}]}}
        s.update("a", state="DONE", result=result, finished_at="2026-01-01T00:00:05.000+00:00")
        got = s.get("a")
        assert got.result == result and got.finished_at.endswith("05.000+00:00")

    def test_list_is_newest_first_and_limited(self):
        s = self.make_store()
        for i, ts in enumerate(["2026-01-01T00:00:01.000+00:00", "2026-01-01T00:00:03.000+00:00",
                                "2026-01-01T00:00:02.000+00:00"]):
            s.create(make_job(f"j{i}", ts))
        assert [j.job_id for j in s.list()] == ["j1", "j2", "j0"]
        assert [j.job_id for j in s.list(limit=2)] == ["j1", "j2"]

    def test_events_keep_append_order_and_are_per_job(self):
        s = self.make_store()
        s.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
        s.create(make_job("b", "2026-01-01T00:00:01.000+00:00"))
        s.append_events("a", [{"node": "ingest"}, {"node": "extract"}])
        s.append_events("b", [{"node": "other"}])
        s.append_events("a", [{"node": "validate"}])
        assert [e["node"] for e in s.get_events("a")] == ["ingest", "extract", "validate"]
        assert [e["node"] for e in s.get_events("b")] == ["other"]
        assert s.get_events("none") == []

    def test_mark_interrupted_only_touches_unfinished_jobs(self):
        s = self.make_store()
        s.create(make_job("q", "2026-01-01T00:00:00.000+00:00"))
        s.create(make_job("r", "2026-01-01T00:00:01.000+00:00", state="RUNNING"))
        s.create(make_job("d", "2026-01-01T00:00:02.000+00:00", state="DONE"))
        assert s.mark_interrupted() == 2
        assert s.get("q").state == "ERROR" and s.get("q").error == "interrupted by restart"
        assert s.get("r").finished_at is not None
        assert s.get("d").state == "DONE"
        assert s.mark_interrupted() == 0
