from enum import Enum
from typing import Any, TypedDict


class Status(str, Enum):
    INGESTED = "INGESTED"
    EXTRACTED = "EXTRACTED"
    INDEXED = "INDEXED"
    VALIDATING = "VALIDATING"
    AUDITING = "AUDITING"
    RECONCILING = "RECONCILING"
    RECONCILED = "RECONCILED"
    UNRESOLVED = "UNRESOLVED"
    MAX_REVISIONS_EXCEEDED = "MAX_REVISIONS_EXCEEDED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NO_PROGRESS = "NO_PROGRESS"
    FAILED = "FAILED"


class LedgerState(TypedDict, total=False):
    pdf_path: str
    invoice_id: str
    pages: list
    document: Any
    ledger: Any
    original_ledger: Any
    retrieval_index: Any
    discrepancies: list
    last_signatures: Any
    audit_candidates: list
    audit_evidence: list
    retrieval_events: list
    proposed_corrections: list
    audit_trail: list
    revision: int
    max_revisions: int
    status: Status
    route: str
    error: str | None
