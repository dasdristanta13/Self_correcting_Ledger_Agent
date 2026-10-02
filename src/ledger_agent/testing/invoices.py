from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ledger_agent.money import q2


@dataclass
class ItemSpec:
    description: str
    quantity: Decimal
    unit_price: Decimal
    printed_amount: Decimal | None = None   # override to print a wrong amount


@dataclass
class InvoiceSpec:
    invoice_id: str
    items: list[ItemSpec]
    currency: str = "USD"
    discount: Decimal = Decimal("0")
    tax_rates: tuple[Decimal, ...] = (Decimal("0.10"),)
    shipping: Decimal = Decimal("0")
    printed_subtotal: Decimal | None = None
    printed_taxes: tuple[Decimal | None, ...] = ()
    printed_total: Decimal | None = None

    def resolved(self):
        amounts = [i.printed_amount if i.printed_amount is not None
                   else q2(i.quantity * i.unit_price) for i in self.items]
        subtotal = (self.printed_subtotal if self.printed_subtotal is not None
                    else sum(amounts, Decimal("0")))
        base = subtotal - self.discount
        taxes = []
        for n, rate in enumerate(self.tax_rates):
            over = self.printed_taxes[n] if n < len(self.printed_taxes) else None
            taxes.append((rate, over if over is not None else q2(base * rate)))
        total = (self.printed_total if self.printed_total is not None
                 else q2(subtotal - self.discount + sum((t for _, t in taxes), Decimal("0"))
                         + self.shipping))
        return amounts, subtotal, taxes, total


def default_spec(invoice_id: str = "INV-001") -> InvoiceSpec:
    return InvoiceSpec(invoice_id, [
        ItemSpec("Industrial Filter", Decimal("12"), Decimal("84.50")),
        ItemSpec("Gasket", Decimal("3"), Decimal("10.00")),
    ])


def many_items_spec(n: int, invoice_id: str = "INV-MANY") -> InvoiceSpec:
    return InvoiceSpec(invoice_id, [
        ItemSpec(f"Part {i:03d}", Decimal(i % 5 + 1), Decimal("2.50")) for i in range(1, n + 1)
    ])


def _m(v: Decimal) -> str:
    return f"${v:,.2f}"


def render_invoice(spec: InvoiceSpec, path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    amounts, subtotal, taxes, total = spec.resolved()
    styles = getSampleStyleSheet()
    flow = [Paragraph(f"Invoice #{spec.invoice_id}", styles["Title"]),
            Paragraph(f"Currency: {spec.currency}", styles["Normal"]), Spacer(1, 12)]
    data = [["Description", "Qty", "Unit Price", "Amount"]]
    for it, amt in zip(spec.items, amounts):
        data.append([it.description, f"{it.quantity:f}", f"{it.unit_price:,.2f}", f"{amt:,.2f}"])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    flow += [table, Spacer(1, 12), Paragraph(f"Subtotal: {_m(subtotal)}", styles["Normal"])]
    if spec.discount:
        flow.append(Paragraph(f"Discount: {_m(spec.discount)}", styles["Normal"]))
    for rate, amt in taxes:
        flow.append(Paragraph(f"Tax ({(rate * 100).normalize():f}%): {_m(amt)}", styles["Normal"]))
    if spec.shipping:
        flow.append(Paragraph(f"Shipping: {_m(spec.shipping)}", styles["Normal"]))
    flow.append(Paragraph(f"Total: {_m(total)}", styles["Normal"]))
    path = Path(path)
    SimpleDocTemplate(str(path), pagesize=letter).build(flow)
    return path
