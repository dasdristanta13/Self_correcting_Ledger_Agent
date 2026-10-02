from decimal import Decimal as D

import pytest

from ledger_agent.config import ValidationRules
from ledger_agent.eval.metrics import Outcome, flatten, variant_metrics
from ledger_agent.eval.variants import run_no_rag
from ledger_agent.paths import set_field
from ledger_agent.testing.ledgers import make_ledger
from ledger_agent.validation.arithmetic import validate


def test_flatten_covers_items_taxes_and_scalars():
    flat = flatten(make_ledger())
    assert flat["items[line_01].amount"] == D("1014.00")
    assert flat["tax_lines[tax_01].amount"] == D("104.40") and flat["total"] == D("1148.40")


def outcome(kind, orig, truth, final, corrections, status="RECONCILED", it=1):
    return Outcome(case="c", kind=kind, status=status, original=orig, truth=truth, final=final,
                   corrections=corrections, iterations=it, latency_ms=10.0)


def test_metrics_correct_and_false_correction():
    truth = make_ledger()
    bad = set_field(truth, "items[line_01].amount", D("1040.00"))
    wrong = set_field(truth, "items[line_01].amount", D("999.00"))
    ok = outcome("extraction_error", bad, truth, truth, 1)
    false = outcome("extraction_error", bad, truth, wrong, 1, status="MAX_REVISIONS_EXCEEDED", it=3)
    doc_err_fixed = outcome("document_error", bad, bad, truth, 1)
    abstained = outcome("document_error", bad, bad, bad, 0, status="UNRESOLVED", it=0)
    m = variant_metrics([ok, false, doc_err_fixed, abstained])
    assert m["n"] == 4 and m["correct_rate"] == 0.5          # ok + abstained
    assert m["false_correction_rate"] == 0.5                  # wrong value + fixed-the-document
    assert m["reconciled_rate"] == 0.5 and m["max_iterations"] == 3


def test_no_rag_trusts_arithmetic_even_when_the_invoice_is_right():
    # quantity was corrupted: arithmetic-repair rewrites the AMOUNT to fit the wrong quantity
    corrupted = set_field(make_ledger(), "items[line_01].quantity", D("13"))
    final, revs, status = run_no_rag(corrupted, ValidationRules(), max_revisions=3)
    assert final.items[0].quantity == D("13") and final.items[0].amount == D("1098.50")
    assert final.items[0].amount != make_ledger().items[0].amount
    assert revs >= 1


def test_no_rag_leaves_clean_ledgers_alone():
    final, revs, status = run_no_rag(make_ledger(), ValidationRules(), max_revisions=3)
    assert revs == 0 and status == "RECONCILED"
    assert validate(final, ValidationRules()) == []
