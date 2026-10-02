import re
from dataclasses import dataclass

from ledger_agent.money import parse_money
from ledger_agent.models import Document, DocumentTable, TableCell, TextBlock

REQUIRED = frozenset({"description", "quantity", "unit_price", "amount"})
_SYNONYMS = {
    "description": {"description", "item", "product", "details", "name"},
    "quantity": {"qty", "quantity", "units"},
    "unit_price": {"unit price", "price", "rate", "unit cost", "net price"},
    "amount": {"amount", "total", "line total", "ext", "extended", "net worth"},
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


_NON_ITEM_LABEL = re.compile(
    r"^(sub\s*)?total|balance|amount due|tax|vat|gst|discount|shipping|freight|fees?", re.I)


def _numeric(value: str) -> bool:
    try:
        parse_money(value)
        return True
    except ValueError:
        return False


def _is_item_row(by_field: dict[str, TableCell]) -> bool:
    """False for headings, wrapped-description continuations and totals rows."""
    qty = _numeric(by_field["quantity"].value)
    price = _numeric(by_field["unit_price"].value)
    amount = _numeric(by_field["amount"].value)
    if not (qty or price or amount):
        return False
    if not (qty or price):
        desc = by_field["description"].value.strip()
        if not desc or _NON_ITEM_LABEL.match(desc) or any(
                _NON_ITEM_LABEL.match(by_field[f].value.strip()) for f in ("quantity", "unit_price")):
            return False
    return True


def iter_line_item_rows(doc: Document):
    """Yield line-item rows across tables with global ids.

    A table on a later page with no mappable header but the same column count as the
    previous item table is a headerless continuation: it reuses that table's column map
    and printed headers, and its row 0 (taken as a header by the table extractor) is a
    DATA row, reported with Provenance.row == 0 (its true cell row index).
    """
    n = 0
    prev: tuple[int, dict[str, int], list[str], int] | None = None  # page, cmap, headers, ncols
    for table in sorted(doc.tables, key=lambda t: (t.page, t.table_id)):
        cmap = column_map(table.headers, doc.column_overrides.get(table.table_id))
        headers, min_row = table.headers, 1
        if REQUIRED <= cmap.keys():
            prev = (table.page, cmap, table.headers, len(table.headers))
        elif prev and table.page > prev[0] and len(table.headers) == prev[3]:
            cmap, headers, min_row = prev[1], prev[2], 0
        else:
            continue
        for row_no, cells in table.rows(min_row).items():
            by_field = {f: cells[i] for f, i in cmap.items() if i in cells}
            if not REQUIRED <= by_field.keys() or not _is_item_row(by_field):
                continue
            n += 1
            yield LineItemRow(
                item_id=f"line_{n:02d}", table=table, row=row_no, cells=by_field,
                headers={f: headers[cmap[f]] for f in by_field},
            )


def inside_any_table(doc: Document, block: TextBlock) -> bool:
    cx = (block.bbox[0] + block.bbox[2]) / 2
    cy = (block.bbox[1] + block.bbox[3]) / 2
    return any(
        t.page == block.page and t.bbox[0] <= cx <= t.bbox[2] and t.bbox[1] <= cy <= t.bbox[3]
        for t in doc.tables
    )
