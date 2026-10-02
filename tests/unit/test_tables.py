from ledger_agent.ingestion.tables import PyMuPDFTableExtractor, extract_tables
from ledger_agent.testing.invoices import default_spec, many_items_spec, render_invoice

def test_extract_default_table(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "a.pdf")
    [t] = extract_tables(pdf)
    assert (t.table_id, t.page) == ("table_01", 1)
    assert t.headers == ["Description", "Qty", "Unit Price", "Amount"]
    row1 = t.rows()[1]
    assert row1[0].value == "Industrial Filter" and row1[3].value == "1,014.00"
    assert len(row1[3].bbox) == 4 and not t.low_quality

def test_multipage_tables_get_global_ids(tmp_path):
    pdf = render_invoice(many_items_spec(80), tmp_path / "m.pdf")
    tables = PyMuPDFTableExtractor().extract(str(pdf))
    assert len(tables) >= 2
    assert [t.table_id for t in tables] == [f"table_{i:02d}" for i in range(1, len(tables) + 1)]
    assert all(t.headers[0] == "Description" for t in tables)
