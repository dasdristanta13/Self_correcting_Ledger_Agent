from pathlib import Path

from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.api.runner import run_job
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps
from ledger_agent.storage.base import Job
from ledger_agent.storage.memory import InMemoryJobStore
from ledger_agent.testing.invoices import default_spec, render_invoice


def deps(job_id):
    return Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer())


def new_store():
    s = InMemoryJobStore()
    s.create(Job(job_id="j1", filename="INV-001.pdf", created_at="2026-01-01T00:00:00.000+00:00"))
    return s


def test_run_job_success_stores_json_result_and_deletes_upload(tmp_path):
    store = new_store()
    pdf = render_invoice(default_spec(), tmp_path / "j1.pdf")
    run_job(store, deps, "j1", Path(pdf), "INV-001")
    job = store.get("j1")
    assert job.state == "DONE" and job.finished_at and job.error is None
    assert job.result["status"] == "RECONCILED"
    assert job.result["ledger"]["total"] == "1148.40"            # money is a string
    assert not pdf.exists()


def test_run_job_turns_crashes_into_error_state(tmp_path):
    store = new_store()
    pdf = render_invoice(default_spec(), tmp_path / "j1.pdf")

    def boom(job_id):
        raise RuntimeError("deps exploded")

    run_job(store, boom, "j1", Path(pdf), "INV-001")
    job = store.get("j1")
    assert job.state == "ERROR" and "deps exploded" in job.error and job.result is None
    assert not pdf.exists()


def test_run_job_for_unreadable_pdf_is_a_result_not_an_error(tmp_path):
    store = new_store()
    bad = tmp_path / "j1.pdf"
    bad.write_bytes(b"%PDF-1.4 not really a pdf")
    run_job(store, deps, "j1", bad, "broken")
    job = store.get("j1")
    assert job.state == "DONE" and job.result["status"] == "FAILED"
