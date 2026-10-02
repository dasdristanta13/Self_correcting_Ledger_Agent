from decimal import Decimal as D
from pathlib import Path

import pytest

from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps, run_invoice
from ledger_agent.state import Status
from ledger_agent.testing.corrupt import corrupting_builder
from ledger_agent.testing.invoices import InvoiceSpec, ItemSpec, render_invoice

FIXTURES = sorted((Path(__file__).parents[1] / "fixtures" / "net_worth").glob("invoice_*.pdf"))
EXPECTED_TOTALS = {"invoice_51109322": D("277163.70"), "invoice_51109323": D("671136.40"),
                   "invoice_51109324": D("1152597.60"), "invoice_51109325": D("2397277.30"),
                   "invoice_51109326": D("131725.00")}


def _deps(**kw):
    return Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer(), **kw)


def test_fixtures_present():
    assert len(FIXTURES) == 5


@pytest.mark.parametrize("pdf", FIXTURES, ids=lambda p: p.stem)
def test_real_invoice_reconciles_without_corrections(pdf):
    r = run_invoice(str(pdf), _deps())
    assert r.status == Status.RECONCILED and r.error is None and r.corrections == []
    assert r.ledger.total == EXPECTED_TOTALS[pdf.stem] and r.ledger.currency == "INR"


def _spec():
    return InvoiceSpec("NW-1", [ItemSpec("Phone", D("3"), D("83989.00")),
                                ItemSpec("Case", D("2"), D("499.00"))], currency="INR", layout="net_worth")


def test_generated_net_worth_invoice_reconciles(tmp_path):
    r = run_invoice(str(render_invoice(_spec(), tmp_path / "nw.pdf")), _deps())
    assert r.status == Status.RECONCILED


def test_wrong_summary_total_is_self_corrected_from_the_summary_cell(tmp_path):
    pdf = render_invoice(_spec(), tmp_path / "nw.pdf")
    clean = run_invoice(str(pdf), _deps()).ledger.total
    r = run_invoice(str(pdf), _deps(ledger_builder=corrupting_builder("total", D("1.00"))))
    assert r.status == Status.RECONCILED and r.ledger.total == clean
    assert r.corrections and r.evidence[0].source.table_id is not None
