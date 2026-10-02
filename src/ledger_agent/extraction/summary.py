import re
from dataclasses import dataclass
from decimal import Decimal

from ledger_agent.models import Document, DocumentTable, Provenance, TableCell
from ledger_agent.money import parse_money

_ROLES = {
    "rate": {"vat %", "tax %", "gst %"},
    "net": {"net worth", "net amount"},
    "tax": {"vat", "tax", "gst"},
    "gross": {"gross worth", "gross amount"},
}
_TOTAL_LABEL = re.compile(r"^(grand\s+)?total$", re.I)
_RATE = re.compile(r"^(\d+(?:\.\d+)?)\s*%$")
_CCY = re.compile(r"^([A-Z]{3})\b")


@dataclass(frozen=True)
class SummaryEntry:
    field: str
    amount: Decimal
    rate: Decimal | None
    table: DocumentTable
    row: int
    header: str
    cell: TableCell
    currency: str | None

    def provenance(self, document_id: str) -> Provenance:
        return Provenance(document_id=document_id, page=self.table.page, table_id=self.table.table_id,
                          row=self.row, column=self.header, bbox=self.cell.bbox)


def _role_columns(headers: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for idx, h in enumerate(headers):
        norm = " ".join(re.sub(r"[^a-z% ]", " ", h.lower()).split())
        for role, names in _ROLES.items():
            if norm in names and role not in out:
                out[role] = idx
    return out


def _entry(field, cell, rate, table, row) -> SummaryEntry | None:
    if cell is None or not cell.value:
        return None
    try:
        amount = parse_money(cell.value)
    except ValueError:
        return None
    m = _CCY.match(cell.value.strip())
    return SummaryEntry(field=field, amount=amount, rate=rate, table=table, row=row,
                        header=table.headers[cell.column], cell=cell, currency=m.group(1) if m else None)


def summary_entries(doc: Document) -> list[SummaryEntry]:
    out: list[SummaryEntry] = []
    for table in sorted(doc.tables, key=lambda t: (t.page, t.table_id)):
        cols = _role_columns(table.headers)
        if not {"rate", "net", "tax", "gross"} <= cols.keys():
            continue
        rows = table.rows(1)
        rate_rows = [(r, cells, _RATE.match(cells[cols["rate"]].value.strip()))
                     for r, cells in rows.items()
                     if cols["rate"] in cells and not cells.get(0, TableCell(value="", row=r, column=0, bbox=[0, 0, 0, 0])).value.strip()]
        rate_rows = [(r, cells, m) for r, cells, m in rate_rows if m]
        for r, cells, m in rate_rows:
            rate = Decimal(m.group(1)) / 100 if len(rate_rows) == 1 else None
            e = _entry("tax", cells.get(cols["tax"]), rate, table, r)
            if e:
                out.append(e)
        for r, cells in rows.items():
            if not _TOTAL_LABEL.match(cells[0].value.strip() if 0 in cells else ""):
                continue
            for field, role in (("subtotal", "net"), ("total", "gross")):
                e = _entry(field, cells.get(cols[role]), None, table, r)
                if e:
                    out.append(e)
            if not rate_rows:
                e = _entry("tax", cells.get(cols["tax"]), None, table, r)
                if e:
                    out.append(e)
    return out
