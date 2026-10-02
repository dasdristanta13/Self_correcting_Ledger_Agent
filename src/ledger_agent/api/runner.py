from __future__ import annotations

from pathlib import Path
from typing import Callable

from ledger_agent.graph import Deps, run_invoice
from ledger_agent.storage.base import JobStore, utc_now


def run_job(store: JobStore, deps_factory: Callable[[str], Deps], job_id: str,
            pdf_path: Path, invoice_id: str) -> None:
    """Run one reconciliation. Never raises: failures become job.state == 'ERROR'."""
    try:
        store.update(job_id, state="RUNNING")
        deps = deps_factory(job_id)
        result = run_invoice(str(pdf_path), deps, invoice_id=invoice_id)
        store.update(job_id, state="DONE", finished_at=utc_now(),
                     result=result.model_dump(mode="json"))
    except Exception as exc:  # service-level failure, distinct from an invoice FAILED result
        try:
            store.update(job_id, state="ERROR", finished_at=utc_now(), error=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
    finally:
        Path(pdf_path).unlink(missing_ok=True)
