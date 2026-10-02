from decimal import Decimal
from ledger_agent.config import Config

def test_defaults():
    c = Config()
    assert c.max_revisions == 3 and c.confidence_threshold == 0.90
    assert c.validation.tolerance == Decimal("0.01")

def test_from_yaml(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("max_revisions: 5\nvalidation:\n  tolerance: 0.05\n")
    c = Config.from_yaml(p)
    assert c.max_revisions == 5 and c.validation.tolerance == Decimal("0.05")
