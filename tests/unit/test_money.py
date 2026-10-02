from decimal import Decimal
import pytest
from ledger_agent.money import parse_money, q2

def test_parse_money_formats():
    assert parse_money("$1,014.00") == Decimal("1014.00")
    assert parse_money("(5.00)") == Decimal("-5.00")
    assert parse_money("-$10.00") == Decimal("-10.00")
    assert parse_money("12 pcs") == Decimal("12")

def test_parse_money_rejects_garbage():
    for bad in ["", "abc", "1.2.3"]:
        with pytest.raises(ValueError):
            parse_money(bad)

def test_q2_rounds_half_up():
    assert q2(Decimal("1.005")) == Decimal("1.01")
    assert q2(Decimal("9.999")) == Decimal("10.00")
