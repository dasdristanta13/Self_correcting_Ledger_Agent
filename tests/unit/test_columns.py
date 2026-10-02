from ledger_agent.columns import canonical_column, iter_line_item_rows
from ledger_agent.testing.ledgers import make_document

def test_canonical_column():
    assert canonical_column("Unit Price") == "unit_price"
    assert canonical_column("QTY") == "quantity"
    assert canonical_column("Notes") is None

def test_item_ids_are_global_and_ordered():
    rows = list(iter_line_item_rows(make_document()))
    assert [r.item_id for r in rows] == ["line_01", "line_02"]
    assert rows[0].cells["amount"].value == "1,014.00"
    assert rows[0].headers["unit_price"] == "Unit Price"
