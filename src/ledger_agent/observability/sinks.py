from __future__ import annotations

import json
import logging

from ledger_agent.storage.base import JobStore
from ledger_agent.tracing import TraceEvent

_log = logging.getLogger("ledger_agent.trace")


class JsonLogSink:
    def __init__(self, logger: logging.Logger | None = None):
        self._log = logger or _log

    def emit(self, event: TraceEvent) -> None:
        self._log.info(json.dumps(event.model_dump(), default=str, sort_keys=True))


class StoreTraceSink:
    def __init__(self, store: JobStore, job_id: str):
        self._store, self._job_id = store, job_id

    def emit(self, event: TraceEvent) -> None:
        # round-trip through JSON so stored events are plain JSON types
        self._store.append_events(self._job_id, [json.loads(json.dumps(event.model_dump(), default=str))])


class CompositeSink:
    def __init__(self, *sinks):
        self._sinks = sinks

    def emit(self, event: TraceEvent) -> None:
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception:
                logging.getLogger(__name__).exception("trace sink %s failed", type(sink).__name__)


def configure_json_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    trace = logging.getLogger("ledger_agent.trace")
    trace.handlers = [handler]
    trace.setLevel(level)
    trace.propagate = False
