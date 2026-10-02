from decimal import Decimal as D
import pytest
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.retrieval.chunks import build_chunks
from ledger_agent.retrieval.hybrid import IndexDisposedError, InvoiceScopeError, build_index
from ledger_agent.testing.ledgers import make_document

EMB = HashingEmbedder()
TEN = tuple((f"Part {i:02d}", D("2"), D("5.00")) for i in range(1, 11))

def test_chunks_cover_rows_and_totals():
    chunks = build_chunks(make_document())
    by_type = {}
    for c in chunks:
        by_type.setdefault(c.chunk_type, []).append(c)
    li = by_type["line_item"]
    assert [c.item_id for c in li] == ["line_01", "line_02"]
    assert li[0].values["amount"] == "1,014.00" and li[0].row_id == 1 and li[0].table_id == "table_01"
    assert li[0].provenance.page == 1 and li[0].provenance.row == 1
    assert {c.field for c in by_type["totals"]} == {"subtotal", "total"}
    [tax] = by_type["tax"]
    assert tax.item_id == "tax_01" and tax.values["amount"] == "104.40"
    assert all(c.invoice_id == "INV-001" for c in chunks)
    assert not any("Industrial Filter" in c.text for c in by_type.get("text", []))

def test_source_row_is_in_top_k():
    idx = build_index(make_document(items=TEN), EMB)
    res = idx.search("INV-001", "line_07 Part 07 quantity unit price amount", k=3,
                     chunk_types=["line_item"])
    assert "line_07" in [r.chunk.item_id for r in res]

@pytest.mark.parametrize("mode", ["hybrid", "bm25", "vector"])
def test_modes_return_results(mode):
    idx = build_index(make_document(items=TEN), EMB)
    assert idx.search("INV-001", "Part 03 line_03", k=2, mode=mode)

def test_identical_line_items_resolve_by_item_id():
    same = (("Gasket", D("3"), D("10.00")),) * 3
    idx = build_index(make_document(items=same), EMB)
    top = idx.search("INV-001", "line_02 Gasket quantity unit price amount", k=3,
                     chunk_types=["line_item"])[0]
    assert top.chunk.item_id == "line_02"

def test_cross_invoice_queries_are_rejected_and_never_leak():
    a = build_index(make_document(invoice_id="INV-A"), EMB)
    b = build_index(make_document(invoice_id="INV-B"), EMB)
    with pytest.raises(InvoiceScopeError):
        a.search("INV-B", "total")
    assert all(r.chunk.invoice_id == "INV-A" for r in a.search("INV-A", "total", k=10))
    assert all(r.chunk.invoice_id == "INV-B" for r in b.search("INV-B", "total", k=10))

def test_dispose():
    idx = build_index(make_document(), EMB)
    idx.dispose()
    with pytest.raises(IndexDisposedError):
        idx.search("INV-001", "total")


def test_summary_cells_become_chunks_with_table_provenance():
    from ledger_agent.retrieval.chunks import build_chunks
    from ledger_agent.testing.ledgers import make_net_worth_document
    chunks = build_chunks(make_net_worth_document())
    by_field = {c.field: c for c in chunks if c.field}
    assert by_field["total"].values == {"amount": "277163.70"} and by_field["total"].chunk_type == "totals"
    assert (by_field["total"].table_id, by_field["total"].row_id) == ("table_02", 2)
    assert by_field["total"].provenance.column == "Gross Worth"
    tax = next(c for c in chunks if c.chunk_type == "tax")
    assert tax.item_id == "tax_01" and tax.values == {"amount": "25196.70"}


def test_text_total_suppresses_summary_total_chunk():
    from ledger_agent.models import TextBlock
    from ledger_agent.retrieval.chunks import build_chunks
    from ledger_agent.testing.ledgers import make_net_worth_document
    doc = make_net_worth_document()
    doc.text_blocks.append(TextBlock(block_id="p1_b0", page=1, text="Total: $277,163.70", bbox=[0, 200, 50, 210]))
    totals = [c for c in build_chunks(doc) if c.field == "total"]
    assert len(totals) == 1 and totals[0].table_id is None
