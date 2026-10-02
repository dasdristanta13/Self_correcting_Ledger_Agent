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


def test_net_price_net_worth_headers_map_to_unit_price_and_amount():
    from ledger_agent.columns import REQUIRED, column_map
    headers = ["No.", "Description", "Qty", "UM", "Net Price", "Net Worth", "VAT %", "Gross Worth"]
    cmap = column_map(headers)
    assert cmap == {"description": 1, "quantity": 2, "unit_price": 4, "amount": 5}
    assert REQUIRED <= cmap.keys()


def test_summary_table_headers_are_not_a_line_item_table():
    from ledger_agent.columns import REQUIRED, column_map
    cmap = column_map(["", "VAT %", "Net Worth", "VAT", "Gross Worth"])
    assert not REQUIRED <= cmap.keys()
