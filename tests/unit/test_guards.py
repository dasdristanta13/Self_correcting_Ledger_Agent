from decimal import Decimal as D
from ledger_agent.agents.guards import decide_after_validate, signatures
from ledger_agent.models import Discrepancy

def disc(obs="1040.00"):
    return Discrepancy(field="items[line_01].amount", expected=D("1014.00"), observed=D(obs),
                       difference=D(obs) - D("1014.00"), rule="line_amount")

def test_no_discrepancies_finalizes():
    assert decide_after_validate([], None, 0, 3) == "finalize"

def test_first_failure_audits():
    assert decide_after_validate([disc()], None, 0, 3) == "audit"

def test_same_signature_is_no_progress():
    assert decide_after_validate([disc()], signatures([disc()]), 1, 3) == "no_progress"

def test_changed_signature_continues_until_revisions_exhausted():
    prev = signatures([disc("1040.00")])
    assert decide_after_validate([disc("1050.00")], prev, 2, 3) == "audit"
    assert decide_after_validate([disc("1050.00")], prev, 3, 3) == "max_revisions"

def test_zero_max_revisions_blocks_correction():
    assert decide_after_validate([disc()], None, 0, 0) == "max_revisions"

def test_no_progress_takes_priority_over_max():
    assert decide_after_validate([disc()], signatures([disc()]), 3, 3) == "no_progress"
