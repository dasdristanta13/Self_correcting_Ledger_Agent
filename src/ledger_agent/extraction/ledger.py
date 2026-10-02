import json
import re
from decimal import Decimal

from ledger_agent.columns import REQUIRED, column_map, inside_any_table, iter_line_item_rows
from ledger_agent.extraction.summary import summary_entries
from ledger_agent.models import Document, Ledger, LineItem, Provenance, TaxLine
from ledger_agent.money import parse_money
from ledger_agent.protocols import LLMClient
from ledger_agent.textparse import parse_labeled_line

_CCY = re.compile(r"Currency:\s*([A-Z]{3})")
_SYSTEM = "Map each invoice table header to one of: description, quantity, unit_price, amount, or null."
_SCHEMA = {"type": "object", "properties": {"mapping": {"type": "object"}}, "required": ["mapping"]}


class ExtractionError(Exception):
    pass


def resolve_column_overrides(doc: Document, llm: LLMClient | None) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    if llm is None:
        return out
    for t in doc.tables:
        if REQUIRED <= column_map(t.headers).keys() or len(t.headers) < 3:
            continue
        mapping = llm.complete_json(_SYSTEM, json.dumps({"headers": t.headers}), _SCHEMA).get("mapping", {})
        cmap: dict[str, int] = {}
        for header, canon in mapping.items():
            if canon in REQUIRED and header in t.headers and canon not in cmap:
                cmap[canon] = t.headers.index(header)
        if REQUIRED <= cmap.keys():
            out[t.table_id] = cmap
    return out


def build_ledger(doc: Document) -> Ledger:
    inv = doc.document_id
    items: list[LineItem] = []
    for r in iter_line_item_rows(doc):
        def prov(field: str, _r=r) -> Provenance:
            return Provenance(document_id=inv, page=_r.table.page, table_id=_r.table.table_id,
                              row=_r.row, column=_r.headers[field], bbox=_r.cells[field].bbox)
        try:
            qty = parse_money(r.cells["quantity"].value)
            price = parse_money(r.cells["unit_price"].value)
            amount = parse_money(r.cells["amount"].value)
        except ValueError as exc:
            raise ExtractionError(f"{r.item_id}: {exc}") from exc
        items.append(LineItem(id=r.item_id, description=r.cells["description"].value,
                              quantity=qty, unit_price=price, amount=amount,
                              source={f: prov(f) for f in REQUIRED}))
    if not items:
        raise ExtractionError("no line-item table found")

    scalars: dict[str, Decimal] = {}
    sources: dict[str, Provenance] = {}
    tax_lines: list[TaxLine] = []
    currency: str | None = None
    for block in sorted(doc.text_blocks, key=lambda b: (b.page, b.bbox[1], b.bbox[0])):
        if inside_any_table(doc, block):
            continue
        for line in block.text.splitlines():
            m = _CCY.search(line)
            if m:
                currency = m.group(1)
            la = parse_labeled_line(line)
            if la is None:
                continue
            src = Provenance(document_id=inv, page=block.page, block_id=block.block_id, bbox=block.bbox)
            if la.field == "tax":
                tax_lines.append(TaxLine(id=f"tax_{len(tax_lines) + 1:02d}", rate=la.rate,
                                         amount=la.amount, source={"amount": src}))
            elif la.field not in scalars:
                scalars[la.field] = la.amount
                sources[la.field] = src
    text_tax = bool(tax_lines)
    for e in summary_entries(doc):
        currency = currency or e.currency
        src = e.provenance(inv)
        if e.field == "tax":
            if not text_tax:
                tax_lines.append(TaxLine(id=f"tax_{len(tax_lines) + 1:02d}", rate=e.rate,
                                         amount=e.amount, source={"amount": src}))
        elif e.field not in scalars:
            scalars[e.field] = e.amount
            sources[e.field] = src
    if "total" not in scalars:
        raise ExtractionError("no grand total found")
    tax = sum((t.amount for t in tax_lines), Decimal("0")) if tax_lines else None
    return Ledger(invoice_id=inv, currency=currency or "USD", items=items, subtotal=scalars.get("subtotal"),
                  discount=scalars.get("discount"), tax=tax, tax_lines=tax_lines,
                  shipping=scalars.get("shipping"), fees=scalars.get("fees"),
                  total=scalars["total"], sources=sources)
