from decimal import Decimal

from ledger_agent.models import (
    Document, DocumentPage, DocumentTable, Ledger, LineItem, Provenance, TableCell,
    TaxLine, TextBlock,
)
from ledger_agent.money import q2

_DEFAULT_ITEMS = (
    ("Industrial Filter", Decimal("12"), Decimal("84.50")),
    ("Gasket", Decimal("3"), Decimal("10.00")),
)
_HEADERS = ["Description", "Qty", "Unit Price", "Amount"]


def make_ledger(items=None, discount=None, tax_rates=(Decimal("0.10"),), shipping=None,
                invoice_id="INV-001") -> Ledger:
    items = items or _DEFAULT_ITEMS
    line_items = []
    for n, (desc, qty, price) in enumerate(items, start=1):
        src = {"amount": Provenance(document_id=invoice_id, page=1, table_id="table_01",
                                    row=n, column="Amount")}
        line_items.append(LineItem(id=f"line_{n:02d}", description=desc, quantity=qty,
                                   unit_price=price, amount=q2(qty * price), source=src))
    subtotal = sum((i.amount for i in line_items), Decimal("0"))
    base = subtotal - (discount or Decimal("0"))
    tax_lines = [TaxLine(id=f"tax_{n:02d}", rate=r, amount=q2(base * r))
                 for n, r in enumerate(tax_rates, start=1)]
    tax = sum((t.amount for t in tax_lines), Decimal("0")) if tax_lines else None
    total = q2(subtotal - (discount or 0) + (tax or 0) + (shipping or 0))
    return Ledger(invoice_id=invoice_id, items=line_items, subtotal=subtotal,
                  discount=discount, tax=tax, tax_lines=tax_lines, shipping=shipping,
                  total=total)


def _fmt(v: Decimal) -> str:
    return f"{v:,.2f}"


def make_document(items=None, discount=None, tax_rates=(Decimal("0.10"),), shipping=None,
                  invoice_id="INV-001") -> Document:
    led = make_ledger(items, discount, tax_rates, shipping, invoice_id)
    cells = [TableCell(value=h, row=0, column=c, bbox=[50 + 100 * c, 100, 150 + 100 * c, 120])
             for c, h in enumerate(_HEADERS)]
    for r, it in enumerate(led.items, start=1):
        vals = [it.description, f"{it.quantity:f}", _fmt(it.unit_price), _fmt(it.amount)]
        for c, v in enumerate(vals):
            y = 100 + 20 * r
            cells.append(TableCell(value=v, row=r, column=c,
                                   bbox=[50 + 100 * c, y, 150 + 100 * c, y + 20]))
    y_end = 100 + 20 * (len(led.items) + 1)
    table = DocumentTable(table_id="table_01", page=1, headers=list(_HEADERS), cells=cells,
                          bbox=[50, 100, 450, y_end])
    lines = [f"Invoice #{invoice_id}", "Currency: USD", f"Subtotal: ${_fmt(led.subtotal)}"]
    if discount:
        lines.append(f"Discount: ${_fmt(discount)}")
    for t in led.tax_lines:
        lines.append(f"Tax ({(t.rate * 100).normalize():f}%): ${_fmt(t.amount)}")
    if shipping:
        lines.append(f"Shipping: ${_fmt(shipping)}")
    lines.append(f"Total: ${_fmt(led.total)}")
    blocks = [TextBlock(block_id=f"p1_b{n}", page=1, text=t,
                        bbox=[50, y_end + 20 * (n + 1), 300, y_end + 20 * (n + 2)])
              for n, t in enumerate(lines)]
    page = DocumentPage(page_number=1, text="\n".join(lines))
    return Document(document_id=invoice_id, pages=[page], tables=[table], text_blocks=blocks)
