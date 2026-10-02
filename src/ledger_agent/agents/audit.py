import json
import math
from dataclasses import dataclass
from typing import Protocol

from ledger_agent.models import Chunk, Discrepancy, Evidence, Ledger, Provenance, ScoredChunk
from ledger_agent.money import parse_money
from ledger_agent.paths import PathRef, parse_path
from ledger_agent.protocols import LLMClient
from ledger_agent.retrieval.hybrid import InvoiceIndex

_SCALAR_TYPES = ["totals", "tax", "discount", "shipping"]


class EvidenceProposer(Protocol):
    def propose(self, discrepancy: Discrepancy, chunks: list[ScoredChunk]) -> list[Evidence]: ...


@dataclass
class AuditCandidates:
    discrepancy: Discrepancy
    query: str
    retrieved: list[ScoredChunk]
    evidence: list[Evidence]


def _attr(ref: PathRef) -> str:
    return ref.attr if ref.kind == "item" else "amount"


def _targets(chunk: Chunk, ref: PathRef) -> bool:
    if ref.kind == "item":
        return chunk.chunk_type == "line_item" and chunk.item_id == ref.id
    if ref.kind == "tax":
        return ref.attr == "amount" and chunk.chunk_type == "tax" and chunk.item_id == ref.id
    if ref.attr == "tax":           # scalar tax is derived from tax lines; never evidence
        return False
    return chunk.chunk_type != "line_item" and chunk.field == ref.attr


def build_query(discrepancy: Discrepancy, ledger: Ledger) -> tuple[str, list[str] | None]:
    ref = parse_path(discrepancy.field)
    if ref.kind == "item":
        item = next((i for i in ledger.items if i.id == ref.id), None)
        desc = item.description if item else ""
        return f"{ref.id} {desc} quantity unit price amount", ["line_item"]
    if ref.kind == "tax":
        return f"{ref.id} tax rate amount", ["tax"]
    return f"{ref.attr} " + " ".join(discrepancy.related_fields), _SCALAR_TYPES


def retrieve_and_propose(discrepancy, ledger, index: InvoiceIndex, proposer, k: int) -> AuditCandidates:
    query, types = build_query(discrepancy, ledger)
    k = max(k, len(discrepancy.related_fields) + 3)
    retrieved = index.search(index.invoice_id, query, k=k, chunk_types=types)
    return AuditCandidates(discrepancy, query, retrieved, proposer.propose(discrepancy, retrieved))


class ChunkValueProposer:
    def propose(self, discrepancy: Discrepancy, chunks: list[ScoredChunk]) -> list[Evidence]:
        out: list[Evidence] = []
        for path in discrepancy.related_fields:
            ref = parse_path(path)
            for rank, sc in enumerate(chunks):
                ch = sc.chunk
                if not _targets(ch, ref):
                    continue
                raw = ch.values.get(_attr(ref))
                try:
                    value = parse_money(raw) if raw is not None else None
                except ValueError:
                    value = None
                if value is not None:
                    conf = 0.97 if rank == 0 else 0.92 if rank < 3 else 0.80
                    out.append(Evidence(field=path, value=value, confidence=conf,
                                        chunk_id=ch.chunk_id, quote=ch.text,
                                        source=ch.provenance.model_copy(update={"column": _attr(ref)})))
                break
        return out


class LLMProposer:
    _SYSTEM = ("You are auditing one invoice. Using ONLY the provided chunks, report the printed "
               "value for each requested field. Return JSON {evidence:[{field,value,chunk_id,confidence}]}.")

    def __init__(self, llm: LLMClient):
        self._llm = llm

    def propose(self, discrepancy: Discrepancy, chunks: list[ScoredChunk]) -> list[Evidence]:
        prompt = json.dumps({
            "discrepancy": discrepancy.model_dump(mode="json"),
            "chunks": [{"chunk_id": s.chunk.chunk_id, "text": s.chunk.text} for s in chunks],
        })
        resp = self._llm.complete_json(self._SYSTEM, prompt, {"type": "object"})
        by_id = {s.chunk.chunk_id: s.chunk for s in chunks}
        out: list[Evidence] = []
        for item in resp.get("evidence", []):
            ch = by_id.get(item.get("chunk_id"))
            if ch is None:
                continue
            try:
                value = parse_money(str(item["value"]))
                conf = float(item["confidence"])
                if not (math.isfinite(conf) and 0 <= conf <= 1):
                    continue
                path = item["field"]
                attr = _attr(parse_path(path))
            except (KeyError, ValueError, TypeError):
                continue
            out.append(Evidence(field=path, value=value, confidence=conf, chunk_id=ch.chunk_id,
                                quote=ch.text, source=ch.provenance.model_copy(update={"column": attr})))
        return out


def _recorded_source(ledger: Ledger, ref: PathRef) -> Provenance | None:
    if ref.kind == "item":
        item = next((i for i in ledger.items if i.id == ref.id), None)
        return item.source.get(ref.attr) if item else None
    if ref.kind == "tax":
        line = next((t for t in ledger.tax_lines if t.id == ref.id), None)
        return line.source.get("amount") if line else None
    return ledger.sources.get(ref.attr)


def _matches_ledger_source(ledger: Ledger, ref: PathRef, chunk: Chunk) -> bool:
    rec = _recorded_source(ledger, ref)
    if rec is None:                 # no provenance recorded (hand-built ledger): nothing to tie to
        return True
    if ref.kind == "item":
        return (rec.page, rec.table_id, rec.row) == (chunk.page, chunk.table_id, chunk.row_id)
    return (rec.page, rec.block_id) == (chunk.page, chunk.provenance.block_id)


def verify_evidence(ev: Evidence, discrepancy: Discrepancy, chunks: list[ScoredChunk],
                    invoice_id: str, threshold: float, ledger: Ledger | None = None) -> str | None:
    if ev.field not in discrepancy.related_fields:
        return "field not related to discrepancy"
    chunk = next((s.chunk for s in chunks if s.chunk.chunk_id == ev.chunk_id), None)
    if chunk is None:
        return "evidence chunk was not retrieved"
    if not (chunk.invoice_id == invoice_id == ev.source.document_id):
        return "evidence is from a different invoice"
    if (ev.source.page, ev.source.table_id, ev.source.row) != (chunk.page, chunk.table_id, chunk.row_id):
        return "source location does not match chunk"
    ref = parse_path(ev.field)
    if not _targets(chunk, ref):
        return "chunk does not describe the target field"
    raw = chunk.values.get(_attr(ref))
    try:
        if raw is None or parse_money(raw) != ev.value:
            return "value does not match chunk"
    except ValueError:
        return "value does not match chunk"
    if not (math.isfinite(ev.confidence) and 0 <= ev.confidence <= 1 and ev.confidence >= threshold):
        return f"confidence {ev.confidence:.2f} below threshold {threshold:.2f}"
    if ledger is not None and not _matches_ledger_source(ledger, ref, chunk):
        return "source location differs from the ledger's recorded source"
    return None


def verify_candidates(cand: AuditCandidates, invoice_id: str, threshold: float,
                      ledger: Ledger | None = None):
    ok: list[Evidence] = []
    rejected: list[tuple[Evidence, str]] = []
    for ev in cand.evidence:
        reason = verify_evidence(ev, cand.discrepancy, cand.retrieved, invoice_id, threshold, ledger)
        (rejected.append((ev, reason)) if reason else ok.append(ev))
    return ok, rejected
