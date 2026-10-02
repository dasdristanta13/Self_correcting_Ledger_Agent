from decimal import Decimal as D
import pytest
from ledger_agent.config import ValidationRules
from ledger_agent.extraction.canonical import build_document, locate_cell
from ledger_agent.extraction.ledger import ExtractionError, build_ledger, resolve_column_overrides
from ledger_agent.fakes import FakeLLM
from ledger_agent.ingestion.pdf import ingest_pdf
from ledger_agent.ingestion.tables import extract_tables
from ledger_agent.testing.invoices import InvoiceSpec, ItemSpec, default_spec, many_items_spec, render_invoice
from ledger_agent.testing.ledgers import make_document, make_ledger, make_net_worth_document
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


def _add_row(doc, table_idx, row, values):
    from ledger_agent.models import TableCell
    t = doc.tables[table_idx]
    for c, v in enumerate(values):
        t.cells.append(TableCell(value=v, row=row, column=c, bbox=[50 + 100 * c, 300 + 20 * row, 150 + 100 * c, 320 + 20 * row]))

def test_non_item_rows_inside_table_are_skipped_and_chunks_stay_aligned():
    from ledger_agent.retrieval.chunks import build_chunks
    base = build_ledger(make_document())
    doc = make_document()
    _add_row(doc, 0, 3, ["Labor", "", "", ""])                      # section heading
    _add_row(doc, 0, 4, ["(continued from above)", "", "", ""])     # wrapped description
    _add_row(doc, 0, 5, ["", "", "Total", "1,044.00"])              # totals row
    led = build_ledger(doc)
    assert [(i.id, i.amount) for i in led.items] == [(i.id, i.amount) for i in base.items]
    chunk_ids = [c.item_id for c in build_chunks(doc) if c.chunk_type == "line_item"]
    assert chunk_ids == [i.id for i in led.items]

def test_partially_numeric_row_still_fails():
    doc = make_document()
    _add_row(doc, 0, 3, ["Widget", "2", "5.00", "ten"])
    with pytest.raises(ExtractionError, match="line_03"):
        build_ledger(doc)

def test_headerless_continuation_table_is_included():
    from ledger_agent.models import DocumentTable, TableCell
    doc = make_document()
    first = doc.tables[0]
    rows = [["Washer", "4", "2.50", "10.00"], ["Bolt", "2", "1.00", "2.00"]]
    cells = [TableCell(value=v, row=r, column=c, bbox=[50 + 100 * c, 100 + 20 * r, 150 + 100 * c, 120 + 20 * r])
             for r, row in enumerate(rows) for c, v in enumerate(row)]
    doc.tables.append(DocumentTable(table_id="table_02", page=2, headers=rows[0], cells=cells,
                                    bbox=[50, 100, 450, 160]))
    from ledger_agent.retrieval.chunks import build_chunks
    led = build_ledger(doc)
    assert [i.id for i in led.items] == ["line_01", "line_02", "line_03", "line_04"]
    assert [i.description for i in led.items[2:]] == ["Washer", "Bolt"]
    assert led.items[2].source["amount"].row == 0 and led.items[2].source["amount"].table_id == "table_02"
    assert [c.item_id for c in build_chunks(doc) if c.chunk_type == "line_item"] == [i.id for i in led.items]
    # header-bearing continuation (repeated header) still works and is not double counted
    assert len(first.rows()) == 2


def test_net_worth_layout_builds_a_validating_ledger():
    led = build_ledger(make_net_worth_document())
    assert led.currency == "INR"
    assert [(i.quantity, i.unit_price, i.amount) for i in led.items] == [(D("3.00"), D("83989.00"), D("251967.00"))]
    assert (led.subtotal, led.tax, led.total) == (D("251967.00"), D("25196.70"), D("277163.70"))
    assert led.tax_lines[0].rate == D("0.10")
    assert (led.sources["total"].table_id, led.sources["total"].column) == ("table_02", "Gross Worth")
    assert validate(led, ValidationRules()) == []


def test_net_worth_layout_without_total_row_is_an_extraction_error():
    with pytest.raises(ExtractionError, match="grand total"):
        build_ledger(make_net_worth_document(total_row=False))
