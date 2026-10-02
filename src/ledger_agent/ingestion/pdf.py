import pymupdf

from ledger_agent.models import DocumentPage
from ledger_agent.protocols import OcrBackend


def ingest_pdf(path, min_chars: int = 30, ocr: OcrBackend | None = None) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    with pymupdf.open(str(path)) as doc:
        for number, page in enumerate(doc, start=1):
            text = page.get_text("text")
            blocks = [
                {"block_id": f"p{number}_b{n}", "bbox": [x0, y0, x1, y1], "text": t.strip()}
                for (x0, y0, x1, y1, t, n, kind) in page.get_text("blocks")
                if kind == 0 and t.strip()
            ]
            scanned = len(text.strip()) < min_chars
            if scanned and ocr is not None:
                text, blocks = ocr.recognize(page.get_pixmap(dpi=200).tobytes("png"))
                pages.append(DocumentPage(page_number=number, text=text, blocks=blocks, is_ocr=True))
            else:
                pages.append(DocumentPage(page_number=number, text=text, blocks=blocks,
                                          needs_ocr=scanned))
    return pages
