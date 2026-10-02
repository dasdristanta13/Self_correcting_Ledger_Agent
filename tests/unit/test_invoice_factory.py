import pymupdf
from ledger_agent.testing.invoices import default_spec, many_items_spec, render_invoice

def test_render_default_invoice(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    with pymupdf.open(pdf) as doc:
        text = doc[0].get_text()
        assert "Invoice #INV-001" in text
        assert "Total: $1,148.40" in text
        tables = doc[0].find_tables().tables
        assert len(tables) == 1
        rows = tables[0].extract()
        assert rows[0] == ["Description", "Qty", "Unit Price", "Amount"]
        assert len(rows) == 3

def test_many_items_spans_pages_with_repeated_header(tmp_path):
    pdf = render_invoice(many_items_spec(80), tmp_path / "INV-MANY.pdf")
    with pymupdf.open(pdf) as doc:
        assert doc.page_count >= 2
        for page in doc:
            tables = page.find_tables().tables
            assert tables and tables[0].extract()[0][0] == "Description"
