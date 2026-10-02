from __future__ import annotations

import dataclasses
import logging
import uuid
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from ledger_agent.agents.audit import EvidenceProposer, retrieve_and_propose, verify_candidates
from ledger_agent.agents.guards import decide_after_validate, signatures
from ledger_agent.agents.reconciliation import PatchRejected, apply_patches, propose_patches
from ledger_agent.config import Config
from ledger_agent.extraction.canonical import build_document
from ledger_agent.extraction.ledger import build_ledger, resolve_column_overrides
from ledger_agent.ingestion.pdf import ingest_pdf
from ledger_agent.ingestion.tables import PyMuPDFTableExtractor
from ledger_agent.models import AuditRecord, Document, Evidence, Ledger
from ledger_agent.protocols import Embedder, LLMClient, OcrBackend, TableExtractor
from ledger_agent.retrieval.hybrid import build_index
from ledger_agent.state import LedgerState, Status
from ledger_agent.tracing import NullTraceSink, TraceSink, traced
from ledger_agent.validation.arithmetic import validate


@dataclass
class Deps:
    embedder: Embedder
    proposer: EvidenceProposer
    config: Config = field(default_factory=Config)
    llm: LLMClient | None = None
    ocr: OcrBackend | None = None
    table_extractor: TableExtractor = field(default_factory=PyMuPDFTableExtractor)
    ledger_builder: Callable[[Document], Ledger] = build_ledger
    validator: Callable = validate
    vector_factory: Callable | None = None
    trace_sink: TraceSink = field(default_factory=NullTraceSink)
    retrieval_mode: str = "hybrid"


class ReconciliationResult(BaseModel):
    invoice_id: str
    status: Status
    iterations: int
    ledger: Ledger | None
    original_ledger: Ledger | None
    corrections: list[AuditRecord]
    evidence: list[Evidence]
    error: str | None = None


