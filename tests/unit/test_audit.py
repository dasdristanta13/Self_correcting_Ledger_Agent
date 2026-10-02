from decimal import Decimal as D
from ledger_agent.agents.audit import (ChunkValueProposer, LLMProposer, build_query,
                                       retrieve_and_propose, verify_candidates, verify_evidence)
from ledger_agent.fakes import FakeLLM, HashingEmbedder
from ledger_agent.paths import set_field
from ledger_agent.retrieval.hybrid import build_index
from ledger_agent.testing.ledgers import make_document, make_ledger
from ledger_agent.validation.arithmetic import validate
from ledger_agent.config import ValidationRules

EMB = HashingEmbedder()

def setup(items=None):
    doc = make_document(items=items)
    ledger = set_field(make_ledger(items=items), "items[line_01].amount", D("1040.00"))
    d = next(x for x in validate(ledger, ValidationRules()) if x.field == "items[line_01].amount")
    return doc, ledger, d, build_index(doc, EMB)

def test_build_query_targets_the_item():
    _, ledger, d, _ = setup()
    q, types = build_query(d, ledger)
    assert "line_01" in q and "Industrial Filter" in q and types == ["line_item"]

def test_line_discrepancy_yields_verified_evidence_with_source_row():
    _, ledger, d, idx = setup()
    cand = retrieve_and_propose(d, ledger, idx, ChunkValueProposer(), k=5)
    ok, rejected = verify_candidates(cand, "INV-001", 0.90)
    by_field = {e.field: e for e in ok}
    amt = by_field["items[line_01].amount"]
    assert amt.value == D("1014.00") and amt.confidence >= 0.97
    assert (amt.source.page, amt.source.table_id, amt.source.row) == (1, "table_01", 1)
    assert not rejected

def test_total_discrepancy_never_proposes_derived_tax_scalar():
    doc = make_document(tax_rates=(D("0.05"), D("0.07")))
    ledger = make_ledger(tax_rates=(D("0.05"), D("0.07"))).model_copy(update={"total": D("1.00")})
    d = validate(ledger, ValidationRules())[0]
    idx = build_index(doc, EMB)
    cand = retrieve_and_propose(d, ledger, idx, ChunkValueProposer(), k=5)
    assert "tax" not in {e.field for e in cand.evidence}
    assert "total" in {e.field for e in cand.evidence}

def test_verifier_rejects_low_confidence_foreign_and_tampered_evidence():
    _, ledger, d, idx = setup()
    cand = retrieve_and_propose(d, ledger, idx, ChunkValueProposer(), k=5)
    ev = next(e for e in cand.evidence if e.field == "items[line_01].amount")
    chunks = cand.retrieved
    assert verify_evidence(ev, d, chunks, "INV-001", 0.90) is None
    assert "confidence" in verify_evidence(ev.model_copy(update={"confidence": 0.5}), d, chunks, "INV-001", 0.90)
    assert "invoice" in verify_evidence(ev, d, chunks, "INV-OTHER", 0.90)
    assert "value" in verify_evidence(ev.model_copy(update={"value": D("999.00")}), d, chunks, "INV-001", 0.90)
    assert "related" in verify_evidence(ev.model_copy(update={"field": "total"}), d, chunks, "INV-001", 0.90)
    assert "retrieved" in verify_evidence(ev.model_copy(update={"chunk_id": "nope"}), d, chunks, "INV-001", 0.90)
    src = ev.source.model_copy(update={"row": 2})
    assert "source" in verify_evidence(ev.model_copy(update={"source": src}), d, chunks, "INV-001", 0.90)

def test_llm_proposer_cannot_invent_provenance_or_values():
    _, ledger, d, idx = setup()
    cand = retrieve_and_propose(d, ledger, idx, ChunkValueProposer(), k=5)
    real = next(s.chunk for s in cand.retrieved if s.chunk.item_id == "line_01")
    llm = FakeLLM([{"evidence": [
        {"field": "items[line_01].amount", "value": "1014.00", "chunk_id": real.chunk_id, "confidence": 0.95},
        {"field": "items[line_01].amount", "value": "1014.00", "chunk_id": "ghost", "confidence": 0.99},
        {"field": "items[line_01].amount", "value": "oops", "chunk_id": real.chunk_id, "confidence": 0.99},
    ]}])
    evs = LLMProposer(llm).propose(d, cand.retrieved)
    assert len(evs) == 1 and evs[0].source.row == 1 and evs[0].value == D("1014.00")
    ok, _ = verify_candidates(type(cand)(d, cand.query, cand.retrieved, evs), "INV-001", 0.90)
    assert len(ok) == 1
