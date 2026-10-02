from decimal import Decimal as D

from ledger_agent.extraction.summary import summary_entries
from ledger_agent.models import Document, DocumentPage, DocumentTable, TableCell


def _doc(rows):
    headers = ["", "VAT %", "Net Worth", "VAT", "Gross Worth"]
    cells = [TableCell(value=h, row=0, column=c, bbox=[0, 0, 1, 1]) for c, h in enumerate(headers)]
    for r, row in enumerate(rows, start=1):
        cells += [TableCell(value=v, row=r, column=c, bbox=[c, r, c + 1, r + 1]) for c, v in enumerate(row)]
    t = DocumentTable(table_id="table_02", page=1, headers=headers, cells=cells, bbox=[0, 0, 5, 5])
    return Document(document_id="X", pages=[DocumentPage(page_number=1, text="")], tables=[t], text_blocks=[])


def _by_field(entries):
    return {(e.field, e.rate): e for e in entries}


def test_single_rate_summary():
    doc = _doc([["", "10%", "251,967.00", "25,196.70", "277,163.70"],
                ["Total", "", "INR 251,967.00", "INR 25,196.70", "INR 277,163.70"]])
    es = summary_entries(doc)
    got = {(e.field, e.rate): e.amount for e in es}
    assert got == {("tax", D("0.10")): D("25196.70"), ("subtotal", None): D("251967.00"),
                   ("total", None): D("277163.70")}
    assert {e.currency for e in es if e.field != "tax" or e.rate is None} <= {"INR", None}
    total = _by_field(es)[("total", None)]
    assert (total.table.table_id, total.row, total.header) == ("table_02", 2, "Gross Worth")
    assert total.provenance("X").bbox == total.cell.bbox


def test_wrapped_currency_cell_is_merged_by_extractor_and_parses():
    doc = _doc([["", "10%", "100.00", "10.00", "110.00"],
                ["Total", "", "INR 100.00", "INR 10.00", "INR 110.00"]])
    assert any(e.currency == "INR" for e in summary_entries(doc))


def test_multiple_rate_rows_drop_the_rate():
    doc = _doc([["", "5%", "100.00", "5.00", "105.00"], ["", "12%", "100.00", "12.00", "112.00"],
                ["Total", "", "200.00", "17.00", "217.00"]])
    es = summary_entries(doc)
    taxes = [e for e in es if e.field == "tax"]
    assert [e.amount for e in taxes] == [D("5.00"), D("12.00")] and all(e.rate is None for e in taxes)
    assert _by_field(es)[("total", None)].amount == D("217.00")


def test_total_row_supplies_tax_when_no_rate_rows():
    es = summary_entries(_doc([["Total", "", "100.00", "10.00", "110.00"]]))
    assert [(e.field, e.amount) for e in es if e.field == "tax"] == [("tax", D("10.00"))]


def test_line_item_table_is_not_a_summary():
    headers = ["No.", "Description", "Qty", "UM", "Net Price", "Net Worth", "VAT %", "Gross Worth"]
    cells = [TableCell(value=h, row=0, column=c, bbox=[0, 0, 1, 1]) for c, h in enumerate(headers)]
    t = DocumentTable(table_id="table_01", page=1, headers=headers, cells=cells, bbox=[0, 0, 5, 5])
    assert summary_entries(Document(document_id="X", pages=[], tables=[t], text_blocks=[])) == []
