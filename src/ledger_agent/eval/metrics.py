from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ledger_agent.models import Ledger


def flatten(ledger: Ledger) -> dict[str, Decimal]:
    flat: dict[str, Decimal] = {}
    for it in ledger.items:
        for attr in ("quantity", "unit_price", "amount"):
            flat[f"items[{it.id}].{attr}"] = getattr(it, attr)
    for t in ledger.tax_lines:
        flat[f"tax_lines[{t.id}].amount"] = t.amount
    for name in ("subtotal", "discount", "tax", "shipping", "fees", "total"):
        value = getattr(ledger, name)
        if value is not None:
            flat[name] = value
    return flat


@dataclass
class Outcome:
    case: str
    kind: str
    status: str
    original: Ledger
    truth: Ledger
    final: Ledger | None
    corrections: int
    iterations: int
    latency_ms: float


def _correct(o: Outcome) -> bool:
    return o.final is not None and flatten(o.final) == flatten(o.truth)


def _false_correction(o: Outcome) -> bool:
    if o.final is None:
        return False
    orig, truth, final = flatten(o.original), flatten(o.truth), flatten(o.final)
    return any(final.get(k) != orig.get(k) and final.get(k) != truth.get(k) for k in set(final) | set(orig))


def variant_metrics(outcomes: list[Outcome]) -> dict:
    n = len(outcomes)
    rate = lambda pred: sum(1 for o in outcomes if pred(o)) / n if n else 0.0     # noqa: E731
    return {
        "n": n,
        "correct_rate": rate(_correct),
        "false_correction_rate": rate(_false_correction),
        "reconciled_rate": rate(lambda o: o.status == "RECONCILED"),
        "unresolved_rate": rate(lambda o: o.status in ("UNRESOLVED", "INSUFFICIENT_EVIDENCE", "NO_PROGRESS")),
        "mean_iterations": sum(o.iterations for o in outcomes) / n if n else 0.0,
        "max_iterations": max((o.iterations for o in outcomes), default=0),
        "mean_latency_ms": sum(o.latency_ms for o in outcomes) / n if n else 0.0,
    }
