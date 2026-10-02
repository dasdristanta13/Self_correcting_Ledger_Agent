import pytest

from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps, run_invoice
from ledger_agent.retrieval.hybrid import IndexDisposedError, build_index
from ledger_agent.retrieval.vector import VectorIndex
from ledger_agent.testing.invoices import default_spec, render_invoice
from ledger_agent.testing.ledgers import make_document
from ledger_agent.tracing import ListTraceSink, NullTraceSink, TraceEvent

EMB = HashingEmbedder()


class SpyVector:
    def __init__(self, chunks, embedder):
        self._inner = VectorIndex(chunks, embedder)
        self.disposed = 0

    def scores(self, query):
        return self._inner.scores(query)

    def dispose(self):
        self.disposed += 1


def test_vector_factory_is_used_and_disposed():
    made = []

    def factory(invoice_id, chunks, embedder):
        made.append(SpyVector(chunks, embedder))
        return made[0]

    idx = build_index(make_document(), EMB, vector_factory=factory)
    assert idx.search("INV-001", "total", k=2)
    idx.dispose()
    assert made[0].disposed == 1
    with pytest.raises(IndexDisposedError):
        idx.search("INV-001", "total")


def test_dispose_swallows_backend_errors():
    class Boom(SpyVector):
        def dispose(self):
            raise RuntimeError("chroma down")

    idx = build_index(make_document(), EMB, vector_factory=lambda i, c, e: Boom(c, e))
    idx.dispose()  # must not raise


def test_default_mode_applies_and_explicit_mode_wins():
    idx = build_index(make_document(), EMB, mode="bm25")
    assert idx.default_mode == "bm25"
    assert idx.search("INV-001", "total", k=1)
    assert idx.search("INV-001", "total", k=1, mode="vector")


def test_graph_emits_one_ordered_trace_event_per_node(tmp_path):
    sink = ListTraceSink()
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    deps = Deps(embedder=EMB, proposer=ChunkValueProposer(), trace_sink=sink)
    res = run_invoice(str(pdf), deps, run_id="run-abc")
    assert res.status.value == "RECONCILED"
    assert [e.node for e in sink.events] == [
        "ingest", "extract", "build_index", "build_ledger", "validate", "finalize"]
    assert {e.run_id for e in sink.events} == {"run-abc"}
    assert all(isinstance(e, TraceEvent) and e.latency_ms >= 0 for e in sink.events)
    assert sink.events[-1].status == "RECONCILED"


def test_failing_sink_never_breaks_the_run(tmp_path):
    class Bad:
        def emit(self, event):
            raise RuntimeError("sink down")

    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    deps = Deps(embedder=EMB, proposer=ChunkValueProposer(), trace_sink=Bad())
    assert run_invoice(str(pdf), deps).status.value == "RECONCILED"


def test_null_sink_is_default(tmp_path):
    assert isinstance(Deps(embedder=EMB, proposer=ChunkValueProposer()).trace_sink, NullTraceSink)
