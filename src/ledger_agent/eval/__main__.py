import argparse
from pathlib import Path

from ledger_agent.eval.report import to_csv, to_markdown
from ledger_agent.eval.runner import run_evaluation


def main() -> None:
    p = argparse.ArgumentParser(description="Compare No-RAG, Vector, BM25 and Hybrid reconciliation.")
    p.add_argument("--out", default="eval_report")
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    res = run_evaluation(workdir=out / "pdfs")
    (out / "report.md").write_text(to_markdown(res), encoding="utf-8")
    (out / "results.csv").write_text(to_csv(res), encoding="utf-8")
    print(to_markdown(res))


if __name__ == "__main__":
    main()
