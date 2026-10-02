from decimal import Decimal as D
import pytest
from ledger_agent.agents.reconciliation import PatchRejected, apply_patches, check_patch, propose_patches
from ledger_agent.models import Evidence, Patch, Provenance
from ledger_agent.paths import get_field, set_field
from ledger_agent.testing.ledgers import make_ledger

def ev(field="items[line_01].amount", value="1014.00", conf=0.97):
    return Evidence(field=field, value=D(value), confidence=conf, chunk_id="c1",
                    source=Provenance(document_id="INV-001", page=1, table_id="table_01", row=1))

def bad_ledger():
    return set_field(make_ledger(), "items[line_01].amount", D("1040.00"))

def test_propose_skips_equal_values_and_unknown_paths():
    led = make_ledger()
    assert propose_patches(led, [ev()]) == []
    assert propose_patches(bad_ledger(), [ev(field="items[line_99].amount")]) == []

def test_propose_dedupes_by_highest_confidence():
    ps = propose_patches(bad_ledger(), [ev(conf=0.91), ev(conf=0.99)])
    assert len(ps) == 1 and ps[0].confidence == 0.99
    assert (ps[0].old_value, ps[0].new_value, ps[0].source_table, ps[0].source_row) == (D("1040.00"), D("1014.00"), "table_01", 1)

def test_apply_records_revision_and_does_not_mutate_input():
    led = bad_ledger()
    new, records = apply_patches(led, propose_patches(led, [ev()]), revision=1, threshold=0.90)
    assert get_field(new, "items[line_01].amount") == D("1014.00")
    assert get_field(led, "items[line_01].amount") == D("1040.00")
    r = records[0]
    assert (r.revision, r.field, r.old_value, r.new_value, r.source_page, r.source_row) == \
           (1, "items[line_01].amount", D("1040.00"), D("1014.00"), 1, 1)

def patch(**kw):
    base = dict(path="items[line_01].amount", old_value=D("1040.00"), new_value=D("1014.00"),
                reason="r", source_page=1, source_table="table_01", source_row=1, confidence=0.97)
    base.update(kw)
    return Patch(**base)

@pytest.mark.parametrize("kw", [
    {"confidence": 0.5}, {"old_value": D("1.00")}, {"source_page": None}, {"path": "items[line_99].amount"},
])
def test_safety_checks_reject(kw):
    with pytest.raises(PatchRejected):
        check_patch(bad_ledger(), patch(**kw), 0.90)

def test_check_passes_for_valid_patch():
    check_patch(bad_ledger(), patch(), 0.90)

def test_gate_rejects_nan_confidence_and_nan_threshold():
    p = Patch.model_construct(**{**patch().model_dump(), "confidence": float("nan")})
    with pytest.raises(PatchRejected, match="confidence"):
        check_patch(bad_ledger(), p, 0.90)
    with pytest.raises(PatchRejected, match="confidence"):
        check_patch(bad_ledger(), patch(), float("nan"))

def test_gate_rejects_non_finite_new_value():
    p = Patch.model_construct(**{**patch().model_dump(), "new_value": D("NaN")})
    with pytest.raises(PatchRejected):
        check_patch(bad_ledger(), p, 0.90)

def test_patch_model_rejects_nan_confidence():
    with pytest.raises(Exception):
        patch(confidence=float("nan"))
