from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from ledger_agent.graph import Deps, run_invoice
from ledger_agent.storage.base import JobStore, utc_now

logger = logging.getLogger(__name__)


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
        logger.exception("job %s failed", job_id)       # full detail stays in the server log only
        try:
            store.update(job_id, state="ERROR", finished_at=utc_now(),
                         error=f"Processing failed ({type(exc).__name__}). See server logs.")
        except Exception:
            logger.exception("could not mark job %s ERROR", job_id)
    finally:
        try:
            Path(pdf_path).unlink(missing_ok=True)
        except Exception:
            logger.exception("could not remove upload %s", pdf_path)
