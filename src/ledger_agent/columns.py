import re
from dataclasses import dataclass

from ledger_agent.models import Document, DocumentTable, TableCell, TextBlock

REQUIRED = frozenset({"description", "quantity", "unit_price", "amount"})
_SYNONYMS = {
    "description": {"description", "item", "product", "details", "name"},
    "quantity": {"qty", "quantity", "units"},
    "unit_price": {"unit price", "price", "rate", "unit cost"},
    "amount": {"amount", "total", "line total", "ext", "extended"},
}


def canonical_column(header: str) -> str | None:
    h = re.sub(r"[^a-z ]", "", header.lower()).strip()
    for canon, names in _SYNONYMS.items():
        if h in names:
            return canon
    return None


def column_map(headers: list[str], override: dict[str, int] | None = None) -> dict[str, int]:
    if override:
        return dict(override)
    out: dict[str, int] = {}
    for idx, header in enumerate(headers):
        canon = canonical_column(header)
        if canon and canon not in out:
            out[canon] = idx
    return out


@dataclass(frozen=True)
class LineItemRow:
    item_id: str                 # global across tables: line_01, line_02, ...
    table: DocumentTable
    row: int
    cells: dict[str, TableCell]  # canonical field -> cell
    headers: dict[str, str]      # canonical field -> printed header


def iter_line_item_rows(doc: Document):
    n = 0
    for table in sorted(doc.tables, key=lambda t: (t.page, t.table_id)):
        cmap = column_map(table.headers, doc.column_overrides.get(table.table_id))
        if not REQUIRED <= cmap.keys():
            continue
        for row_no, cells in table.rows().items():
            by_field = {f: cells[i] for f, i in cmap.items() if i in cells}
            if not REQUIRED <= by_field.keys():
                continue
            if not any(c.value.strip() for c in by_field.values()):
                continue
            n += 1
            yield LineItemRow(
                item_id=f"line_{n:02d}", table=table, row=row_no, cells=by_field,
                headers={f: table.headers[cmap[f]] for f in by_field},
            )


def inside_any_table(doc: Document, block: TextBlock) -> bool:
    cx = (block.bbox[0] + block.bbox[2]) / 2
    cy = (block.bbox[1] + block.bbox[3]) / 2
    return any(
        t.page == block.page and t.bbox[0] <= cx <= t.bbox[2] and t.bbox[1] <= cy <= t.bbox[3]
        for t in doc.tables
    )
