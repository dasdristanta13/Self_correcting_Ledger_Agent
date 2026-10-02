from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps, run_invoice
from ledger_agent.state import Status
from ledger_agent.testing.invoices import default_spec, render_invoice

def test_clean_invoice_reconciles_without_revisions(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer()))
    assert res.status == Status.RECONCILED and res.iterations == 0 and res.corrections == []
    assert res.invoice_id == "INV-001" and res.ledger.total > 0
