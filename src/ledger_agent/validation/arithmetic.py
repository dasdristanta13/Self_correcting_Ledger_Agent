from decimal import Decimal

from ledger_agent.config import ValidationRules
from ledger_agent.models import Discrepancy, Ledger
from ledger_agent.money import q2

ZERO = Decimal("0")


def _check(field, expected, observed, rule, related, tol):
    diff = observed - expected
    if abs(diff) > tol:
        return Discrepancy(field=field, expected=expected, observed=observed,
                           difference=diff, rule=rule, related_fields=related)
    return None


def validate(ledger: Ledger, rules: ValidationRules) -> list[Discrepancy]:
    tol = rules.tolerance
    out: list[Discrepancy] = []

    def add(d):
        if d:
            out.append(d)

    for it in ledger.items:
        base = f"items[{it.id}]"
        add(_check(f"{base}.amount", q2(it.quantity * it.unit_price), it.amount, "line_amount",
                   [f"{base}.amount", f"{base}.quantity", f"{base}.unit_price"], tol))

    items_sum = sum((i.amount for i in ledger.items), ZERO)
    if ledger.subtotal is not None:
        add(_check("subtotal", items_sum, ledger.subtotal, "subtotal_sum", ["subtotal"], tol))

    subtotal = ledger.subtotal if ledger.subtotal is not None else items_sum
    tax_base = subtotal - (ledger.discount or ZERO)
    for t in ledger.tax_lines:
        if t.rate is not None:
            add(_check(f"tax_lines[{t.id}].amount", q2(tax_base * t.rate), t.amount, "tax_rate",
                       [f"tax_lines[{t.id}].amount"], tol))

    tax_total = ledger.tax if ledger.tax is not None else sum((t.amount for t in ledger.tax_lines), ZERO)
    values = {"subtotal": subtotal, "discount": ledger.discount, "tax": tax_total,
              "shipping": ledger.shipping, "fees": ledger.fees}
    expected = q2(sum((sign * (values.get(name) or ZERO) for name, sign in rules.total_terms.items()), ZERO))
    present = [n for n in ("subtotal", "discount", "tax", "shipping", "fees")
               if n in rules.total_terms and getattr(ledger, n) is not None]
    add(_check("total", expected, ledger.total, "grand_total", ["total", *present], tol))
    return out
