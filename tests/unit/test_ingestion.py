import pymupdf
from ledger_agent.ingestion.pdf import ingest_pdf
from ledger_agent.testing.invoices import default_spec, render_invoice

class FakeOcr:
    def recognize(self, page_png):
        return "Total: $1.00 scanned text that is long enough", [
            {"block_id": "ocr_b0", "bbox": [0, 0, 1, 1], "text": "Total: $1.00"}]

def blank_pdf(path):
    d = pymupdf.open(); d.new_page(); d.save(path); d.close()
    return path

def test_native_pdf_needs_no_ocr(tmp_path):
    pages = ingest_pdf(render_invoice(default_spec(), tmp_path / "a.pdf"))
    assert len(pages) == 1 and not pages[0].is_ocr and not pages[0].needs_ocr
    assert "Invoice #INV-001" in pages[0].text
    assert pages[0].blocks and len(pages[0].blocks[0]["bbox"]) == 4
    assert pages[0].blocks[0]["block_id"].startswith("p1_b")

def test_blank_page_flagged_when_no_ocr(tmp_path):
    pages = ingest_pdf(blank_pdf(tmp_path / "b.pdf"))
    assert pages[0].needs_ocr and not pages[0].is_ocr

def test_blank_page_uses_ocr_backend(tmp_path):
    pages = ingest_pdf(blank_pdf(tmp_path / "c.pdf"), ocr=FakeOcr())
    assert pages[0].is_ocr and not pages[0].needs_ocr and "scanned" in pages[0].text
