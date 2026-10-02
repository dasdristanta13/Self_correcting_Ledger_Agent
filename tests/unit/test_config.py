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

def test_from_yaml_reads_utf8(tmp_path):
    p = tmp_path / "u.yaml"
    # U+0141 encodes as 0xC5 0x81; 0x81 is undefined in cp1252, so a locale decode would fail
    p.write_bytes("# Łódź note\nmax_revisions: 4\n".encode("utf-8"))
    assert Config.from_yaml(p).max_revisions == 4
