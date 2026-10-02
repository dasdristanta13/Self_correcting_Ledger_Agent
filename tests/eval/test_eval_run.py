import csv
import io

from ledger_agent.eval.dataset import default_cases
from ledger_agent.eval.report import to_csv, to_markdown
from ledger_agent.eval.runner import run_evaluation

SMOKE = ["clean", "line_amount", "quantity_error", "document_total"]


def test_dataset_has_the_documented_error_categories():
    names = {c.name for c in default_cases()}
    assert {"clean", "line_amount", "decimal_error", "quantity_error", "unit_price_error", "subtotal",
            "tax", "total", "duplicate_lines", "multi_tax", "discount", "shipping", "two_errors",
            "document_line_amount", "document_total", "document_subtotal"} <= names


def test_run_produces_three_variants_plus_bm25_and_hybrid_is_safest(tmp_path):
    cases = [c for c in default_cases() if c.name in SMOKE]
    res = run_evaluation(cases, workdir=tmp_path)
    assert set(res.metrics) == {"no_rag", "vector", "bm25", "hybrid"}
    h, n = res.metrics["hybrid"], res.metrics["no_rag"]
    assert h["false_correction_rate"] == 0.0
    assert n["false_correction_rate"] > h["false_correction_rate"]
    assert h["correct_rate"] >= n["correct_rate"]
    assert 0.0 <= res.retrieval["hybrid"]["mrr"] <= 1.0


def test_reports_render(tmp_path):
    res = run_evaluation([c for c in default_cases() if c.name in SMOKE[:2]], workdir=tmp_path)
    md = to_markdown(res)
    assert "| variant |" in md and "hybrid" in md and "false-correction" in md.lower()
    rows = list(csv.DictReader(io.StringIO(to_csv(res))))
    assert {r["variant"] for r in rows} == {"no_rag", "vector", "bm25", "hybrid"}


def test_shipping_case_never_yields_a_false_correction_in_any_mode(tmp_path):
    from ledger_agent.eval.variants import MODES

    res = run_evaluation([c for c in default_cases() if c.name == "shipping"], workdir=tmp_path)
    for variant in MODES:
        (o,) = res.outcomes[variant]
        assert o.final == o.truth or o.status in ("UNRESOLVED", "INSUFFICIENT_EVIDENCE"), (variant, o.status)


def test_eval_cli_writes_a_gitignore_into_the_output_dir(tmp_path, monkeypatch):
    import sys

    from ledger_agent.eval import __main__ as cli

    out = tmp_path / "rep"
    monkeypatch.setattr(sys, "argv", ["eval", "--out", str(out)])
    monkeypatch.setattr(cli, "run_evaluation",
                        lambda workdir: run_evaluation([c for c in default_cases() if c.name == "clean"],
                                                       workdir=workdir))
    cli.main()
    assert (out / ".gitignore").read_text().strip() == "*"
    assert (out / "report.md").exists()