def _guarded(name: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(state):
            try:
                return fn(state)
            except Exception as exc:  # any node failure ends the run cleanly
                return {"status": Status.FAILED, "error": f"{name}: {exc}", "route": "failed"}
        return wrapper
    return deco


def build_graph(deps: Deps):
    cfg = deps.config

    @_guarded("ingest")
    def ingest(state):
        pages = ingest_pdf(state["pdf_path"], min_chars=cfg.ocr_min_chars, ocr=deps.ocr)
        missing = [p.page_number for p in pages if p.needs_ocr]
        total_chars = sum(len(p.text.strip()) for p in pages)
        # A near-empty page in an otherwise native document (blank last page, a short
        # thank-you page) is ignored; only a document that as a whole lacks text needs OCR.
        if missing and total_chars < cfg.ocr_min_chars:
            return {"status": Status.FAILED, "route": "failed",
                    "error": f"ingest: pages {missing} need OCR but no OCR backend is configured"}
        return {"pages": pages, "status": Status.INGESTED, "route": "extract"}

    @_guarded("extract")
    def extract(state):
        doc_id = state.get("invoice_id") or Path(state["pdf_path"]).stem
        tables = deps.table_extractor.extract(state["pdf_path"])
        doc = build_document(doc_id, state["pages"], tables)
        doc.column_overrides = resolve_column_overrides(doc, deps.llm)
        return {"invoice_id": doc_id, "document": doc, "status": Status.EXTRACTED, "route": "build_index"}

    @_guarded("build_index")
    def build_index_node(state):
        return {"retrieval_index": build_index(state["document"], deps.embedder, deps.vector_factory,
                                           deps.retrieval_mode),
                "status": Status.INDEXED, "route": "build_ledger"}

    @_guarded("build_ledger")
    def build_ledger_node(state):
        ledger = deps.ledger_builder(state["document"])
        return {"ledger": ledger, "original_ledger": ledger, "revision": 0,
                "last_signatures": None, "status": Status.VALIDATING, "route": "validate"}

    @_guarded("validate")
    def validate_node(state):
        ds = deps.validator(state["ledger"], cfg.validation)
        outcome = decide_after_validate(ds, state.get("last_signatures"),
                                        state["revision"], state["max_revisions"])
        update: dict[str, Any] = {"discrepancies": ds, "last_signatures": signatures(ds)}
        if outcome == "finalize":
            update |= {"route": "finalize"}
        elif outcome == "audit":
            update |= {"route": "audit", "status": Status.AUDITING}
        else:
            status = Status.NO_PROGRESS if outcome == "no_progress" else Status.MAX_REVISIONS_EXCEEDED
            update |= {"route": "failed", "status": status}
        return update

    @_guarded("audit")
    def audit(state):
        cands = [retrieve_and_propose(d, state["ledger"], state["retrieval_index"],
                                      deps.proposer, cfg.top_k) for d in state["discrepancies"]]
        return {"audit_candidates": cands, "route": "verify_evidence"}

    @_guarded("verify_evidence")
    def verify_evidence_node(state):
        verified: list[Evidence] = []
        events = list(state.get("retrieval_events", []))
        for cand in state["audit_candidates"]:
            ok, rejected = verify_candidates(cand, state["invoice_id"], cfg.confidence_threshold,
                                          state["ledger"])
            verified += ok
            events.append({
                "revision": state["revision"], "field": cand.discrepancy.field, "query": cand.query,
                "retrieved": [(s.chunk.chunk_id, round(s.score, 6)) for s in cand.retrieved],
                "rejected": [(e.field, why) for e, why in rejected],
            })
        update = {"audit_evidence": verified, "retrieval_events": events}
        if not verified:
            return update | {"status": Status.INSUFFICIENT_EVIDENCE, "route": "failed"}
        return update | {"route": "reconcile"}

    @_guarded("reconcile")
    def reconcile(state):
        patches = propose_patches(state["ledger"], state["audit_evidence"])
        if not patches:
            return {"status": Status.UNRESOLVED, "route": "failed",
                    "error": "evidence agrees with the extracted values; nothing to correct"}
        try:
            ledger, records = apply_patches(state["ledger"], patches, state["revision"] + 1,
                                            cfg.confidence_threshold)
        except PatchRejected as exc:
            return {"status": Status.UNRESOLVED, "route": "failed", "error": f"patch rejected: {exc}"}
        return {"ledger": ledger, "revision": state["revision"] + 1, "proposed_corrections": patches,
                "audit_trail": list(state.get("audit_trail", [])) + records,
                "status": Status.RECONCILING, "route": "validate"}

    def _dispose(state):
        idx = state.get("retrieval_index")
        if idx is not None:
            try:
                idx.dispose()
            except Exception:   # cleanup failure must never hide the run's result
                pass
        return {"retrieval_index": None}

    @_guarded("finalize")
    def finalize(state):
        return _dispose(state) | {"status": Status.RECONCILED}

    @_guarded("failed")
    def failed(state):
        return _dispose(state)

    g = StateGraph(LedgerState)
    for name, fn in [("ingest", ingest), ("extract", extract), ("build_index", build_index_node),
                     ("build_ledger", build_ledger_node), ("validate", validate_node),
                     ("audit", audit), ("verify_evidence", verify_evidence_node),
                     ("reconcile", reconcile), ("finalize", finalize), ("failed", failed)]:
        g.add_node(name, traced(name, fn, deps.trace_sink))
    g.add_edge(START, "ingest")

    def route(src: str, targets: list[str]):
        g.add_conditional_edges(src, lambda s: s["route"], {t: t for t in targets})

    route("ingest", ["extract", "failed"])
    route("extract", ["build_index", "failed"])
    route("build_index", ["build_ledger", "failed"])
    route("build_ledger", ["validate", "failed"])
    route("validate", ["audit", "finalize", "failed"])
    route("audit", ["verify_evidence", "failed"])
    route("verify_evidence", ["reconcile", "failed"])
    route("reconcile", ["validate", "failed"])
    g.add_edge("finalize", END)
    g.add_edge("failed", END)
    return g.compile()


def run_invoice(pdf_path: str, deps: Deps, invoice_id: str | None = None,
               run_id: str | None = None) -> ReconciliationResult:
    initial: LedgerState = {"pdf_path": str(pdf_path), "max_revisions": deps.config.max_revisions,
                            "audit_trail": [], "audit_evidence": [], "retrieval_events": [],
                            "revision": 0, "run_id": run_id or uuid.uuid4().hex[:12]}
    if invoice_id:
        initial["invoice_id"] = invoice_id
    limit = 4 * deps.config.max_revisions + 30
    built: list = []
    inner_factory = deps.vector_factory
    if inner_factory is not None:
        def recording_factory(*a, **kw):
            idx = inner_factory(*a, **kw)
            built.append(idx)
            return idx
        deps = dataclasses.replace(deps, vector_factory=recording_factory)
    try:
        final = build_graph(deps).invoke(initial, {"recursion_limit": limit})
    except GraphRecursionError as exc:
        return ReconciliationResult(
            invoice_id=invoice_id or Path(pdf_path).stem, status=Status.MAX_REVISIONS_EXCEEDED,
            iterations=0, ledger=None, original_ledger=None, corrections=[], evidence=[],
            error=f"graph recursion limit ({limit}) exceeded: {exc}")
    finally:
        for idx in built:                       # idempotent; guarantees no leaked index on an aborted run
            try:
                idx.dispose()
            except Exception:
                logging.getLogger(__name__).exception("index dispose failed")
    return ReconciliationResult(
        invoice_id=final.get("invoice_id", Path(pdf_path).stem), status=final["status"],
        iterations=final.get("revision", 0), ledger=final.get("ledger"),
        original_ledger=final.get("original_ledger"), corrections=final.get("audit_trail", []),
        evidence=final.get("audit_evidence", []), error=final.get("error"))
