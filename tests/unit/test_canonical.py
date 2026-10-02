from ledger_agent.extraction.canonical import build_document, describe, locate_cell
from ledger_agent.ingestion.pdf import ingest_pdf
from ledger_agent.ingestion.tables import extract_tables
from ledger_agent.models import Provenance
from ledger_agent.testing.invoices import default_spec, render_invoice

def test_document_and_provenance_roundtrip(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    doc = build_document("INV-001", ingest_pdf(pdf), extract_tables(pdf))
    assert doc.document_id == "INV-001" and doc.text_blocks and doc.tables
    prov = Provenance(document_id="INV-001", page=1, table_id="table_01", row=1, column="Amount")
    assert locate_cell(doc, prov).value == "1,014.00"
    canon = prov.model_copy(update={"column": "amount"})
    assert locate_cell(doc, canon).value == "1,014.00"
    assert describe(prov) == "Invoice INV-001 / Page 1 / table_01 / Row 1 / Column: Amount"
    assert locate_cell(doc, Provenance(document_id="INV-001", page=1)) is None
