import io
import json
import logging

from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps, run_invoice
from ledger_agent.observability.sinks import (
    CompositeSink,
    JsonLogSink,
    StoreTraceSink,
    configure_json_logging,
)
from ledger_agent.storage.base import Job
from ledger_agent.storage.memory import InMemoryJobStore
from ledger_agent.testing.invoices import default_spec, render_invoice
from ledger_agent.tracing import ListTraceSink, TraceEvent


def event(node="ingest"):
    return TraceEvent(run_id="r1", invoice_id="INV-001", node=node, revision=0,
                      started_at="2026-01-01T00:00:00.000+00:00", latency_ms=1.0, status="INGESTED",
                      detail={"route": "extract"})


def test_json_log_sink_writes_one_parseable_line(caplog):
    with caplog.at_level(logging.INFO, logger="ledger_agent.trace"):
        JsonLogSink().emit(event())
    [rec] = [r for r in caplog.records if r.name == "ledger_agent.trace"]
    assert json.loads(rec.getMessage())["node"] == "ingest"


def test_store_sink_appends_json_safe_events():
    store = InMemoryJobStore()
    store.create(Job(job_id="j", filename="a.pdf", created_at="2026-01-01T00:00:00.000+00:00"))
    sink = StoreTraceSink(store, "j")
    sink.emit(event("ingest"))
    sink.emit(event("extract"))
    got = store.get_events("j")
    assert [e["node"] for e in got] == ["ingest", "extract"]
    json.dumps(got)                                   # fully JSON-serialisable


def test_composite_isolates_failing_sinks():
    seen = ListTraceSink()

    class Bad:
        def emit(self, e):
            raise RuntimeError("down")

    CompositeSink(Bad(), seen).emit(event())
    assert len(seen.events) == 1


def test_full_run_is_traced_to_log_and_store(tmp_path, caplog):
    store = InMemoryJobStore()
    store.create(Job(job_id="j", filename="a.pdf", created_at="2026-01-01T00:00:00.000+00:00"))
    sink = CompositeSink(StoreTraceSink(store, "j"), JsonLogSink())
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    with caplog.at_level(logging.INFO, logger="ledger_agent.trace"):
        run_invoice(str(pdf), Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer(), trace_sink=sink),
                    run_id="run-1")
    events = store.get_events("j")
    assert [e["node"] for e in events] == ["ingest", "extract", "build_index", "build_ledger", "validate", "finalize"]
    assert {e["run_id"] for e in events} == {"run-1"}
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.name == "ledger_agent.trace"]
    assert len(lines) == len(events)


def test_configure_json_logging_emits_one_json_line_to_own_handler():
    trace = logging.getLogger("ledger_agent.trace")
    saved = (trace.handlers[:], trace.level, trace.propagate)
    try:
        configure_json_logging("INFO")
        assert trace.propagate is False
        [handler] = trace.handlers
        buf = io.StringIO()
        handler.setStream(buf)
        JsonLogSink().emit(event("extract"))
        lines = buf.getvalue().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["node"] == "extract"
    finally:
        trace.handlers, trace.propagate = saved[0], saved[2]
        trace.setLevel(saved[1])


def test_configure_json_logging_is_idempotent():
    trace = logging.getLogger("ledger_agent.trace")
    saved = (trace.handlers[:], trace.level, trace.propagate)
    try:
        configure_json_logging()
        configure_json_logging()
        assert len(trace.handlers) == 1
    finally:
        trace.handlers, trace.propagate = saved[0], saved[2]
        trace.setLevel(saved[1])
