from decimal import Decimal
import pytest
from ledger_agent.paths import PathError, get_field, parse_path, set_field
from ledger_agent.testing.ledgers import make_ledger

def test_parse_path():
    assert parse_path("items[line_01].amount").kind == "item"
    assert parse_path("tax_lines[tax_01].amount").kind == "tax"
    assert parse_path("total").kind == "scalar"
    with pytest.raises(PathError):
        parse_path("items[line_01].description")
    with pytest.raises(PathError):
        parse_path("bogus")

def test_get_set_do_not_mutate_original():
    led = make_ledger()
    new = set_field(led, "items[line_01].amount", Decimal("1040.00"))
    assert get_field(led, "items[line_01].amount") == Decimal("1014.00")
    assert get_field(new, "items[line_01].amount") == Decimal("1040.00")

def test_set_tax_line_recomputes_tax_total():
    led = make_ledger(tax_rates=(Decimal("0.05"), Decimal("0.07")))
    new = set_field(led, "tax_lines[tax_01].amount", Decimal("1.00"))
    assert new.tax == Decimal("1.00") + led.tax_lines[1].amount

def test_missing_element():
    with pytest.raises(PathError):
        get_field(make_ledger(), "items[line_99].amount")
