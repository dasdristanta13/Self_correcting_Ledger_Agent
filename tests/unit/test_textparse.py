from decimal import Decimal
from ledger_agent.textparse import parse_labeled_line, tokenize

def test_tokenize_normalizes_thousands_commas():
    assert tokenize("Amount: $1,014.00 | Row 7") == ["amount", "1014.00", "row", "7"]
    assert "line_07" in tokenize("line_07 Gasket")

def test_labeled_lines():
    a = parse_labeled_line("Subtotal: $1,044.00")
    assert (a.field, a.amount, a.rate) == ("subtotal", Decimal("1044.00"), None)
    t = parse_labeled_line("Tax (10%): $104.40")
    assert (t.field, t.amount, t.rate) == ("tax", Decimal("104.40"), Decimal("0.10"))
    assert parse_labeled_line("Grand Total: $5.00").field == "total"
    assert parse_labeled_line("Discount: -$10.00").amount == Decimal("10.00")
    assert parse_labeled_line("Industrial Filter") is None
    assert parse_labeled_line("Total") is None
