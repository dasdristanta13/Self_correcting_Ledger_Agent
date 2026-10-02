import pymupdf

from ledger_agent.models import DocumentTable, TableCell


def _clean(value) -> str:
    return " ".join((value or "").split())


def extract_tables(path) -> list[DocumentTable]:
    out: list[DocumentTable] = []
    with pymupdf.open(str(path)) as doc:
        for page_no, page in enumerate(doc, start=1):
            for t in page.find_tables().tables:
                rows = t.extract()
                if len(rows) < 2:
                    continue
                headers = [_clean(h) for h in rows[0]]
                cells: list[TableCell] = []
                for r, trow in enumerate(t.rows):
                    for c, bbox in enumerate(trow.cells):
                        box = list(bbox) if bbox else list(trow.bbox)
                        cells.append(TableCell(value=_clean(rows[r][c]), row=r, column=c, bbox=box))
                filled = sum(1 for c in cells if c.value)
                low = (filled / len(cells) < 0.6) or any(not h for h in headers)
                out.append(DocumentTable(table_id=f"table_{len(out) + 1:02d}", page=page_no,
                                         headers=headers, cells=cells, bbox=list(t.bbox),
                                         low_quality=low))
    return out


class PyMuPDFTableExtractor:
    def extract(self, pdf_path: str) -> list[DocumentTable]:
        return extract_tables(pdf_path)
