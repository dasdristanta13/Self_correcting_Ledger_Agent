from typing import Literal

from ledger_agent.models import Discrepancy

Outcome = Literal["finalize", "audit", "no_progress", "max_revisions"]


def signatures(discrepancies: list[Discrepancy]) -> frozenset[tuple]:
    return frozenset((d.field, d.expected, d.observed, d.difference) for d in discrepancies)


def decide_after_validate(discrepancies: list[Discrepancy], prev_signatures,
                          revision: int, max_revisions: int) -> Outcome:
    if not discrepancies:
        return "finalize"
    if prev_signatures is not None and signatures(discrepancies) == prev_signatures:
        return "no_progress"
    if revision >= max_revisions:
        return "max_revisions"
    return "audit"
