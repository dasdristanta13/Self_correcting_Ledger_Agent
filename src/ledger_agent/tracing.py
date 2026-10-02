from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Protocol

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)


class TraceEvent(BaseModel):
    run_id: str
    invoice_id: str | None = None
    node: str
    revision: int = 0
    started_at: str
    latency_ms: float
    status: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class TraceSink(Protocol):
    def emit(self, event: TraceEvent) -> None: ...


class NullTraceSink:
    def emit(self, event: TraceEvent) -> None:
        return None


class ListTraceSink:
    def __init__(self):
        self.events: list[TraceEvent] = []

    def emit(self, event: TraceEvent) -> None:
        self.events.append(event)


def summarize(update: dict, state: dict) -> dict:
    d: dict[str, Any] = {}
    if "route" in update:
        d["route"] = update["route"]
    if update.get("error"):
        d["error"] = update["error"]
    if "discrepancies" in update:
        d["discrepancies"] = [x.field for x in update["discrepancies"]]
    if "audit_candidates" in update:
        d["queries"] = [c.query for c in update["audit_candidates"]]
    if "audit_evidence" in update:
        d["evidence_count"] = len(update["audit_evidence"])
    if update.get("retrieval_events"):
        d["last_retrieval"] = update["retrieval_events"][-1]
    if "proposed_corrections" in update:
        d["corrections"] = [p.path for p in update["proposed_corrections"]]
    return d


def traced(node_name: str, fn: Callable, sink: TraceSink) -> Callable:
    """Wrap a graph node so it emits one TraceEvent; sink failures never affect the run."""

    @wraps(fn)
    def wrapper(state):
        started = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        t0 = time.perf_counter()
        update = fn(state)
        try:
            status = update.get("status", state.get("status"))
            sink.emit(TraceEvent(
                run_id=state.get("run_id", ""), invoice_id=update.get("invoice_id", state.get("invoice_id")),
                node=node_name, revision=update.get("revision", state.get("revision", 0)),
                started_at=started, latency_ms=round((time.perf_counter() - t0) * 1000, 3),
                status=getattr(status, "value", status), detail=summarize(update, state)))
        except Exception:  # tracing must never break reconciliation
            _log.exception("trace sink failed for node %s", node_name)
        return update

    return wrapper
