from __future__ import annotations

import csv
import io

from ledger_agent.eval.runner import EvalResult

COLS = ["n", "correct_rate", "false_correction_rate", "reconciled_rate", "unresolved_rate",
        "mean_iterations", "max_iterations", "mean_latency_ms"]
ORDER = ["no_rag", "vector", "bm25", "hybrid"]


def to_markdown(res: EvalResult) -> str:
    head = "| variant | n | correct | false-correction | reconciled | unresolved | mean iters | max iters | latency ms |"
    lines = [head, "|" + "---|" * 9]
    for v in ORDER:
        m = res.metrics[v]
        lines.append(f"| {v} | {m['n']} | {m['correct_rate']:.0%} | {m['false_correction_rate']:.0%} | "
                     f"{m['reconciled_rate']:.0%} | {m['unresolved_rate']:.0%} | {m['mean_iterations']:.2f} | "
                     f"{m['max_iterations']} | {m['mean_latency_ms']:.1f} |")
    lines += ["", "Retrieval of the source row (line-item cases):", "",
              "| mode | n | recall@1 | recall@3 | MRR |", "|---|---|---|---|---|"]
    for mode in ("vector", "bm25", "hybrid"):
        r = res.retrieval[mode]
        lines.append(f"| {mode} | {r['n']} | {r['recall@1']:.0%} | {r['recall@3']:.0%} | {r['mrr']:.3f} |")
    lines += ["", "`no_rag` is an arithmetic-trust baseline (no LLM, no retrieval): a stand-in for "
                  "'an LLM without retrieval'. Swap a real LLM client in later."]
    return "\n".join(lines)


def to_csv(res: EvalResult) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["variant", *COLS])
    for v in ORDER:
        w.writerow([v, *[res.metrics[v][c] for c in COLS]])
    return buf.getvalue()
