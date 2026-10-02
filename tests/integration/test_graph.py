from decimal import Decimal as D
import pymupdf
from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.config import Config
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps, run_invoice
from ledger_agent.models import Discrepancy
from ledger_agent.state import Status
from ledger_agent.testing.corrupt import corrupting_builder, scripted_validator
from ledger_agent.testing.invoices import InvoiceSpec, ItemSpec, default_spec, render_invoice

def deps(**kw):
    return Deps(embedder=HashingEmbedder(), proposer=kw.pop("proposer", ChunkValueProposer()), **kw)

def test_line_amount_extraction_error_is_corrected_with_provenance(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps(ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00"))))
    assert res.status == Status.RECONCILED and res.iterations == 1
    [rec] = res.corrections
    assert (rec.revision, rec.field, rec.old_value, rec.new_value) == (1, "items[line_01].amount", D("1040.00"), D("1014.00"))
    assert (rec.source_page, rec.source_table, rec.source_row) == (1, "table_01", 1)
    assert rec.confidence >= 0.9
    assert res.ledger.items[0].amount == D("1014.00")
    assert res.original_ledger.items[0].amount == D("1040.00")      # original preserved

def test_wrong_total_extraction_error_is_corrected(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps(ledger_builder=corrupting_builder("total", D("1200.00"))))
    assert res.status == Status.RECONCILED and res.ledger.total == D("1148.40")

def test_duplicate_lines_patch_the_right_row(tmp_path):                # Review Focus 2
    spec = InvoiceSpec("INV-DUP", [ItemSpec("Gasket", D("3"), D("10.00"))] * 3)
    pdf = render_invoice(spec, tmp_path / "INV-DUP.pdf")
    res = run_invoice(str(pdf), deps(ledger_builder=corrupting_builder("items[line_02].amount", D("99.00"))))
    assert res.status == Status.RECONCILED
    assert [(r.field, r.source_row) for r in res.corrections] == [("items[line_02].amount", 2)]

def test_invoice_that_is_itself_wrong_is_unresolved_not_guessed(tmp_path):  # Review Focus 5
    spec = default_spec()
    spec.items[0].printed_amount = D("1040.00")
    pdf = render_invoice(spec, tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps())
    assert res.status == Status.UNRESOLVED and res.iterations == 0 and res.corrections == []

class LowConfidence(ChunkValueProposer):
    def propose(self, discrepancy, chunks):
        return [e.model_copy(update={"confidence": 0.5}) for e in super().propose(discrepancy, chunks)]

def test_weak_evidence_is_insufficient(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps(proposer=LowConfidence(),
                                     ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00"))))
    assert res.status == Status.INSUFFICIENT_EVIDENCE and res.iterations == 0

def disc(field, exp, obs, related):
    return Discrepancy(field=field, expected=D(exp), observed=D(obs),
                       difference=D(obs) - D(exp), rule="line_amount", related_fields=related)

L1 = disc("items[line_01].amount", "1014.00", "1040.00",
          ["items[line_01].amount", "items[line_01].quantity", "items[line_01].unit_price"])
L2 = disc("items[line_02].amount", "30.00", "99.00",
          ["items[line_02].amount", "items[line_02].quantity", "items[line_02].unit_price"])

def test_no_progress_terminates(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps(ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00")),
                                     validator=scripted_validator([[L1]])))  # same discrepancy forever
    assert res.status == Status.NO_PROGRESS and res.iterations == 1

def test_max_revisions_terminates(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    builder = corrupting_builder("items[line_01].amount", D("1040.00"), also=("items[line_02].amount", D("99.00")))
    res = run_invoice(str(pdf), deps(config=Config(max_revisions=1), ledger_builder=builder,
                                     validator=scripted_validator([[L1], [L2]])))
    assert res.status == Status.MAX_REVISIONS_EXCEEDED and res.iterations == 1

def test_zero_revisions_allowed_blocks_correction(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps(config=Config(max_revisions=0),
                                     ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00"))))
    assert res.status == Status.MAX_REVISIONS_EXCEEDED and res.corrections == []

def test_scanned_pdf_without_ocr_fails_cleanly(tmp_path):             # Review Focus 3
    p = tmp_path / "scan.pdf"
    d = pymupdf.open(); d.new_page(); d.save(p); d.close()
    res = run_invoice(str(p), deps())
    assert res.status == Status.FAILED and "OCR" in res.error and res.ledger is None

def test_pdf_without_line_item_table_fails_cleanly(tmp_path):          # Review Focus 4
    p = tmp_path / "notable.pdf"
    d = pymupdf.open(); page = d.new_page()
    page.insert_text((72, 72), "Invoice #X  Total: $5.00  this page has no tables at all, just prose")
    d.save(p); d.close()
    res = run_invoice(str(p), deps())
    assert res.status == Status.FAILED and "line-item" in res.error
