from decimal import Decimal as D
from ledger_agent.config import ValidationRules
from ledger_agent.paths import set_field
from ledger_agent.testing.ledgers import make_ledger
from ledger_agent.validation.arithmetic import validate

R = ValidationRules()

def fields(ledger):
    return {d.field for d in validate(ledger, R)}

def test_correct_invoice_has_no_discrepancies():
    assert validate(make_ledger(), R) == []

def test_wrong_line_amount():
    led = set_field(make_ledger(), "items[line_01].amount", D("1040.00"))
    ds = validate(led, R)
    d = next(x for x in ds if x.field == "items[line_01].amount")
    assert (d.expected, d.observed, d.difference, d.rule) == (D("1014.00"), D("1040.00"), D("26.00"), "line_amount")
    assert "items[line_01].quantity" in d.related_fields
    assert "subtotal" in {x.field for x in ds}

def test_wrong_subtotal():
    led = make_ledger().model_copy(update={"subtotal": D("1050.00")})
    assert "subtotal" in fields(led)

def test_wrong_tax_line():
    led = set_field(make_ledger(), "tax_lines[tax_01].amount", D("100.00"))
    fs = fields(led)
    assert "tax_lines[tax_01].amount" in fs and "total" in fs

def test_wrong_total():
    led = make_ledger().model_copy(update={"total": D("1200.00")})
    ds = validate(led, R)
    assert [d.field for d in ds] == ["total"]
    assert {"total", "subtotal", "tax"} <= set(ds[0].related_fields)

def test_discount_applies_before_tax():
    assert validate(make_ledger(discount=D("44.00")), R) == []

def test_shipping_included_in_total():
    assert validate(make_ledger(shipping=D("15.00")), R) == []
    bad = make_ledger(shipping=D("15.00")).model_copy(update={"total": D("1148.40")})
    assert fields(bad) == {"total"}

def test_multiple_tax_rates():
    led = make_ledger(tax_rates=(D("0.05"), D("0.07")))
    assert validate(led, R) == []
    assert led.tax == D("52.20") + D("73.08")

def test_rounding_within_tolerance_passes_but_two_cents_fails():
    items = (("Widget", D("3"), D("3.333")),)
    led = make_ledger(items=items, tax_rates=())
    assert led.items[0].amount == D("10.00")
    near = set_field(led, "items[line_01].amount", D("10.01"))
    assert "items[line_01].amount" not in fields(near)
    far = set_field(led, "items[line_01].amount", D("10.02"))
    assert "items[line_01].amount" in fields(far)

def test_custom_total_terms():
    rules = ValidationRules(total_terms={"subtotal": 1})
    led = make_ledger()  # total includes tax, so a subtotal-only formula must flag it
    assert [d.field for d in validate(led, rules)] == ["total"]
