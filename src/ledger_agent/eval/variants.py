from __future__ import annotations

from ledger_agent.config import ValidationRules
from ledger_agent.models import Ledger
from ledger_agent.paths import set_field
from ledger_agent.validation.arithmetic import validate

MODES = {"vector": "vector", "bm25": "bm25", "hybrid": "hybrid"}


def run_no_rag(ledger: Ledger, rules: ValidationRules, max_revisions: int) -> tuple[Ledger, int, str]:
    """No-RAG baseline: no retrieval, no evidence. Trusts arithmetic and rewrites the field a
    rule flagged to the value the rule expects. Stand-in for 'an LLM without retrieval'."""
    current, revisions = ledger, 0
    while revisions < max_revisions:
        found = validate(current, rules)
        if not found:
            return current, revisions, "RECONCILED"
        d = found[0]
        current = set_field(current, d.field, d.expected)
        revisions += 1
    return current, revisions, "RECONCILED" if not validate(current, rules) else "MAX_REVISIONS_EXCEEDED"
