from ledger_agent.columns import column_map
from ledger_agent.models import Document, DocumentPage, DocumentTable, Provenance, TableCell, TextBlock


def build_document(document_id: str, pages: list[DocumentPage], tables: list[DocumentTable]) -> Document:
    blocks = [TextBlock(block_id=b["block_id"], page=p.page_number, text=b["text"], bbox=list(b["bbox"]))
              for p in pages for b in p.blocks]
    return Document(document_id=document_id, pages=pages, tables=tables, text_blocks=blocks)


def locate_cell(doc: Document, prov: Provenance) -> TableCell | None:
    if prov.table_id is None or prov.row is None or prov.column is None:
        return None
    table = doc.table(prov.table_id)
    if table is None:
        return None
    if prov.column in table.headers:
        col = table.headers.index(prov.column)
    else:
        col = column_map(table.headers, doc.column_overrides.get(table.table_id)).get(prov.column)
    if col is None:
        return None
    return next((c for c in table.cells if c.row == prov.row and c.column == col), None)


def describe(prov: Provenance) -> str:
    parts = [f"Invoice {prov.document_id}", f"Page {prov.page}"]
    if prov.table_id:
        parts.append(prov.table_id)
    if prov.row is not None:
        parts.append(f"Row {prov.row}")
    if prov.column:
        parts.append(f"Column: {prov.column}")
    return " / ".join(parts)
