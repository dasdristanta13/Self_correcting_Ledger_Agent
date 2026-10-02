from decimal import Decimal as D
import pytest
from ledger_agent.config import ValidationRules
from ledger_agent.extraction.canonical import build_document, locate_cell
from ledger_agent.extraction.ledger import ExtractionError, build_ledger, resolve_column_overrides
from ledger_agent.fakes import FakeLLM
from ledger_agent.ingestion.pdf import ingest_pdf
from ledger_agent.ingestion.tables import extract_tables
from ledger_agent.testing.invoices import InvoiceSpec, ItemSpec, default_spec, many_items_spec, render_invoice
from ledger_agent.testing.ledgers import make_document, make_ledger
from ledger_agent.validation.arithmetic import validate

def doc_from(spec, tmp_path):
    pdf = render_invoice(spec, tmp_path / f"{spec.invoice_id}.pdf")
    return build_document(spec.invoice_id, ingest_pdf(pdf), extract_tables(pdf))

def test_hand_built_document_matches_reference_ledger():
    led = build_ledger(make_document())
    ref = make_ledger()
    assert (led.subtotal, led.tax, led.total) == (ref.subtotal, ref.tax, ref.total)
    assert led.items[0].amount == D("1014.00") and led.tax_lines[0].rate == D("0.10")

def test_real_pdf_roundtrip_has_provenance(tmp_path):
    spec = default_spec()
    doc = doc_from(spec, tmp_path)
    led = build_ledger(doc)
    assert led.invoice_id == "INV-001" and led.currency == "USD"
    assert validate(led, ValidationRules()) == []
    src = led.items[0].source["amount"]
    assert (src.page, src.table_id, src.row, src.column) == (1, "table_01", 1, "Amount")
    assert locate_cell(doc, src).value == "1,014.00"
    assert led.sources["total"].block_id

def test_discount_shipping_multi_tax(tmp_path):
    spec = default_spec()
    spec.discount, spec.shipping = D("44.00"), D("15.00")
    spec.tax_rates = (D("0.05"), D("0.07"))
    led = build_ledger(doc_from(spec, tmp_path))
    assert led.discount == D("44.00") and led.shipping == D("15.00") and len(led.tax_lines) == 2
    assert validate(led, ValidationRules()) == []

def test_multipage_item_ids_are_global(tmp_path):                      # Review Focus 1
    led = build_ledger(doc_from(many_items_spec(80), tmp_path))
    assert [i.id for i in led.items] == [f"line_{n:02d}" for n in range(1, 81)]
    assert validate(led, ValidationRules()) == []

def test_missing_total_or_table_raises(tmp_path):                      # Review Focus 4
    doc = make_document()
    doc.text_blocks = [b for b in doc.text_blocks if not b.text.startswith("Total")]
    with pytest.raises(ExtractionError, match="grand total"):
        build_ledger(doc)
    doc2 = make_document()
    doc2.tables = []
    with pytest.raises(ExtractionError, match="line-item"):
        build_ledger(doc2)

def test_llm_maps_unknown_headers():
    doc = make_document()
    t = doc.tables[0]
    t.headers = ["Part", "Count", "Each", "Line Cost"]
    assert resolve_column_overrides(doc, None) == {}
    llm = FakeLLM([{"mapping": {"Part": "description", "Count": "quantity",
                                "Each": "unit_price", "Line Cost": "amount"}}])
    doc.column_overrides = resolve_column_overrides(doc, llm)
    assert doc.column_overrides == {"table_01": {"description": 0, "quantity": 1, "unit_price": 2, "amount": 3}}
    assert build_ledger(doc).items[0].amount == D("1014.00")

def test_llm_incomplete_mapping_is_ignored():
    doc = make_document()
    doc.tables[0].headers = ["Part", "Count", "Each", "Line Cost"]
    llm = FakeLLM([{"mapping": {"Part": "description"}}])
    assert resolve_column_overrides(doc, llm) == {}
