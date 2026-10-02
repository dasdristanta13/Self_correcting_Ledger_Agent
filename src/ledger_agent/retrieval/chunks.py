from ledger_agent.columns import inside_any_table, iter_line_item_rows
from ledger_agent.extraction.summary import summary_entries
from ledger_agent.models import Chunk, Document, Provenance
from ledger_agent.textparse import parse_labeled_line

_TYPE = {"subtotal": "totals", "total": "totals", "tax": "tax", "discount": "discount",
         "shipping": "shipping", "fees": "shipping"}


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def build_chunks(doc: Document) -> list[Chunk]:
    inv = doc.document_id
    chunks: list[Chunk] = []
    for r in iter_line_item_rows(doc):
        values = {f: c.value for f, c in r.cells.items()}
        text = (f"Invoice {inv} | Page {r.table.page} | {r.table.table_id} | Row {r.row} | {r.item_id}\n"
                f"Description: {values['description']}\nQuantity: {values['quantity']}\n"
                f"Unit Price: {values['unit_price']}\nAmount: {values['amount']}")
        prov = Provenance(document_id=inv, page=r.table.page, table_id=r.table.table_id,
                          row=r.row, bbox=_union([c.bbox for c in r.cells.values()]))
        chunks.append(Chunk(chunk_id=f"{inv}:{r.item_id}", invoice_id=inv, chunk_type="line_item",
                            text=text, page=r.table.page, table_id=r.table.table_id,
                            row_id=r.row, item_id=r.item_id, values=values, provenance=prov))
    tax_n = 0
    for block in sorted(doc.text_blocks, key=lambda b: (b.page, b.bbox[1], b.bbox[0])):
        if inside_any_table(doc, block):
            continue
        for n, line in enumerate(block.text.splitlines()):
            prov = Provenance(document_id=inv, page=block.page, block_id=block.block_id,
                              bbox=block.bbox)
            la = parse_labeled_line(line)
            if la is None:
                kind = "header" if "invoice #" in line.lower() else "text"
                chunks.append(Chunk(chunk_id=f"{inv}:{block.block_id}:{n}", invoice_id=inv,
                                    chunk_type=kind, text=f"Invoice {inv} | Page {block.page} | {line}",
                                    page=block.page, provenance=prov))
                continue
            item_id = None
            if la.field == "tax":
                tax_n += 1
                item_id = f"tax_{tax_n:02d}"
            chunks.append(Chunk(
                chunk_id=f"{inv}:{block.block_id}:{n}", invoice_id=inv, chunk_type=_TYPE[la.field],
                text=f"Invoice {inv} | Page {block.page} | {item_id or la.field} | {line.strip()}",
                page=block.page, item_id=item_id, field=la.field,
                values={"amount": str(la.amount)}, provenance=prov))
    for e in summary_entries(doc):
        item_id = None
        if e.field == "tax":
            if tax_n:                       # labeled text tax lines win, as in build_ledger
                continue
            item_id = f"tax_{sum(1 for c in chunks if c.chunk_type == 'tax') + 1:02d}"
        chunks.append(Chunk(
            chunk_id=f"{inv}:{e.table.table_id}:r{e.row}c{e.cell.column}", invoice_id=inv,
            chunk_type=_TYPE[e.field], page=e.table.page, table_id=e.table.table_id, row_id=e.row,
            item_id=item_id, field=e.field, values={"amount": str(e.amount)},
            text=f"Invoice {inv} | Page {e.table.page} | {item_id or e.field} | {e.header}: {e.cell.value}",
            provenance=e.provenance(inv)))
    return chunks
