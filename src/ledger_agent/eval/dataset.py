from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal as D

from ledger_agent.testing.invoices import InvoiceSpec, ItemSpec, default_spec


@dataclass(frozen=True)
class Case:
    name: str
    kind: str                                   # clean | extraction_error | document_error
    spec: InvoiceSpec
    corrupt: tuple[str, D] | None = None        # ledger corrupted AFTER extraction (extraction error)
    also: tuple[str, D] | None = None


def _s(name: str, **kw) -> InvoiceSpec:
    spec = default_spec(f"EV-{name}")
    for k, v in kw.items():
        setattr(spec, k, v)
    return spec


def default_cases() -> list[Case]:
    dup = [ItemSpec("Gasket", D("3"), D("10.00")) for _ in range(3)]
    doc_line = default_spec("EV-document_line_amount")
    doc_line.items[0].printed_amount = D("1040.00")
    return [
        Case("clean", "clean", _s("clean")),
        Case("line_amount", "extraction_error", _s("line_amount"), ("items[line_01].amount", D("1040.00"))),
        Case("decimal_error", "extraction_error", _s("decimal_error"), ("items[line_01].amount", D("10140.00"))),
        Case("quantity_error", "extraction_error", _s("quantity_error"), ("items[line_01].quantity", D("13"))),
        Case("unit_price_error", "extraction_error", _s("unit_price_error"), ("items[line_01].unit_price", D("845.00"))),
        Case("subtotal", "extraction_error", _s("subtotal"), ("subtotal", D("1050.00"))),
        Case("tax", "extraction_error", _s("tax"), ("tax_lines[tax_01].amount", D("100.00"))),
        Case("total", "extraction_error", _s("total"), ("total", D("1200.00"))),
        Case("duplicate_lines", "extraction_error", _s("duplicate_lines", items=dup), ("items[line_02].amount", D("99.00"))),
        Case("multi_tax", "extraction_error", _s("multi_tax", tax_rates=(D("0.05"), D("0.07"))),
             ("tax_lines[tax_02].amount", D("70.00"))),
        Case("discount", "extraction_error", _s("discount", discount=D("44.00")), ("total", D("1144.00"))),
        Case("shipping", "extraction_error", _s("shipping", shipping=D("15.00")), ("shipping", D("25.00"))),
        Case("two_errors", "extraction_error", _s("two_errors"), ("items[line_01].amount", D("1040.00")),
             also=("total", D("1200.00"))),
        Case("document_line_amount", "document_error", doc_line),
        Case("document_total", "document_error", _s("document_total", printed_total=D("1200.00"))),
        Case("document_subtotal", "document_error", _s("document_subtotal", printed_subtotal=D("1050.00"))),
    ]
