from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from ledger_agent.agents.audit import ChunkValueProposer, build_query
from ledger_agent.config import Config
from ledger_agent.eval.dataset import Case, default_cases
from ledger_agent.eval.metrics import Outcome, variant_metrics
from ledger_agent.eval.variants import MODES, run_no_rag
from ledger_agent.extraction.canonical import build_document
from ledger_agent.extraction.ledger import build_ledger
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps, run_invoice
from ledger_agent.ingestion.pdf import ingest_pdf
from ledger_agent.ingestion.tables import extract_tables
from ledger_agent.paths import parse_path, set_field
from ledger_agent.retrieval.hybrid import build_index
from ledger_agent.testing.corrupt import corrupting_builder
from ledger_agent.testing.invoices import render_invoice
from ledger_agent.validation.arithmetic import validate

EMB = HashingEmbedder()


@dataclass
class EvalResult:
    metrics: dict[str, dict]
    retrieval: dict[str, dict]
    outcomes: dict[str, list[Outcome]]


def _document(pdf: Path, name: str):
    return build_document(name, ingest_pdf(pdf), extract_tables(pdf))


def retrieval_metrics(rendered: list[tuple[Case, Path]], mode: str, ks=(1, 3)) -> dict:
    ranks: list[int] = []
    for case, pdf in rendered:
        if case.corrupt is None or parse_path(case.corrupt[0]).kind != "item":
            continue
        doc = _document(pdf, case.spec.invoice_id)
        ledger = set_field(build_ledger(doc), case.corrupt[0], case.corrupt[1])
        target = parse_path(case.corrupt[0]).id
        d = next((x for x in validate(ledger, Config().validation) if x.field.startswith("items[")), None)
        if d is None:
            continue
        query, types = build_query(d, ledger)
        index = build_index(doc, EMB, mode=mode)
        found = index.search(index.invoice_id, query, k=1000, mode=mode, chunk_types=types)
        index.dispose()
        rank = next((i for i, s in enumerate(found) if s.chunk.item_id == target), len(found))
        ranks.append(rank)
    n = len(ranks)
    out = {"n": n, "mrr": sum(1.0 / (r + 1) for r in ranks) / n if n else 0.0}
    for k in ks:
        out[f"recall@{k}"] = sum(1 for r in ranks if r < k) / n if n else 0.0
    return out


def run_evaluation(cases: list[Case] | None = None, workdir: Path | None = None) -> EvalResult:
    cases = cases or default_cases()
    work = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="ledger-eval-"))
    work.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    rendered = [(c, render_invoice(c.spec, work / f"{c.spec.invoice_id}.pdf")) for c in cases]
    outcomes: dict[str, list[Outcome]] = {v: [] for v in ["no_rag", *MODES]}

    for case, pdf in rendered:
        doc = _document(pdf, case.spec.invoice_id)
        clean = build_ledger(doc)
        start = (set_field(set_field(clean, case.corrupt[0], case.corrupt[1]), *case.also)
                 if case.corrupt and case.also else
                 set_field(clean, *case.corrupt) if case.corrupt else clean)
        truth = clean if case.kind != "document_error" else start    # a document error has nothing to restore
        builder = corrupting_builder(*case.corrupt, also=case.also) if case.corrupt else build_ledger

        t0 = time.perf_counter()
        final, revs, status = run_no_rag(start, cfg.validation, cfg.max_revisions)
        outcomes["no_rag"].append(Outcome(case.name, case.kind, status, start, truth, final, revs, revs,
                                          (time.perf_counter() - t0) * 1000))
        for variant, mode in MODES.items():
            deps = Deps(embedder=EMB, proposer=ChunkValueProposer(), retrieval_mode=mode, ledger_builder=builder)
            t0 = time.perf_counter()
            res = run_invoice(str(pdf), deps, invoice_id=case.spec.invoice_id)
            outcomes[variant].append(Outcome(case.name, case.kind, res.status.value, start, truth, res.ledger,
                                             len(res.corrections), res.iterations, (time.perf_counter() - t0) * 1000))

    return EvalResult(
        metrics={v: variant_metrics(o) for v, o in outcomes.items()},
        retrieval={m: retrieval_metrics(rendered, m) for m in MODES},
        outcomes=outcomes)
