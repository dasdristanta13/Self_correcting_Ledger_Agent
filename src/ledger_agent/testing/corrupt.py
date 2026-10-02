from decimal import Decimal
from typing import Callable

from ledger_agent.extraction.ledger import build_ledger
from ledger_agent.models import Discrepancy, Document, Ledger
from ledger_agent.paths import set_field


def corrupting_builder(path: str, value: Decimal, also: tuple[str, Decimal] | None = None
                       ) -> Callable[[Document], Ledger]:
    def build(doc: Document) -> Ledger:
        led = set_field(build_ledger(doc), path, value)
        return set_field(led, also[0], also[1]) if also else led
    return build


def scripted_validator(script: list[list[Discrepancy]]):
    calls = {"n": 0}

    def validator(ledger, rules):
        out = script[min(calls["n"], len(script) - 1)]
        calls["n"] += 1
        return out
    return validator
