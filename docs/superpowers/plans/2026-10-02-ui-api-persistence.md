# UI, API, Chroma Persistence and Cycle-2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Parallel execution (user instruction, overrides the skill's one-at-a-time default):** Wave 0 runs sequentially; then the six stream tasks (P1, P2, A, F, O1, O2) are dispatched **in one message and run concurrently**, each in its own git worktree and branch (see "Parallel protocol"). Their reviews also run concurrently. Wave I runs after the merge.

**Goal:** Add a drag-and-drop web UI, a FastAPI service, ChromaDB persistence and per-invoice vector backend, tracing, and the No-RAG/Vector/Hybrid evaluation harness on top of the finished core loop.

**Architecture:** Wave 0 adds small seams to the core (vector factory, trace sink, retrieval mode) and freezes the contracts (`JobStore`, OpenAPI, example job). Six independent streams then implement behind those seams with disjoint file ownership. Wave I wires everything (`build_app`), proves it end to end, and checks the UI in a headless browser.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, python-multipart, httpx (tests), chromadb, pydantic v2, pytest; Node 22 / npm, Vite, React 18, TypeScript, Vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-10-02-ui-api-persistence-design.md` (builds on `docs/superpowers/specs/2026-10-02-ledger-agent-core-design.md`; branch `feature/core-loop` provides the 92-test core).

## Global Constraints

- Branch base: `feature/ui-api-persistence` (off `feature/core-loop`). `feature/core-loop` is not modified.
- All money in API JSON and in the UI is a **string** (pydantic `model_dump(mode="json")`); the frontend never converts money to `Number`.
- Chroma records use explicit dummy embeddings (`[0.0]`) and `embedding_function=None`; real chunk embeddings come only from our `Embedder`. Nothing may download a model or need network.
- Per-invoice vector collections are named `idx-<16 hex>` and **must be deleted** on `dispose()`; a startup sweep deletes any leftover `idx-*`.
- The `invoice_id` scope guard in `InvoiceIndex` is unchanged and still enforced for every backend.
- Upload limits: PDF magic bytes `%PDF` required (extension is ignored), `MAX_UPLOAD_MB` default 20 (`413` over), non-PDF `415`, missing file `422`. Error body: `{"code": str, "message": str}`.
- Job `state` ∈ `QUEUED|RUNNING|DONE|ERROR`; `result.status` ∈ the core terminal statuses (`RECONCILED, UNRESOLVED, MAX_REVISIONS_EXCEEDED, INSUFFICIENT_EVIDENCE, NO_PROGRESS, FAILED`). `ERROR` = service failure; `FAILED` = invoice could not be processed.
- Defaults stay offline: `HashingEmbedder`, `ChunkValueProposer`. No API keys needed anywhere.
- Frontend: Vite + React + TypeScript, plain CSS design tokens, no UI component library; WCAG AA contrast; works at phone width; respects `prefers-reduced-motion`; light/dark via `prefers-color-scheme`.
- Python tests live in unique-basename files under `tests/<area>/` (no `__init__.py`). Existing 92 tests must stay green after every merge.
- Commits end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Never stage `.gitignore` (it has an unrelated uncommitted `docs/` line); if a new file under `docs/` must be committed use `git add -f <file>`.

## Review Focus

1. **Fake `.pdf`, oversize and traversal uploads** (a text file named `x.pdf`, an empty body, a name like `../../evil.pdf`) must be rejected or neutralised before anything touches the graph or an unsafe path. Tests: Task A.
2. **Chroma collection leaks**: the per-invoice collection must be deleted on success, on every `failed` terminal path, and when a node crashes; leftovers are swept at startup. Tests: Task P2, Task I2.
3. **Concurrent uploads** must not mix invoices (separate jobs, separate collections, correct `invoice_id` per result). Tests: Task A, Task I2.
4. **Restart**: jobs persist, and jobs left `QUEUED/RUNNING` by a crash become `ERROR` ("interrupted by restart") instead of spinning forever in the UI. Tests: Task W0-2 contract, Task P1, Task I2.
5. **Frontend robustness**: unknown `result.status`, a 200-row ledger, a very long filename, and money strings larger than JS safe integers must render correctly. Tests: Task F.

## File Structure

```
contracts/openapi.yaml, contracts/example-job.json            (W0-2)
src/ledger_agent/tracing.py                                    (W0-1)
src/ledger_agent/storage/{__init__,base,memory}.py             (W0-2)
src/ledger_agent/storage/chroma_store.py                       (P1)
src/ledger_agent/retrieval/chroma_vector.py                    (P2)
src/ledger_agent/api/{__init__,app,runner}.py                  (A)
src/ledger_agent/api/main.py                                   (I1)
src/ledger_agent/observability/{__init__,sinks}.py             (O1)
src/ledger_agent/eval/{__init__,__main__,dataset,variants,metrics,runner,report}.py  (O2)
frontend/ ...                                                  (F)
tests/storage/, tests/vector/, tests/api/, tests/observability/, tests/eval/, tests/e2e/
```

## Parallel protocol

Repo root: `C:/Users/ASUS/Documents/Projects/Claude_Projects/Self_correcting_Ledger_Agent` (`$REPO`). Python: `$REPO/.venv/Scripts/python.exe` (`$PY`).

After Wave 0 is committed and pushed on `feature/ui-api-persistence`, the controller creates one worktree per stream **as siblings of the repo**:
```bash
cd $REPO
for s in persist-store persist-vector api frontend obs-sinks eval; do
  git worktree add ../ledger-wt-$s -b stream/$s feature/ui-api-persistence
done
```
Each implementer works only inside `../ledger-wt-<stream>`, runs tests there with `$PY -m pytest <files>` (the worktree's `pythonpath=src` shadows the editable install; confirm with `$PY -c "import ledger_agent,sys;print(ledger_agent.__file__)"` run *via pytest*, or `PYTHONPATH=src $PY ...` for scripts), commits on `stream/<name>`, and `git push -u origin stream/<name>`. Streams never edit `pyproject.toml`, `graph.py`, `retrieval/hybrid.py`, `storage/base.py` or `contracts/` (Wave 0 owns them); a stream that needs such a change reports BLOCKED instead.

Merge (controller, after all six are reviewed clean): in `$REPO` on `feature/ui-api-persistence`: `git merge --no-ff stream/<name>` one by one, running the full suite after each; then `git worktree remove ../ledger-wt-<name>` and delete the stream branches locally.

| Task | Stream branch | Worktree |
|---|---|---|
| P1 Chroma job store | `stream/persist-store` | `../ledger-wt-persist-store` |
| P2 Chroma vector backend | `stream/persist-vector` | `../ledger-wt-persist-vector` |
| A API | `stream/api` | `../ledger-wt-api` |
| F Frontend | `stream/frontend` | `../ledger-wt-frontend` |
| O1 Trace sinks | `stream/obs-sinks` | `../ledger-wt-obs-sinks` |
| O2 Evaluation | `stream/eval` | `../ledger-wt-eval` |

---

## Wave 0 (sequential)

### Task W0-1: Core seams (vector factory, trace sink, retrieval mode) and dependencies

**Files:**
- Modify: `pyproject.toml`, `src/ledger_agent/retrieval/vector.py`, `src/ledger_agent/retrieval/hybrid.py`, `src/ledger_agent/graph.py`, `src/ledger_agent/state.py`
- Create: `src/ledger_agent/tracing.py`
- Test: `tests/unit/test_seams.py`

**Interfaces:**
- Produces:
  - `VectorIndexLike` protocol (in `retrieval/vector.py`): `scores(query: str) -> list[float]` (aligned with chunk order) and `dispose() -> None`; `VectorIndex.dispose()` is a no-op.
  - `VectorFactory = Callable[[str, list[Chunk], Embedder], VectorIndexLike]`.
  - `InvoiceIndex(invoice_id, chunks, embedder, vector_factory=None, default_mode="hybrid")`; `.search(..., mode: str | None = None)` uses `default_mode` when `mode` is None; `.dispose()` always clears state first, then calls the vector backend's `dispose()` (exceptions swallowed). `build_index(doc, embedder, vector_factory=None, mode="hybrid")`.
  - `TraceEvent`, `TraceSink` (protocol, `emit(event) -> None`), `NullTraceSink`, `ListTraceSink` (`.events`), `summarize(update, state) -> dict`, `traced(node_name, fn, sink) -> fn`.
  - `Deps` gains `vector_factory: VectorFactory | None = None`, `trace_sink: TraceSink = NullTraceSink()`, `retrieval_mode: str = "hybrid"`. `run_invoice(pdf_path, deps, invoice_id=None, run_id=None)`; state gains `run_id`.

- [ ] **Step 1: Dependencies.** In `pyproject.toml` add to `dependencies`: `"chromadb>=0.5"`, `"fastapi>=0.110"`, `"uvicorn>=0.29"`, `"python-multipart>=0.0.9"`; add to the `dev` extra: `"httpx>=0.27"`. Run `$PY -m pip install -e ".[dev]"`. Expected: installs; then `$PY -c "import chromadb, fastapi, httpx; print(chromadb.__version__)"` prints a version.

- [ ] **Step 2: Write failing tests** — `tests/unit/test_seams.py`:
```python
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
```
- [ ] **Step 3: Run, verify failure** — `$PY -m pytest tests/unit/test_seams.py -v` → FAIL (ImportError `ledger_agent.tracing`).

- [ ] **Step 4: Implement.**

`src/ledger_agent/tracing.py`:
```python
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
```
`retrieval/vector.py` — add at top `from typing import Callable, Protocol` and append:
```python
class VectorIndexLike(Protocol):
    def scores(self, query: str) -> list[float]: ...
    def dispose(self) -> None: ...


VectorFactory = Callable[[str, "list[Chunk]", Embedder], VectorIndexLike]
```
and add to `VectorIndex`:
```python
    def dispose(self) -> None:
        return None
```
`retrieval/hybrid.py` — replace `InvoiceIndex.__init__`, `search` signature head, `dispose`, and `build_index`:
```python
class InvoiceIndex:
    def __init__(self, invoice_id: str, chunks: list[Chunk], embedder: Embedder,
                 vector_factory=None, default_mode: str = "hybrid"):
        stray = [c.chunk_id for c in chunks if c.invoice_id != invoice_id]
        if stray:
            raise InvoiceScopeError(f"chunks from another invoice: {stray}")
        self.invoice_id = invoice_id
        self.default_mode = default_mode
        self._chunks: list[Chunk] | None = chunks
        self._bm25: BM25Index | None = BM25Index(chunks)
        factory = vector_factory or (lambda inv, ch, emb: VectorIndex(ch, emb))
        self._vec = factory(invoice_id, chunks, embedder)

    def search(self, invoice_id: str, query: str, k: int = 5, mode: str | None = None,
               chunk_types: list[str] | None = None) -> list[ScoredChunk]:
        mode = mode or self.default_mode
        ...  # rest unchanged

    def dispose(self) -> None:
        vec, self._chunks, self._bm25, self._vec = self._vec, None, None, None
        if vec is not None:
            try:
                vec.dispose()
            except Exception:  # backend cleanup failure must not hide the run's result
                pass


def build_index(doc: Document, embedder: Embedder, vector_factory=None,
                mode: str = "hybrid") -> InvoiceIndex:
    return InvoiceIndex(doc.document_id, build_chunks(doc), embedder,
                        vector_factory=vector_factory, default_mode=mode)
```
`state.py` — add `run_id: str` to `LedgerState`.

`graph.py` — (a) import `from ledger_agent.tracing import NullTraceSink, TraceSink, traced`, `import uuid`; (b) add to `Deps`: `vector_factory: Callable | None = None`, `trace_sink: TraceSink = field(default_factory=NullTraceSink)`, `retrieval_mode: str = "hybrid"`; (c) in `build_index_node` call `build_index(state["document"], deps.embedder, deps.vector_factory, deps.retrieval_mode)`; (d) register nodes as `g.add_node(name, traced(name, fn, deps.trace_sink))`; (e) `run_invoice(pdf_path, deps, invoice_id=None, run_id=None)`: add `"run_id": run_id or uuid.uuid4().hex[:12]` to `initial`.

- [ ] **Step 5: Run the whole suite** — `$PY -m pytest -q` → all pass (92 old + 6 new).
- [ ] **Step 6: Commit and push** on `feature/ui-api-persistence`: `git add pyproject.toml src tests && git commit -m "feat: vector-factory, trace-sink and retrieval-mode seams" && git push`.

---

### Task W0-2: Storage contract, in-memory store, OpenAPI contract, example job

**Files:**
- Create: `src/ledger_agent/storage/{__init__,base,memory}.py`, `contracts/openapi.yaml`, `contracts/example-job.json`
- Test: `tests/storage/job_store_contract.py`, `tests/storage/test_memory_store.py`

**Interfaces:**
- Produces (`storage/base.py`): `JobState`, `Job`, `JobStore` protocol, `new_job_id() -> str`, `utc_now() -> str`; (`storage/memory.py`): `InMemoryJobStore`. `JobStoreContract` mixin class that every store's test subclasses (Task P1 reuses it).
  - `Job(job_id: str, filename: str, state: JobState = "QUEUED", created_at: str, finished_at: str | None = None, result: dict | None = None, error: str | None = None)`.
  - `JobStore.create(job) -> None`; `update(job_id, **fields) -> Job` (raises `KeyError` for unknown id); `get(job_id) -> Job | None`; `list(limit: int = 50) -> list[Job]` newest-first by `created_at`; `append_events(job_id, events: list[dict]) -> None`; `get_events(job_id) -> list[dict]` in append order; `mark_interrupted() -> int` (QUEUED/RUNNING → ERROR with `error="interrupted by restart"` and `finished_at` set; returns count).

- [ ] **Step 1: Write the contract tests** — `tests/storage/job_store_contract.py`:
```python
import pytest

from ledger_agent.storage.base import Job


def make_job(job_id, created_at, **kw):
    return Job(job_id=job_id, filename=f"{job_id}.pdf", created_at=created_at, **kw)


class JobStoreContract:
    """Subclass as Test<Store> and implement make_store(self) -> JobStore."""

    def make_store(self):
        raise NotImplementedError

    def test_create_get_roundtrip(self):
        s = self.make_store()
        s.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
        got = s.get("a")
        assert got.job_id == "a" and got.state == "QUEUED" and got.result is None

    def test_get_unknown_is_none(self):
        assert self.make_store().get("nope") is None

    def test_update_changes_fields_and_returns_job(self):
        s = self.make_store()
        s.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
        out = s.update("a", state="RUNNING")
        assert out.state == "RUNNING" and s.get("a").state == "RUNNING"

    def test_update_unknown_raises_keyerror(self):
        with pytest.raises(KeyError):
            self.make_store().update("nope", state="DONE")

    def test_result_roundtrips_nested_strings(self):
        s = self.make_store()
        s.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
        result = {"status": "RECONCILED", "ledger": {"total": "1148.40", "items": [{"amount": "1014.00"}]}}
        s.update("a", state="DONE", result=result, finished_at="2026-01-01T00:00:05.000+00:00")
        got = s.get("a")
        assert got.result == result and got.finished_at.endswith("05.000+00:00")

    def test_list_is_newest_first_and_limited(self):
        s = self.make_store()
        for i, ts in enumerate(["2026-01-01T00:00:01.000+00:00", "2026-01-01T00:00:03.000+00:00",
                                "2026-01-01T00:00:02.000+00:00"]):
            s.create(make_job(f"j{i}", ts))
        assert [j.job_id for j in s.list()] == ["j1", "j2", "j0"]
        assert [j.job_id for j in s.list(limit=2)] == ["j1", "j2"]

    def test_events_keep_append_order_and_are_per_job(self):
        s = self.make_store()
        s.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
        s.create(make_job("b", "2026-01-01T00:00:01.000+00:00"))
        s.append_events("a", [{"node": "ingest"}, {"node": "extract"}])
        s.append_events("b", [{"node": "other"}])
        s.append_events("a", [{"node": "validate"}])
        assert [e["node"] for e in s.get_events("a")] == ["ingest", "extract", "validate"]
        assert [e["node"] for e in s.get_events("b")] == ["other"]
        assert s.get_events("none") == []

    def test_mark_interrupted_only_touches_unfinished_jobs(self):
        s = self.make_store()
        s.create(make_job("q", "2026-01-01T00:00:00.000+00:00"))
        s.create(make_job("r", "2026-01-01T00:00:01.000+00:00", state="RUNNING"))
        s.create(make_job("d", "2026-01-01T00:00:02.000+00:00", state="DONE"))
        assert s.mark_interrupted() == 2
        assert s.get("q").state == "ERROR" and s.get("q").error == "interrupted by restart"
        assert s.get("r").finished_at is not None
        assert s.get("d").state == "DONE"
        assert s.mark_interrupted() == 0
```
`tests/storage/test_memory_store.py`:
```python
from job_store_contract import JobStoreContract

from ledger_agent.storage.memory import InMemoryJobStore


class TestInMemoryStore(JobStoreContract):
    def make_store(self):
        return InMemoryJobStore()
```
- [ ] **Step 2:** `$PY -m pytest tests/storage -v` → FAIL (no module `ledger_agent.storage`).
- [ ] **Step 3: Implement.** `storage/__init__.py` empty. `storage/base.py`:
```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel

JobState = Literal["QUEUED", "RUNNING", "DONE", "ERROR"]


class Job(BaseModel):
    job_id: str
    filename: str
    state: JobState = "QUEUED"
    created_at: str
    finished_at: str | None = None
    result: dict | None = None
    error: str | None = None


class JobStore(Protocol):
    def create(self, job: Job) -> None: ...
    def update(self, job_id: str, **fields) -> Job: ...
    def get(self, job_id: str) -> Job | None: ...
    def list(self, limit: int = 50) -> list[Job]: ...
    def append_events(self, job_id: str, events: list[dict]) -> None: ...
    def get_events(self, job_id: str) -> list[dict]: ...
    def mark_interrupted(self) -> int: ...


def new_job_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
```
`storage/memory.py`:
```python
import threading

from ledger_agent.storage.base import Job, utc_now


class InMemoryJobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._events: dict[str, list[dict]] = {}
        self._lock = threading.RLock()

    def create(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def update(self, job_id: str, **fields) -> Job:
        with self._lock:
            job = self._jobs[job_id]          # KeyError for unknown ids
            job = Job.model_validate({**job.model_dump(), **fields})
            self._jobs[job_id] = job
            return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 50) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]

    def append_events(self, job_id: str, events: list[dict]) -> None:
        with self._lock:
            self._events.setdefault(job_id, []).extend(events)

    def get_events(self, job_id: str) -> list[dict]:
        with self._lock:
            return list(self._events.get(job_id, []))

    def mark_interrupted(self) -> int:
        with self._lock:
            n = 0
            for jid, job in list(self._jobs.items()):
                if job.state in ("QUEUED", "RUNNING"):
                    self.update(jid, state="ERROR", error="interrupted by restart", finished_at=utc_now())
                    n += 1
            return n
```
`contracts/example-job.json` (a DONE job from the "line amount extraction error" scenario; money as strings):
```json
{
  "job_id": "7f3c0d9e5a1b4c2f8e6d1a0b9c8d7e6f",
  "filename": "INV-001.pdf",
  "state": "DONE",
  "created_at": "2026-10-02T09:00:00.000+00:00",
  "finished_at": "2026-10-02T09:00:01.250+00:00",
  "error": null,
  "result": {
    "invoice_id": "INV-001",
    "status": "RECONCILED",
    "iterations": 1,
    "error": null,
    "ledger": {
      "invoice_id": "INV-001", "currency": "USD",
      "items": [
        {"id": "line_01", "description": "Industrial Filter", "quantity": "12", "unit_price": "84.50", "amount": "1014.00",
         "source": {"amount": {"document_id": "INV-001", "page": 1, "table_id": "table_01", "row": 1, "column": "Amount"}}},
        {"id": "line_02", "description": "Gasket", "quantity": "3", "unit_price": "10.00", "amount": "30.00",
         "source": {"amount": {"document_id": "INV-001", "page": 1, "table_id": "table_01", "row": 2, "column": "Amount"}}}
      ],
      "subtotal": "1044.00", "discount": null, "tax": "104.40",
      "tax_lines": [{"id": "tax_01", "rate": "0.10", "amount": "104.40", "source": {}}],
      "shipping": null, "fees": null, "total": "1148.40", "sources": {}
    },
    "original_ledger": {
      "invoice_id": "INV-001", "currency": "USD",
      "items": [
        {"id": "line_01", "description": "Industrial Filter", "quantity": "12", "unit_price": "84.50", "amount": "1040.00", "source": {}},
        {"id": "line_02", "description": "Gasket", "quantity": "3", "unit_price": "10.00", "amount": "30.00", "source": {}}
      ],
      "subtotal": "1044.00", "discount": null, "tax": "104.40",
      "tax_lines": [{"id": "tax_01", "rate": "0.10", "amount": "104.40", "source": {}}],
      "shipping": null, "fees": null, "total": "1148.40", "sources": {}
    },
    "corrections": [
      {"revision": 1, "field": "items[line_01].amount", "old_value": "1040.00", "new_value": "1014.00",
       "reason": "Source invoice evidence", "source_page": 1, "source_table": "table_01", "source_row": 1, "confidence": 0.97}
    ],
    "evidence": [
      {"field": "items[line_01].amount", "value": "1014.00", "confidence": 0.97, "chunk_id": "INV-001:line_01",
       "quote": "Invoice INV-001 | Page 1 | table_01 | Row 1 | line_01\nDescription: Industrial Filter\nQuantity: 12\nUnit Price: 84.50\nAmount: 1,014.00",
       "source": {"document_id": "INV-001", "page": 1, "table_id": "table_01", "row": 1, "column": "amount"}}
    ]
  }
}
```
`contracts/openapi.yaml`:
```yaml
openapi: 3.0.3
info: {title: Self-Correcting Ledger Agent, version: 1.0.0}
paths:
  /api/health:
    get: {summary: Health, responses: {"200": {description: ok, content: {application/json: {schema: {$ref: "#/components/schemas/Health"}}}}}}
  /api/invoices:
    post:
      summary: Upload an invoice PDF
      requestBody:
        required: true
        content: {multipart/form-data: {schema: {type: object, required: [file], properties: {file: {type: string, format: binary}}}}}
      responses:
        "202": {description: accepted, content: {application/json: {schema: {$ref: "#/components/schemas/Accepted"}}}}
        "413": {description: file too large, content: {application/json: {schema: {$ref: "#/components/schemas/Error"}}}}
        "415": {description: not a PDF, content: {application/json: {schema: {$ref: "#/components/schemas/Error"}}}}
        "422": {description: no file, content: {application/json: {schema: {$ref: "#/components/schemas/Error"}}}}
    get:
      summary: Recent jobs, newest first
      parameters: [{name: limit, in: query, schema: {type: integer, default: 50, maximum: 200}}]
      responses: {"200": {description: ok, content: {application/json: {schema: {type: array, items: {$ref: "#/components/schemas/Job"}}}}}}
  /api/invoices/{job_id}:
    get:
      summary: One job
      parameters: [{name: job_id, in: path, required: true, schema: {type: string}}]
      responses:
        "200": {description: ok, content: {application/json: {schema: {$ref: "#/components/schemas/Job"}}}}
        "404": {description: unknown job, content: {application/json: {schema: {$ref: "#/components/schemas/Error"}}}}
  /api/invoices/{job_id}/trace:
    get:
      summary: Trace events of a job
      parameters: [{name: job_id, in: path, required: true, schema: {type: string}}]
      responses:
        "200": {description: ok, content: {application/json: {schema: {type: array, items: {$ref: "#/components/schemas/TraceEvent"}}}}}
        "404": {description: unknown job, content: {application/json: {schema: {$ref: "#/components/schemas/Error"}}}}
components:
  schemas:
    Health: {type: object, required: [status, store], properties: {status: {type: string}, store: {type: string}}}
    Accepted: {type: object, required: [job_id, status], properties: {job_id: {type: string}, status: {type: string, enum: [QUEUED]}}}
    Error: {type: object, required: [code, message], properties: {code: {type: string}, message: {type: string}}}
    Job:
      type: object
      required: [job_id, filename, state, created_at]
      properties:
        job_id: {type: string}
        filename: {type: string}
        state: {type: string, enum: [QUEUED, RUNNING, DONE, ERROR]}
        created_at: {type: string}
        finished_at: {type: string, nullable: true}
        error: {type: string, nullable: true}
        result: {type: object, nullable: true, description: "ReconciliationResult in JSON mode; money values are strings. See contracts/example-job.json."}
    TraceEvent:
      type: object
      required: [run_id, node, started_at, latency_ms]
      properties:
        run_id: {type: string}
        invoice_id: {type: string, nullable: true}
        node: {type: string}
        revision: {type: integer}
        started_at: {type: string}
        latency_ms: {type: number}
        status: {type: string, nullable: true}
        detail: {type: object}
```
Add a test to `tests/storage/test_memory_store.py` that validates the example fixture against the model:
```python
import json
from pathlib import Path

from ledger_agent.graph import ReconciliationResult
from ledger_agent.storage.base import Job


def test_example_job_fixture_matches_models():
    raw = json.loads((Path(__file__).parents[2] / "contracts" / "example-job.json").read_text(encoding="utf-8"))
    job = Job.model_validate(raw)
    result = ReconciliationResult.model_validate(job.result)
    assert result.status.value == "RECONCILED" and result.corrections[0].field == "items[line_01].amount"
```
- [ ] **Step 4:** `$PY -m pytest -q` → all green. **Step 5: Commit and push** (`feat: storage contract, in-memory store, OpenAPI contract and example job`).

---

## Wave P — six parallel streams (dispatch in ONE message after creating the worktrees)

Every stream implementer prompt must include: its worktree path, "work only in this worktree and on branch `stream/<name>`", the file-ownership rule from the Parallel protocol, the task text, the commit/push commands, and the report-file path.

### Task P1: ChromaJobStore (stream `persist-store`)

**Files:**
- Create: `src/ledger_agent/storage/chroma_store.py`
- Test: `tests/storage/test_chroma_store.py`

**Interfaces:**
- Consumes: `Job`, `utc_now`, `JobStoreContract` (tests/storage), `chromadb`.
- Produces: `ChromaJobStore(client)` implementing `JobStore`; `ChromaJobStore.persistent(path) -> ChromaJobStore`. Collections `jobs` (id = job_id; document = `job.model_dump_json()`; metadata `{state, filename, created_at}`) and `events` (id = `f"{job_id}:{seq:08d}"`; document = JSON of the event; metadata `{job_id, seq}`).

- [ ] **Step 1: Tests** — `tests/storage/test_chroma_store.py`:
```python
import chromadb
from job_store_contract import JobStoreContract, make_job

from ledger_agent.storage.chroma_store import ChromaJobStore


class TestChromaStoreContract(JobStoreContract):
    def make_store(self):
        # EphemeralClient shares one in-process system: give every store its own collections
        # by clearing them first so contract tests are isolated.
        client = chromadb.EphemeralClient()
        for name in ("jobs", "events"):
            try:
                client.delete_collection(name)
            except Exception:
                pass
        return ChromaJobStore(client)


def test_jobs_survive_a_new_client_on_the_same_directory(tmp_path):
    first = ChromaJobStore.persistent(tmp_path / "chroma")
    first.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
    first.append_events("a", [{"node": "ingest"}])
    first.update("a", state="DONE", result={"status": "RECONCILED"})
    del first
    try:  # force a genuinely new client/system rather than the cached shared one
        from chromadb.api.shared_system_client import SharedSystemClient
        SharedSystemClient.clear_system_cache()
    except Exception:
        pass
    second = ChromaJobStore.persistent(tmp_path / "chroma")
    got = second.get("a")
    assert got.state == "DONE" and got.result == {"status": "RECONCILED"}
    assert second.get_events("a") == [{"node": "ingest"}]


def test_chroma_store_is_thread_safe_for_concurrent_appends(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    store = ChromaJobStore.persistent(tmp_path / "chroma")
    store.create(make_job("a", "2026-01-01T00:00:00.000+00:00"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: store.append_events("a", [{"n": i}]), range(20)))
    assert sorted(e["n"] for e in store.get_events("a")) == list(range(20))
```
- [ ] **Step 2:** run `tests/storage/test_chroma_store.py` → FAIL (module missing).
- [ ] **Step 3: Implement** `storage/chroma_store.py`:
```python
from __future__ import annotations

import json
import threading
from pathlib import Path

import chromadb

from ledger_agent.storage.base import Job, utc_now

_ZERO = [0.0]


class ChromaJobStore:
    """JobStore on ChromaDB. Records are JSON documents with a dummy embedding."""

    def __init__(self, client):
        self._jobs = client.get_or_create_collection("jobs", embedding_function=None)
        self._events = client.get_or_create_collection("events", embedding_function=None)
        self._lock = threading.RLock()

    @classmethod
    def persistent(cls, path) -> "ChromaJobStore":
        Path(path).mkdir(parents=True, exist_ok=True)
        return cls(chromadb.PersistentClient(path=str(path)))

    def _put(self, job: Job) -> None:
        self._jobs.upsert(ids=[job.job_id], embeddings=[_ZERO], documents=[job.model_dump_json()],
                          metadatas=[{"state": job.state, "filename": job.filename,
                                      "created_at": job.created_at}])

    def create(self, job: Job) -> None:
        with self._lock:
            self._put(job)

    def get(self, job_id: str) -> Job | None:
        docs = self._jobs.get(ids=[job_id], include=["documents"])["documents"]
        return Job.model_validate_json(docs[0]) if docs else None

    def update(self, job_id: str, **fields) -> Job:
        with self._lock:
            job = self.get(job_id)
            if job is None:
                raise KeyError(job_id)
            job = Job.model_validate({**job.model_dump(), **fields})
            self._put(job)
            return job

    def list(self, limit: int = 50) -> list[Job]:
        docs = self._jobs.get(include=["documents"])["documents"]
        jobs = [Job.model_validate_json(d) for d in docs]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)[:limit]

    def append_events(self, job_id: str, events: list[dict]) -> None:
        if not events:
            return
        with self._lock:
            start = len(self._events.get(where={"job_id": job_id}, include=[])["ids"])
            self._events.upsert(
                ids=[f"{job_id}:{start + i:08d}" for i in range(len(events))],
                embeddings=[_ZERO] * len(events),
                documents=[json.dumps(e, default=str) for e in events],
                metadatas=[{"job_id": job_id, "seq": start + i} for i in range(len(events))])

    def get_events(self, job_id: str) -> list[dict]:
        got = self._events.get(where={"job_id": job_id}, include=["documents", "metadatas"])
        pairs = sorted(zip(got["metadatas"], got["documents"]), key=lambda p: p[0]["seq"])
        return [json.loads(doc) for _meta, doc in pairs]

    def mark_interrupted(self) -> int:
        with self._lock:
            got = self._jobs.get(where={"state": {"$in": ["QUEUED", "RUNNING"]}}, include=["documents"])
            for doc in got["documents"]:
                self.update(Job.model_validate_json(doc).job_id, state="ERROR",
                            error="interrupted by restart", finished_at=utc_now())
            return len(got["documents"])
```
Chroma API differs a little between versions (`embedding_function=None`, `where` operators, import path of `SharedSystemClient`): check the installed version; if a call differs, adapt minimally and say so in the report. Do not weaken the contract tests.
- [ ] **Step 4:** `$PY -m pytest tests/storage -v` → PASS (memory + Chroma contract + persistence + threads).
- [ ] **Step 5:** commit on `stream/persist-store` and `git push -u origin stream/persist-store`.

### Task P2: Chroma vector backend (stream `persist-vector`)

**Files:**
- Create: `src/ledger_agent/retrieval/chroma_vector.py`
- Test: `tests/vector/test_chroma_vector.py`

**Interfaces:**
- Consumes: `Chunk`, `Embedder`, `VectorIndexLike`/`VectorFactory`, `build_index`, `InvoiceIndex`, `make_document`, `HashingEmbedder`, `chromadb`.
- Produces: `ChromaVectorIndex(client, invoice_id, chunks, embedder)` implementing `VectorIndexLike` (one collection `idx-<16 hex>`, cosine-equivalent scoring via normalised vectors in an inner-product space; `scores` aligned to chunk order; `dispose()` deletes the collection and is idempotent); `chroma_vector_factory(client) -> VectorFactory`; `sweep_orphan_indexes(client) -> int`; `list_index_collections(client) -> list[str]`.

- [ ] **Step 1: Tests** — `tests/vector/test_chroma_vector.py`:
```python
from decimal import Decimal as D

import chromadb
import pytest

from ledger_agent.fakes import HashingEmbedder
from ledger_agent.retrieval.chroma_vector import (
    ChromaVectorIndex, chroma_vector_factory, list_index_collections, sweep_orphan_indexes)
from ledger_agent.retrieval.hybrid import InvoiceScopeError, build_index
from ledger_agent.testing.ledgers import make_document

EMB = HashingEmbedder()
TEN = tuple((f"Part {i:02d}", D("2"), D("5.00")) for i in range(1, 11))


@pytest.fixture()
def client():
    c = chromadb.EphemeralClient()
    sweep_orphan_indexes(c)
    yield c
    sweep_orphan_indexes(c)


def top_ids(idx, query, mode="hybrid", k=3):
    return [r.chunk.chunk_id for r in idx.search("INV-001", query, k=k, mode=mode,
                                                 chunk_types=["line_item"])]


@pytest.mark.parametrize("query", ["line_07 Part 07 quantity unit price amount",
                                   "line_02 Part 02", "Part 10 amount"])
@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_rankings_match_the_numpy_backend(client, query, mode):
    doc = make_document(items=TEN)
    numpy_idx = build_index(doc, EMB)
    chroma_idx = build_index(doc, EMB, vector_factory=chroma_vector_factory(client))
    assert top_ids(chroma_idx, query, mode) == top_ids(numpy_idx, query, mode)
    chroma_idx.dispose()


def test_scores_are_aligned_to_chunk_order(client):
    doc = make_document(items=TEN)
    from ledger_agent.retrieval.chunks import build_chunks
    from ledger_agent.retrieval.vector import VectorIndex

    chunks = build_chunks(doc)
    ref = VectorIndex(chunks, EMB).scores("line_03 Part 03 amount")
    got = ChromaVectorIndex(client, "INV-001", chunks, EMB).scores("line_03 Part 03 amount")
    assert len(got) == len(ref)
    assert all(abs(a - b) < 1e-4 for a, b in zip(got, ref))


def test_dispose_deletes_the_collection_and_is_idempotent(client):
    idx = build_index(make_document(), EMB, vector_factory=chroma_vector_factory(client))
    assert len(list_index_collections(client)) == 1
    idx.dispose()
    idx.dispose()
    assert list_index_collections(client) == []


def test_two_invoices_use_separate_collections_and_never_leak(client):
    factory = chroma_vector_factory(client)
    a = build_index(make_document(invoice_id="INV-A"), EMB, vector_factory=factory)
    b = build_index(make_document(invoice_id="INV-B"), EMB, vector_factory=factory)
    assert len(list_index_collections(client)) == 2
    with pytest.raises(InvoiceScopeError):
        a.search("INV-B", "total")
    assert all(r.chunk.invoice_id == "INV-A" for r in a.search("INV-A", "total", k=10))
    a.dispose()
    assert len(list_index_collections(client)) == 1
    assert b.search("INV-B", "total", k=3)
    b.dispose()


def test_sweep_removes_orphans_but_not_other_collections(client):
    client.get_or_create_collection("jobs", embedding_function=None)
    ChromaVectorIndex(client, "INV-X", [], EMB)          # empty -> creates nothing
    orphan = build_index(make_document(), EMB, vector_factory=chroma_vector_factory(client))
    assert sweep_orphan_indexes(client) == 1
    assert list_index_collections(client) == []
    names = [getattr(c, "name", c) for c in client.list_collections()]
    assert "jobs" in names
    del orphan


def test_empty_corpus_and_zero_query_vector(client):
    assert ChromaVectorIndex(client, "INV-X", [], EMB).scores("anything") == []
    idx = build_index(make_document(), EMB, vector_factory=chroma_vector_factory(client))
    assert idx.search("INV-001", "", k=2, mode="vector") is not None   # empty query -> zero vector
    idx.dispose()
```
- [ ] **Step 2:** run → FAIL. **Step 3: Implement** `retrieval/chroma_vector.py`:
```python
from __future__ import annotations

import uuid

import numpy as np

from ledger_agent.models import Chunk
from ledger_agent.protocols import Embedder

_PREFIX = "idx-"


def _names(client) -> list[str]:
    return [getattr(c, "name", c) for c in client.list_collections()]


def list_index_collections(client) -> list[str]:
    return [n for n in _names(client) if n.startswith(_PREFIX)]


def sweep_orphan_indexes(client) -> int:
    orphans = list_index_collections(client)
    for name in orphans:
        client.delete_collection(name)
    return len(orphans)


def _normalise(vectors: list[list[float]]) -> np.ndarray:
    m = np.array(vectors, dtype=float)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


class ChromaVectorIndex:
    """Per-invoice vector index in its own Chroma collection (inner product on unit vectors)."""

    def __init__(self, client, invoice_id: str, chunks: list[Chunk], embedder: Embedder):
        self._client = client
        self._embedder = embedder
        self._n = len(chunks)
        self._name: str | None = None
        self._col = None
        if not chunks:
            return
        self._name = f"{_PREFIX}{uuid.uuid4().hex[:16]}"
        # Adapt the "ip" space setting to the installed chromadb version:
        #   >=1.0: configuration={"hnsw": {"space": "ip"}};  older: metadata={"hnsw:space": "ip"}.
        self._col = self._create_collection(client, self._name, invoice_id)
        vectors = _normalise(embedder.embed([c.text for c in chunks]))
        self._col.add(ids=[str(i) for i in range(len(chunks))], embeddings=vectors.tolist(),
                      metadatas=[{"invoice_id": invoice_id, "chunk_id": c.chunk_id} for c in chunks])

    @staticmethod
    def _create_collection(client, name, invoice_id):
        try:
            return client.create_collection(name, embedding_function=None,
                                            configuration={"hnsw": {"space": "ip"}},
                                            metadata={"invoice_id": invoice_id})
        except TypeError:
            return client.create_collection(name, embedding_function=None,
                                            metadata={"hnsw:space": "ip", "invoice_id": invoice_id})

    def scores(self, query: str) -> list[float]:
        if self._col is None:
            return []
        q = _normalise([self._embedder.embed([query])[0]])[0]
        res = self._col.query(query_embeddings=[q.tolist()], n_results=self._n, include=["distances"])
        out = [0.0] * self._n
        for id_, dist in zip(res["ids"][0], res["distances"][0]):
            out[int(id_)] = 1.0 - float(dist)      # ip distance = 1 - dot(unit, unit)
        return out

    def dispose(self) -> None:
        if self._name is None:
            return
        name, self._name, self._col = self._name, None, None
        try:
            self._client.delete_collection(name)
        except Exception:
            pass                                    # already gone


def chroma_vector_factory(client):
    def factory(invoice_id: str, chunks: list[Chunk], embedder: Embedder) -> ChromaVectorIndex:
        return ChromaVectorIndex(client, invoice_id, chunks, embedder)
    return factory
```
If rankings differ from numpy only by float ties, investigate (rounding scores to 6 decimals inside `scores` is acceptable if documented); do not loosen the parity test.
- [ ] **Step 4:** `$PY -m pytest tests/vector -v` → PASS. **Step 5:** commit on `stream/persist-vector`, push.

### Task A: FastAPI service (stream `api`)

**Files:**
- Create: `src/ledger_agent/api/{__init__,app,runner}.py`
- Test: `tests/api/test_api.py`, `tests/api/test_runner.py`

**Interfaces:**
- Consumes: `Job`, `JobStore`, `InMemoryJobStore`, `new_job_id`, `utc_now`, `Deps`, `run_invoice`, `contracts/openapi.yaml` (behaviour must match).
- Produces: `create_app(store, deps_factory, *, max_upload_mb: float = 20, upload_dir=None, executor=None, frontend_dist=None, cors_origins=("http://localhost:5173", "http://127.0.0.1:5173"), store_name="memory") -> FastAPI`, where `deps_factory: Callable[[str], Deps]` receives the job id; `run_job(store, deps_factory, job_id, pdf_path, invoice_id) -> None` in `api/runner.py`.

- [ ] **Step 1: Tests.** `tests/api/test_runner.py`:
```python
from pathlib import Path

from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.api.runner import run_job
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps
from ledger_agent.storage.base import Job
from ledger_agent.storage.memory import InMemoryJobStore
from ledger_agent.testing.invoices import default_spec, render_invoice


def deps(job_id):
    return Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer())


def new_store():
    s = InMemoryJobStore()
    s.create(Job(job_id="j1", filename="INV-001.pdf", created_at="2026-01-01T00:00:00.000+00:00"))
    return s


def test_run_job_success_stores_json_result_and_deletes_upload(tmp_path):
    store = new_store()
    pdf = render_invoice(default_spec(), tmp_path / "j1.pdf")
    run_job(store, deps, "j1", Path(pdf), "INV-001")
    job = store.get("j1")
    assert job.state == "DONE" and job.finished_at and job.error is None
    assert job.result["status"] == "RECONCILED"
    assert job.result["ledger"]["total"] == "1148.40"            # money is a string
    assert not pdf.exists()


def test_run_job_turns_crashes_into_error_state(tmp_path):
    store = new_store()
    pdf = render_invoice(default_spec(), tmp_path / "j1.pdf")

    def boom(job_id):
        raise RuntimeError("deps exploded")

    run_job(store, boom, "j1", Path(pdf), "INV-001")
    job = store.get("j1")
    assert job.state == "ERROR" and "deps exploded" in job.error and job.result is None
    assert not pdf.exists()


def test_run_job_for_unreadable_pdf_is_a_result_not_an_error(tmp_path):
    store = new_store()
    bad = tmp_path / "j1.pdf"
    bad.write_bytes(b"%PDF-1.4 not really a pdf")
    run_job(store, deps, "j1", bad, "broken")
    job = store.get("j1")
    assert job.state == "DONE" and job.result["status"] == "FAILED"
```
`tests/api/test_api.py`:
```python
import time
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.api.app import create_app
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps
from ledger_agent.storage.memory import InMemoryJobStore
from ledger_agent.testing.corrupt import corrupting_builder
from ledger_agent.testing.invoices import default_spec, render_invoice


class Inline:
    def submit(self, fn, *a, **kw):
        fn(*a, **kw)


def plain_deps(job_id):
    return Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer())


def corrupt_deps(job_id):
    return Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer(),
                ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00")))


@pytest.fixture()
def pdf_bytes(tmp_path):
    return render_invoice(default_spec(), tmp_path / "INV-001.pdf").read_bytes()


def make_client(tmp_path, deps_factory=plain_deps, **kw):
    store = InMemoryJobStore()
    app = create_app(store, deps_factory, upload_dir=tmp_path / "up", executor=Inline(), **kw)
    return TestClient(app), store


def upload(client, data, name="INV-001.pdf"):
    return client.post("/api/invoices", files={"file": (name, data, "application/pdf")})


def test_health(tmp_path):
    c, _ = make_client(tmp_path)
    assert c.get("/api/health").json() == {"status": "ok", "store": "memory"}


def test_upload_runs_the_job_and_returns_result(tmp_path, pdf_bytes):
    c, _ = make_client(tmp_path)
    r = upload(c, pdf_bytes)
    assert r.status_code == 202 and r.json()["status"] == "QUEUED"
    job = c.get(f"/api/invoices/{r.json()['job_id']}").json()
    assert job["state"] == "DONE" and job["result"]["status"] == "RECONCILED"
    assert job["filename"] == "INV-001.pdf" and job["result"]["invoice_id"] == "INV-001"


def test_correction_is_visible_with_provenance_and_string_money(tmp_path, pdf_bytes):
    c, _ = make_client(tmp_path, corrupt_deps)
    job = c.get(f"/api/invoices/{upload(c, pdf_bytes).json()['job_id']}").json()
    res = job["result"]
    assert res["iterations"] == 1 and res["corrections"][0]["new_value"] == "1014.00"
    assert res["corrections"][0]["source_table"] == "table_01"
    assert res["original_ledger"]["items"][0]["amount"] == "1040.00"


def test_text_file_named_pdf_is_rejected_415(tmp_path):                      # Review Focus 1
    c, store = make_client(tmp_path)
    r = upload(c, b"hello, definitely not a pdf", name="evil.pdf")
    assert r.status_code == 415 and r.json()["code"] == "not_a_pdf"
    assert store.list() == []


def test_empty_upload_is_415(tmp_path):
    c, _ = make_client(tmp_path)
    assert upload(c, b"").status_code == 415


def test_oversize_upload_is_413(tmp_path, pdf_bytes):
    c, store = make_client(tmp_path, max_upload_mb=0.0001)       # ~104 bytes
    r = upload(c, pdf_bytes)
    assert r.status_code == 413 and r.json()["code"] == "too_large"
    assert store.list() == []


def test_missing_file_is_422(tmp_path):
    c, _ = make_client(tmp_path)
    r = c.post("/api/invoices")
    assert r.status_code == 422 and r.json()["code"] == "missing_file"


def test_traversal_filename_is_neutralised(tmp_path, pdf_bytes):            # Review Focus 1
    c, _ = make_client(tmp_path)
    job = c.get(f"/api/invoices/{upload(c, pdf_bytes, name='../../evil.pdf').json()['job_id']}").json()
    assert job["state"] == "DONE" and job["result"]["invoice_id"] == "evil"
    assert not (tmp_path.parent / "evil.pdf").exists()
    assert list((tmp_path / "up").iterdir()) == []                          # uploads cleaned up


def test_unknown_job_404_for_job_and_trace(tmp_path):
    c, _ = make_client(tmp_path)
    assert c.get("/api/invoices/nope").status_code == 404
    assert c.get("/api/invoices/nope/trace").json()["code"] == "not_found"


def test_list_is_newest_first(tmp_path, pdf_bytes):
    c, _ = make_client(tmp_path)
    ids = [upload(c, pdf_bytes, name=f"A{i}.pdf").json()["job_id"] for i in range(3)]
    listed = [j["job_id"] for j in c.get("/api/invoices").json()]
    assert listed == ids[::-1]
    assert len(c.get("/api/invoices?limit=2").json()) == 2


def test_trace_endpoint_returns_stored_events(tmp_path, pdf_bytes):
    c, store = make_client(tmp_path)
    jid = upload(c, pdf_bytes).json()["job_id"]
    store.append_events(jid, [{"node": "ingest", "latency_ms": 1.0}])
    assert c.get(f"/api/invoices/{jid}/trace").json() == [{"node": "ingest", "latency_ms": 1.0}]


def test_deps_factory_crash_becomes_error_job_not_500(tmp_path, pdf_bytes):
    def boom(job_id):
        raise RuntimeError("no deps")

    c, _ = make_client(tmp_path, boom)
    r = upload(c, pdf_bytes)
    assert r.status_code == 202
    job = c.get(f"/api/invoices/{r.json()['job_id']}").json()
    assert job["state"] == "ERROR" and "no deps" in job["error"]


def test_concurrent_uploads_do_not_mix_invoices(tmp_path, pdf_bytes):       # Review Focus 3
    store = InMemoryJobStore()
    app = create_app(store, plain_deps, upload_dir=tmp_path / "up")          # real thread pool
    c = TestClient(app)
    names = ["ALPHA.pdf", "BRAVO.pdf", "CHARLIE.pdf", "DELTA.pdf"]
    jobs = {upload(c, pdf_bytes, name=n).json()["job_id"]: n for n in names}
    deadline = time.time() + 30
    while time.time() < deadline:
        states = [c.get(f"/api/invoices/{j}").json() for j in jobs]
        if all(s["state"] in ("DONE", "ERROR") for s in states):
            break
        time.sleep(0.1)
    for j, name in jobs.items():
        data = c.get(f"/api/invoices/{j}").json()
        assert data["state"] == "DONE" and data["result"]["invoice_id"] == name[:-4]


def test_cors_allows_the_dev_origin(tmp_path):
    c, _ = make_client(tmp_path)
    r = c.options("/api/invoices", headers={"Origin": "http://localhost:5173",
                                            "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_static_frontend_is_mounted_when_dist_exists(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>UI</body></html>", encoding="utf-8")
    c, _ = make_client(tmp_path, frontend_dist=dist)
    assert "UI" in c.get("/").text
    assert c.get("/api/health").status_code == 200
```
- [ ] **Step 2:** run → FAIL. **Step 3: Implement.** `api/__init__.py` empty. `api/runner.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ledger_agent.graph import Deps, run_invoice
from ledger_agent.storage.base import JobStore, utc_now


def run_job(store: JobStore, deps_factory: Callable[[str], Deps], job_id: str,
            pdf_path: Path, invoice_id: str) -> None:
    """Run one reconciliation. Never raises: failures become job.state == 'ERROR'."""
    try:
        store.update(job_id, state="RUNNING")
        deps = deps_factory(job_id)
        result = run_invoice(str(pdf_path), deps, invoice_id=invoice_id)
        store.update(job_id, state="DONE", finished_at=utc_now(),
                     result=result.model_dump(mode="json"))
    except Exception as exc:  # service-level failure, distinct from an invoice FAILED result
        try:
            store.update(job_id, state="ERROR", finished_at=utc_now(), error=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
    finally:
        Path(pdf_path).unlink(missing_ok=True)
```
`api/app.py`:
```python
from __future__ import annotations

import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ledger_agent.api.runner import run_job
from ledger_agent.graph import Deps
from ledger_agent.storage.base import Job, JobStore, new_job_id, utc_now


def invoice_id_from_filename(filename: str | None) -> str:
    stem = Path((filename or "invoice").replace("\\", "/")).stem
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return (safe or "invoice")[:40]


def create_app(store: JobStore, deps_factory: Callable[[str], Deps], *, max_upload_mb: float = 20,
               upload_dir=None, executor=None, frontend_dist=None,
               cors_origins=("http://localhost:5173", "http://127.0.0.1:5173"),
               store_name: str = "memory") -> FastAPI:
    upload_root = Path(upload_dir) if upload_dir else Path(tempfile.mkdtemp(prefix="ledger-uploads-"))
    upload_root.mkdir(parents=True, exist_ok=True)
    own_pool = executor is None
    pool = executor or ThreadPoolExecutor(max_workers=2)
    max_bytes = int(max_upload_mb * 1024 * 1024)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        if own_pool:
            pool.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Self-Correcting Ledger Agent", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(cors_origins),
                       allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

    def err(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"code": code, "message": message})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "store": store_name}

    @app.post("/api/invoices", status_code=202)
    async def upload(file: UploadFile | None = File(default=None)):
        if file is None:
            return err(422, "missing_file", "Attach a PDF in the 'file' field.")
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            return err(413, "too_large", f"File exceeds the {max_upload_mb:g} MB limit.")
        if not data.startswith(b"%PDF"):
            return err(415, "not_a_pdf", "That file is not a PDF.")
        job_id = new_job_id()
        path = upload_root / f"{job_id}.pdf"
        path.write_bytes(data)
        store.create(Job(job_id=job_id, filename=file.filename or "invoice.pdf", created_at=utc_now()))
        pool.submit(run_job, store, deps_factory, job_id, path, invoice_id_from_filename(file.filename))
        return {"job_id": job_id, "status": "QUEUED"}

    @app.get("/api/invoices")
    def list_jobs(limit: int = 50):
        return [j.model_dump(mode="json") for j in store.list(limit=max(1, min(limit, 200)))]

    @app.get("/api/invoices/{job_id}")
    def get_job(job_id: str):
        job = store.get(job_id)
        if job is None:
            return err(404, "not_found", "No such job.")
        return job.model_dump(mode="json")

    @app.get("/api/invoices/{job_id}/trace")
    def get_trace(job_id: str):
        if store.get(job_id) is None:
            return err(404, "not_found", "No such job.")
        return store.get_events(job_id)

    if frontend_dist is not None and Path(frontend_dist).is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="ui")
    return app
```
- [ ] **Step 4:** `$PY -m pytest tests/api -v` → PASS. **Step 5:** commit on `stream/api`, push.

### Task F: Frontend (stream `frontend`)

**Design requirement.** Before writing any CSS or visual structure, invoke the **`impeccable:impeccable`** skill (shape the page, then craft it) and the **`taste-skill:taste-skill`** (and `taste-skill:minimalist-skill`) skills; apply their guidance to `tokens.css`, `base.css` and component markup. The code below fixes behaviour, structure, accessibility and tests; typography, spacing, colour, motion and micro-copy are yours to refine with those skills. After building, run impeccable's critique/polish pass and record what you changed in the report. Constraints: minimalist single column, no component library, no emoji icons, AA contrast, dark mode via `prefers-color-scheme`, `prefers-reduced-motion` respected.

**Files (all under `frontend/`):** `package.json`, `index.html`, `vite.config.ts`, `tsconfig.json`, `src/main.tsx`, `src/App.tsx`, `src/styles/{tokens,base}.css`, `src/api/{types,client}.ts`, `src/lib/{validate,format}.ts`, `src/hooks/useJob.ts`, `src/components/{DropZone,StatusBadge,LedgerTable,Corrections,Disclosure,Trace,RecentJobs,ResultView}.tsx`, `src/test/{setup.ts,*.test.ts(x)}`.

**Interfaces:** consumes `contracts/example-job.json` (via alias `@contracts`) and the HTTP contract; produces a static build in `frontend/dist` served by FastAPI or `npm run dev` (port 5173, proxy `/api` → `http://localhost:8000`).

- [ ] **Step 1: Scaffold.** `frontend/package.json`:
```json
{
  "name": "ledger-agent-ui",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": { "react": "^18.3.1", "react-dom": "^18.3.1" },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "jsdom": "^24.1.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "vitest": "^2.0.0"
  }
}
```
`vite.config.ts`:
```ts
/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@contracts": path.resolve(__dirname, "../contracts") } },
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" }, fs: { allow: [".."] } },
  test: { environment: "jsdom", globals: true, setupFiles: "./src/test/setup.ts" },
});
```
`tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022", "lib": ["ES2022", "DOM", "DOM.Iterable"], "module": "ESNext",
    "moduleResolution": "bundler", "jsx": "react-jsx", "strict": true, "noUnusedLocals": true,
    "resolveJsonModule": true, "isolatedModules": true, "skipLibCheck": true, "noEmit": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"],
    "paths": { "@contracts/*": ["../contracts/*"] }, "baseUrl": "."
  },
  "include": ["src", "vite.config.ts"]
}
```
`index.html`: standard Vite shell with `<div id="root">`, `<meta name="viewport" content="width=device-width, initial-scale=1">`, title "Ledger Agent", `<script type="module" src="/src/main.tsx">`. `src/main.tsx`: `createRoot(document.getElementById("root")!).render(<App />)` importing `./styles/tokens.css`, `./styles/base.css`. `src/test/setup.ts`: `import "@testing-library/jest-dom/vitest";`. Run `cd frontend && npm install`.

- [ ] **Step 2: Types, formatting, validation (tests first).** `src/api/types.ts`:
```ts
export type JobState = "QUEUED" | "RUNNING" | "DONE" | "ERROR";
export interface Provenance {
  document_id: string; page: number; block_id?: string | null; table_id?: string | null;
  row?: number | null; column?: string | null; bbox?: number[] | null;
}
export interface LineItem {
  id: string; description: string; quantity: string; unit_price: string; amount: string;
  source: Record<string, Provenance>;
}
export interface TaxLine { id: string; rate: string | null; amount: string; source: Record<string, Provenance> }
export interface Ledger {
  invoice_id: string; currency: string; items: LineItem[]; subtotal: string | null; discount: string | null;
  tax: string | null; tax_lines: TaxLine[]; shipping: string | null; fees: string | null; total: string;
  sources: Record<string, Provenance>;
}
export interface Correction {
  revision: number; field: string; old_value: string; new_value: string; reason: string;
  source_page: number | null; source_table: string | null; source_row: number | null; confidence: number;
}
export interface Evidence {
  field: string; value: string; source: Provenance; confidence: number; chunk_id: string; quote: string;
}
export interface Result {
  invoice_id: string; status: string; iterations: number; ledger: Ledger | null;
  original_ledger: Ledger | null; corrections: Correction[]; evidence: Evidence[]; error: string | null;
}
export interface Job {
  job_id: string; filename: string; state: JobState; created_at: string;
  finished_at: string | null; result: Result | null; error: string | null;
}
export interface TraceEvent {
  run_id: string; invoice_id: string | null; node: string; revision: number; started_at: string;
  latency_ms: number; status: string | null; detail: Record<string, unknown>;
}
```
`src/lib/format.ts`:
```ts
export function formatMoney(value: string | null | undefined): string {
  if (value == null) return "—";
  const m = /^(-?)(\d+)(\.\d+)?$/.exec(value.trim());
  if (!m) return value;                       // never route money through Number()
  const [, sign, int, frac = ""] = m;
  return `${sign}${int.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${frac}`;
}

export function provenanceLabel(page: number | null, table: string | null, row: number | null): string {
  const parts: string[] = [];
  if (page != null) parts.push(`Page ${page}`);
  if (table) parts.push(table);
  if (row != null) parts.push(`Row ${row}`);
  return parts.join(" · ");
}

export function fieldLabel(path: string): string {
  const m = /^(items|tax_lines)\[([^\]]+)\]\.(\w+)$/.exec(path);
  if (!m) return path;
  const [, , id, attr] = m;
  return `${id.replace("_", " ")} · ${attr.replace("_", " ")}`;
}
```
`src/lib/validate.ts`:
```ts
export function validateFile(file: File, maxMb = 20): string | null {
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return "That file is not a PDF. Choose an invoice saved as a .pdf file.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > maxMb * 1024 * 1024) return `That file is larger than ${maxMb} MB.`;
  return null;
}
```
Tests `src/test/lib.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { fieldLabel, formatMoney, provenanceLabel } from "../lib/format";
import { validateFile } from "../lib/validate";

describe("formatMoney", () => {
  it("groups thousands without touching decimals", () => {
    expect(formatMoney("1014.00")).toBe("1,014.00");
    expect(formatMoney("-5.00")).toBe("-5.00");
    expect(formatMoney("12")).toBe("12");
  });
  it("is exact beyond JS safe integers", () => {
    expect(formatMoney("123456789012345678901.50")).toBe("123,456,789,012,345,678,901.50");
  });
  it("passes through junk and shows a dash for null", () => {
    expect(formatMoney("n/a")).toBe("n/a");
    expect(formatMoney(null)).toBe("—");
  });
});

describe("labels", () => {
  it("formats provenance and field paths", () => {
    expect(provenanceLabel(1, "table_01", 1)).toBe("Page 1 · table_01 · Row 1");
    expect(provenanceLabel(2, null, null)).toBe("Page 2");
    expect(fieldLabel("items[line_01].amount")).toBe("line 01 · amount");
    expect(fieldLabel("total")).toBe("total");
  });
});

describe("validateFile", () => {
  const f = (name: string, type: string, size = 10) => new File([new Uint8Array(size)], name, { type });
  it("accepts PDFs by type or extension", () => {
    expect(validateFile(f("a.pdf", "application/pdf"))).toBeNull();
    expect(validateFile(f("a.PDF", ""))).toBeNull();
  });
  it("rejects other types, empty and oversize files", () => {
    expect(validateFile(f("a.txt", "text/plain"))).toMatch(/not a PDF/);
    expect(validateFile(f("a.pdf", "application/pdf", 0))).toMatch(/empty/);
    expect(validateFile(f("a.pdf", "application/pdf", 3 * 1024 * 1024), 2)).toMatch(/larger than 2 MB/);
  });
});
```
Run `npm test` → FAIL then implement → PASS.

- [ ] **Step 3: API client and polling hook (tests first).** `src/api/client.ts`:
```ts
import type { Job, TraceEvent } from "./types";

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
  }
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function parse<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T;
  let code = "http_error", message = `Request failed (${res.status}).`;
  try {
    const body = await res.json();
    if (body && typeof body.message === "string") { code = body.code ?? code; message = body.message; }
  } catch { /* non-JSON error body */ }
  throw new ApiError(code, message, res.status);
}

export const getJob = (id: string) => fetch(`${BASE}/api/invoices/${id}`).then((r) => parse<Job>(r));
export const listJobs = (limit = 20) => fetch(`${BASE}/api/invoices?limit=${limit}`).then((r) => parse<Job[]>(r));
export const getTrace = (id: string) =>
  fetch(`${BASE}/api/invoices/${id}/trace`).then((r) => parse<TraceEvent[]>(r));

export function uploadInvoice(file: File, onProgress?: (pct: number) => void): Promise<{ job_id: string; status: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/api/invoices`);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100)); };
    xhr.onerror = () => reject(new ApiError("network", "Could not reach the server. Check your connection and try again.", 0));
    xhr.onload = () => {
      let body: any = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300 && body?.job_id) resolve(body);
      else reject(new ApiError(body?.code ?? "http_error", body?.message ?? `Upload failed (${xhr.status}).`, xhr.status));
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
```
`src/hooks/useJob.ts`:
```ts
import { useEffect, useState } from "react";
import { getJob } from "../api/client";
import type { Job } from "../api/types";

export function useJob(jobId: string | null, intervalMs = 1000) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setJob(null);
    setError(null);
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const j = await getJob(jobId);
        if (cancelled) return;
        setJob(j);
        setError(null);
        if (j.state === "QUEUED" || j.state === "RUNNING") timer = setTimeout(tick, intervalMs);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Network error");
        timer = setTimeout(tick, intervalMs * 3);          // keep trying
      }
    };
    void tick();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [jobId, intervalMs]);

  return { job, error };
}
```
Test `src/test/useJob.test.tsx`:
```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import example from "@contracts/example-job.json";
import type { Job } from "../api/types";
import { useJob } from "../hooks/useJob";

vi.mock("../api/client", () => ({ getJob: vi.fn() }));
import { getJob } from "../api/client";

const done = example as unknown as Job;
const running: Job = { ...done, state: "RUNNING", result: null, finished_at: null };

beforeEach(() => vi.mocked(getJob).mockReset());

it("polls until the job is DONE then stops", async () => {
  vi.mocked(getJob).mockResolvedValueOnce(running).mockResolvedValueOnce(running).mockResolvedValue(done);
  const { result } = renderHook(() => useJob("j1", 10));
  await waitFor(() => expect(result.current.job?.state).toBe("DONE"));
  const calls = vi.mocked(getJob).mock.calls.length;
  await new Promise((r) => setTimeout(r, 60));
  expect(vi.mocked(getJob).mock.calls.length).toBe(calls);
});

it("stops on ERROR", async () => {
  vi.mocked(getJob).mockResolvedValue({ ...running, state: "ERROR", error: "boom" });
  const { result } = renderHook(() => useJob("j1", 10));
  await waitFor(() => expect(result.current.job?.state).toBe("ERROR"));
});

it("keeps retrying after a network error and recovers", async () => {
  vi.mocked(getJob).mockRejectedValueOnce(new Error("offline")).mockResolvedValue(done);
  const { result } = renderHook(() => useJob("j1", 5));
  await waitFor(() => expect(result.current.error).toBe("offline"));
  await waitFor(() => expect(result.current.job?.state).toBe("DONE"));
});

it("does nothing without a job id", () => {
  const { result } = renderHook(() => useJob(null, 10));
  expect(result.current.job).toBeNull();
  expect(getJob).not.toHaveBeenCalled();
});
```
- [ ] **Step 4: Components (tests first).** `src/components/DropZone.tsx`:
```tsx
import { useId, useState, type DragEvent } from "react";
import { validateFile } from "../lib/validate";

interface Props { onFile: (file: File) => void; disabled?: boolean; maxMb?: number }

export function DropZone({ onFile, disabled = false, maxMb = 20 }: Props) {
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();

  const accept = (file: File | undefined) => {
    if (!file) return;
    const problem = validateFile(file, maxMb);
    setError(problem);
    if (!problem) onFile(file);
  };
  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setOver(false);
    if (!disabled) accept(e.dataTransfer.files?.[0]);
  };

  return (
    <div className="dropzone-wrap">
      <input id={inputId} className="visually-hidden" type="file" accept="application/pdf,.pdf"
        disabled={disabled}
        onChange={(e) => { accept(e.target.files?.[0]); e.target.value = ""; }} />
      <label htmlFor={inputId}
        className={`dropzone${over ? " is-over" : ""}${disabled ? " is-disabled" : ""}`}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }}
        onDragLeave={() => setOver(false)} onDrop={onDrop}>
        <span className="dropzone-title">Drop an invoice PDF</span>
        <span className="dropzone-hint">or click to choose a file · PDF up to {maxMb} MB</span>
      </label>
      {error && <p role="alert" className="field-error">{error}</p>}
    </div>
  );
}
```
`src/components/StatusBadge.tsx`:
```tsx
const COPY: Record<string, { label: string; tone: "good" | "warn" | "bad"; hint: string }> = {
  RECONCILED: { label: "Reconciled", tone: "good", hint: "Every figure now checks out." },
  UNRESOLVED: { label: "Needs review", tone: "warn", hint: "The invoice's own figures disagree and nothing in it says which is right." },
  MAX_REVISIONS_EXCEEDED: { label: "Stopped at limit", tone: "warn", hint: "The correction limit was reached before the totals matched." },
  INSUFFICIENT_EVIDENCE: { label: "Not enough evidence", tone: "warn", hint: "No correction was confident enough to apply." },
  NO_PROGRESS: { label: "No progress", tone: "warn", hint: "A correction did not change the discrepancy, so the run stopped." },
  FAILED: { label: "Could not read", tone: "bad", hint: "The invoice could not be processed." },
};

export function StatusBadge({ status }: { status: string }) {
  const c = COPY[status] ?? { label: status, tone: "warn" as const, hint: "Unrecognised status." };
  return (
    <div className={`status status-${c.tone}`} data-status={status}>
      <span className="status-mark" aria-hidden="true" />
      <div><strong>{c.label}</strong><p>{c.hint}</p></div>
    </div>
  );
}
```
`src/components/LedgerTable.tsx`:
```tsx
import type { Correction, Ledger } from "../api/types";
import { formatMoney } from "../lib/format";

interface Props { ledger: Ledger; corrections: Correction[] }

export function LedgerTable({ ledger, corrections }: Props) {
  const changed = new Map(corrections.map((c) => [c.field, c]));
  const cell = (id: string, attr: "quantity" | "unit_price" | "amount", value: string, money: boolean) => {
    const c = changed.get(`items[${id}].${attr}`);
    const shown = money ? formatMoney(value) : value;
    if (!c) return shown;
    const old = money ? formatMoney(c.old_value) : c.old_value;
    return (<><del aria-label={`was ${old}`}>{old}</del> <ins>{shown}</ins></>);
  };
  const totals: [string, string | null][] = [
    ["Subtotal", ledger.subtotal], ["Discount", ledger.discount],
    ...ledger.tax_lines.map((t): [string, string | null] => [`Tax${t.rate ? ` ${t.rate}` : ""}`, t.amount]),
    ["Shipping", ledger.shipping], ["Fees", ledger.fees], ["Total", ledger.total],
  ];
  return (
    <div className="table-scroll">
      <table className="ledger">
        <caption className="visually-hidden">Ledger for invoice {ledger.invoice_id}</caption>
        <thead><tr><th>Description</th><th className="num">Qty</th><th className="num">Unit price</th><th className="num">Amount</th></tr></thead>
        <tbody>
          {ledger.items.map((i) => (
            <tr key={i.id}>
              <td>{i.description}</td>
              <td className="num">{cell(i.id, "quantity", i.quantity, false)}</td>
              <td className="num">{cell(i.id, "unit_price", i.unit_price, true)}</td>
              <td className="num">{cell(i.id, "amount", i.amount, true)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          {totals.filter(([, v]) => v != null).map(([label, v]) => (
            <tr key={label}><th scope="row" colSpan={3}>{label}</th><td className="num">{formatMoney(v)} {label === "Total" ? ledger.currency : ""}</td></tr>
          ))}
        </tfoot>
      </table>
    </div>
  );
}
```
`src/components/Corrections.tsx`:
```tsx
import type { Correction } from "../api/types";
import { fieldLabel, formatMoney, provenanceLabel } from "../lib/format";

export function Corrections({ items }: { items: Correction[] }) {
  if (items.length === 0) return <p className="muted">No corrections were needed.</p>;
  return (
    <ul className="corrections">
      {items.map((c, i) => (
        <li key={`${c.field}-${i}`}>
          <strong>{fieldLabel(c.field)}</strong>
          <span className="change"><del>{formatMoney(c.old_value)}</del> → <ins>{formatMoney(c.new_value)}</ins></span>
          <span className="muted">{provenanceLabel(c.source_page, c.source_table, c.source_row)} · confidence {(c.confidence * 100).toFixed(0)}%</span>
        </li>
      ))}
    </ul>
  );
}
```
`src/components/Disclosure.tsx`:
```tsx
import { useState, type ReactNode } from "react";

export function Disclosure({ title, children, onOpen }: { title: string; children: ReactNode; onOpen?: () => void }) {
  const [opened, setOpened] = useState(false);
  return (
    <details className="disclosure" onToggle={(e) => {
      const open = (e.currentTarget as HTMLDetailsElement).open;
      if (open && !opened) { setOpened(true); onOpen?.(); }
    }}>
      <summary>{title}</summary>
      {opened && <div className="disclosure-body">{children}</div>}
    </details>
  );
}
```
`src/components/Trace.tsx`:
```tsx
import { useEffect, useState } from "react";
import { getTrace } from "../api/client";
import type { TraceEvent } from "../api/types";

export function Trace({ jobId }: { jobId: string }) {
  const [events, setEvents] = useState<TraceEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    getTrace(jobId).then((e) => live && setEvents(e)).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [jobId]);
  if (error) return <p role="alert" className="field-error">{error}</p>;
  if (!events) return <p className="muted">Loading trace…</p>;
  if (events.length === 0) return <p className="muted">No trace was recorded for this job.</p>;
  return (
    <ol className="trace">
      {events.map((e, i) => (<li key={i}><strong>{e.node}</strong> <span className="muted">{e.latency_ms.toFixed(1)} ms{e.status ? ` · ${e.status}` : ""}</span></li>))}
    </ol>
  );
}
```
`src/components/RecentJobs.tsx`:
```tsx
import type { Job } from "../api/types";

export function RecentJobs({ jobs, selected, onSelect }: { jobs: Job[]; selected: string | null; onSelect: (id: string) => void }) {
  if (jobs.length === 0) return null;
  return (
    <section aria-labelledby="recent-h">
      <h2 id="recent-h">Recent</h2>
      <ul className="recent">
        {jobs.map((j) => (
          <li key={j.job_id}>
            <button type="button" aria-current={selected === j.job_id ? "true" : undefined} onClick={() => onSelect(j.job_id)}>
              <span className="recent-name" title={j.filename}>{j.filename}</span>
              <span className="muted">{j.result?.status ?? j.state}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
```
`src/components/ResultView.tsx`:
```tsx
import type { Job } from "../api/types";
import { fieldLabel, formatMoney, provenanceLabel } from "../lib/format";
import { Corrections } from "./Corrections";
import { Disclosure } from "./Disclosure";
import { LedgerTable } from "./LedgerTable";
import { StatusBadge } from "./StatusBadge";
import { Trace } from "./Trace";

export function ResultView({ job }: { job: Job }) {
  if (job.state === "ERROR") {
    return <p role="alert" className="field-error">The service hit a problem processing this file: {job.error ?? "unknown error"}</p>;
  }
  const r = job.result;
  if (!r) return null;
  return (
    <article className="result" aria-label={`Result for ${job.filename}`}>
      <h2 className="result-title" title={job.filename}>{job.filename}</h2>
      <StatusBadge status={r.status} />
      {r.error && <p className="muted">{r.error}</p>}
      <p className="muted">{r.iterations} {r.iterations === 1 ? "correction round" : "correction rounds"}</p>
      {r.ledger && <LedgerTable ledger={r.ledger} corrections={r.corrections} />}
      <h3>Corrections</h3>
      <Corrections items={r.corrections} />
      <Disclosure title={`Evidence (${r.evidence.length})`}>
        <ul className="evidence">
          {r.evidence.map((e, i) => (
            <li key={i}>
              <strong>{fieldLabel(e.field)}</strong> {formatMoney(e.value)}
              <span className="muted"> {provenanceLabel(e.source.page, e.source.table_id ?? null, e.source.row ?? null)}</span>
              <pre>{e.quote}</pre>
            </li>
          ))}
        </ul>
      </Disclosure>
      <Disclosure title="Trace"><Trace jobId={job.job_id} /></Disclosure>
    </article>
  );
}
```
`src/App.tsx`:
```tsx
import { useCallback, useEffect, useState } from "react";
import { ApiError, listJobs, uploadInvoice } from "./api/client";
import type { Job } from "./api/types";
import { DropZone } from "./components/DropZone";
import { RecentJobs } from "./components/RecentJobs";
import { ResultView } from "./components/ResultView";
import { useJob } from "./hooks/useJob";

export default function App() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [recent, setRecent] = useState<Job[]>([]);
  const { job, error: pollError } = useJob(jobId);

  const refresh = useCallback(() => { listJobs().then(setRecent).catch(() => undefined); }, []);
  useEffect(refresh, [refresh]);
  useEffect(() => { if (job?.state === "DONE" || job?.state === "ERROR") refresh(); }, [job?.state, refresh]);

  const working = job?.state === "QUEUED" || job?.state === "RUNNING";
  const busy = uploadPct !== null || working;

  async function handleFile(file: File) {
    setUploadError(null);
    setJobId(null);
    setUploadPct(0);
    try {
      const r = await uploadInvoice(file, setUploadPct);
      setJobId(r.job_id);
    } catch (e) {
      setUploadError(e instanceof ApiError ? e.message : "Upload failed. Check your connection and try again.");
    } finally {
      setUploadPct(null);
    }
  }

  return (
    <main className="page">
      <header><h1>Ledger Agent</h1><p className="muted">Drop an invoice. Get a reconciled ledger and the evidence behind every correction.</p></header>
      <DropZone onFile={handleFile} disabled={busy} />
      {uploadPct !== null && (<div role="status" className="progress"><label>Uploading… <progress max={100} value={uploadPct} /></label></div>)}
      {working && <p role="status" className="progress">Reconciling… this usually takes a few seconds.</p>}
      {uploadError && <p role="alert" className="field-error">{uploadError}</p>}
      {pollError && !job && <p role="alert" className="field-error">Lost contact with the server. Retrying…</p>}
      {job && <ResultView job={job} />}
      <RecentJobs jobs={recent} selected={jobId} onSelect={setJobId} />
    </main>
  );
}
```
`src/styles/tokens.css` (starting point; refine with the design skills):
```css
:root {
  --bg: #fbfbfa; --surface: #ffffff; --ink: #16181d; --muted: #5b6270; --line: #e3e5ea;
  --accent: #1f4ed8; --good: #14683a; --warn: #8a5a00; --bad: #a02020;
  --good-bg: #e7f4ec; --warn-bg: #fbf1dc; --bad-bg: #fbe7e7;
  --radius: 10px; --space: 1rem; --font: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111317; --surface: #181b21; --ink: #eceef2; --muted: #a2a9b6; --line: #2b2f38;
    --accent: #8fa8ff; --good: #7bd8a0; --warn: #f0c36a; --bad: #ff9a9a;
    --good-bg: #14291d; --warn-bg: #2d2411; --bad-bg: #321818;
  }
}
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
```
`base.css` must define at least: `body` (bg/ink/font), `.page` (max-width ~44rem, centred, 16px side gutters, no horizontal scroll at 320px), `.visually-hidden`, `.dropzone` (dashed border, large target, `.is-over`, `.is-disabled`), `input:focus-visible + .dropzone` focus ring, `.status` + tone classes (colour **and** text), `.table-scroll{overflow-x:auto}`, `.ledger` (`.num` right-aligned tabular numbers), `del`/`ins` styling that does not rely on colour alone, `.field-error`, `.muted`, `.recent button`, long filenames truncating with ellipsis (`.recent-name`, `.result-title`: `overflow-wrap:anywhere` or ellipsis), `pre` wrapping, `details/summary` styling. Style these with impeccable/taste guidance.

Component/App tests (`src/test/ui.test.tsx`):
```tsx
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import example from "@contracts/example-job.json";
import type { Job } from "../api/types";
import App from "../App";
import { DropZone } from "../components/DropZone";
import { ResultView } from "../components/ResultView";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, uploadInvoice: vi.fn(), getJob: vi.fn(), listJobs: vi.fn(), getTrace: vi.fn() };
});
import { ApiError, getJob, getTrace, listJobs, uploadInvoice } from "../api/client";

const done = example as unknown as Job;
const pdf = () => new File(["%PDF-1.4"], "INV-001.pdf", { type: "application/pdf" });

describe("DropZone", () => {
  it("accepts a PDF chosen through the input", async () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} />);
    await userEvent.upload(screen.getByLabelText(/drop an invoice pdf/i), pdf());
    expect(onFile).toHaveBeenCalledOnce();
  });
  it("accepts a PDF dropped on the zone", () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} />);
    fireEvent.drop(screen.getByText(/drop an invoice pdf/i).closest("label")!, { dataTransfer: { files: [pdf()] } });
    expect(onFile).toHaveBeenCalledOnce();
  });
  it("rejects a non-PDF with a specific message and does not call onFile", async () => {
    const onFile = vi.fn();
    const user = userEvent.setup({ applyAccept: false });
    render(<DropZone onFile={onFile} />);
    await user.upload(screen.getByLabelText(/drop an invoice pdf/i), new File(["hi"], "notes.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not a PDF/i);
    expect(onFile).not.toHaveBeenCalled();
  });
  it("ignores drops while disabled", () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} disabled />);
    fireEvent.drop(screen.getByText(/drop an invoice pdf/i).closest("label")!, { dataTransfer: { files: [pdf()] } });
    expect(onFile).not.toHaveBeenCalled();
  });
});

describe("ResultView", () => {
  it("shows status, the correction with provenance, and the struck-through old amount", () => {
    render(<ResultView job={done} />);
    expect(screen.getByText("Reconciled")).toBeInTheDocument();
    expect(screen.getAllByText("Page 1 · table_01 · Row 1 · confidence 97%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1,040.00")[0].tagName).toBe("DEL");
    expect(screen.getAllByText("1,014.00").some((n) => n.tagName === "INS")).toBe(true);
  });
  it.each(["UNRESOLVED", "MAX_REVISIONS_EXCEEDED", "INSUFFICIENT_EVIDENCE", "NO_PROGRESS", "FAILED"])(
    "renders terminal status %s", (status) => {
      const job = { ...done, result: { ...done.result!, status, corrections: [] } } as Job;
      render(<ResultView job={job} />);
      expect(document.querySelector(`[data-status="${status}"]`)).not.toBeNull();
    });
  it("handles an unknown status without crashing", () => {                       // Review Focus 5
    const job = { ...done, result: { ...done.result!, status: "SOMETHING_NEW" } } as Job;
    render(<ResultView job={job} />);
    expect(screen.getByText("SOMETHING_NEW")).toBeInTheDocument();
  });
  it("renders a 200-row ledger and a very long filename", () => {                // Review Focus 5
    const items = Array.from({ length: 200 }, (_, i) => ({ ...done.result!.ledger!.items[0], id: `line_${i + 1}`, description: `Part ${i}` }));
    const job = { ...done, filename: "x".repeat(300) + ".pdf",
      result: { ...done.result!, corrections: [], ledger: { ...done.result!.ledger!, items } } } as Job;
    render(<ResultView job={job} />);
    expect(screen.getAllByRole("row").length).toBeGreaterThan(200);
  });
  it("shows money larger than JS safe integers exactly", () => {                  // Review Focus 5
    const ledger = { ...done.result!.ledger!, total: "123456789012345678901.50" };
    render(<ResultView job={{ ...done, result: { ...done.result!, corrections: [], ledger } } as Job} />);
    expect(screen.getByText(/123,456,789,012,345,678,901\.50/)).toBeInTheDocument();
  });
  it("explains a service ERROR distinctly from a FAILED invoice", () => {
    render(<ResultView job={{ ...done, state: "ERROR", result: null, error: "interrupted by restart" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/interrupted by restart/);
  });
  it("loads the trace only when the disclosure is opened", async () => {
    vi.mocked(getTrace).mockResolvedValue([{ run_id: "r", invoice_id: "INV-001", node: "ingest", revision: 0,
      started_at: "t", latency_ms: 1.5, status: "INGESTED", detail: {} }]);
    render(<ResultView job={done} />);
    expect(getTrace).not.toHaveBeenCalled();
    const summary = screen.getByText("Trace");
    fireEvent.click(summary);
    fireEvent(summary.closest("details")!, new Event("toggle"));
    await waitFor(() => expect(getTrace).toHaveBeenCalledWith(done.job_id));
  });
});

describe("App", () => {
  beforeEach(() => {
    vi.mocked(listJobs).mockResolvedValue([]);
    vi.mocked(getJob).mockResolvedValue(done);
    vi.mocked(uploadInvoice).mockReset();
  });
  it("uploads a dropped PDF, polls the job and shows the result", async () => {
    vi.mocked(uploadInvoice).mockResolvedValue({ job_id: done.job_id, status: "QUEUED" });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/drop an invoice pdf/i), pdf());
    expect(await screen.findByText("Reconciled")).toBeInTheDocument();
    expect(uploadInvoice).toHaveBeenCalledOnce();
  });
  it("shows the server's message when the upload is rejected", async () => {
    vi.mocked(uploadInvoice).mockRejectedValue(new ApiError("too_large", "File exceeds the 20 MB limit.", 413));
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/drop an invoice pdf/i), pdf());
    expect(await screen.findByRole("alert")).toHaveTextContent("File exceeds the 20 MB limit.");
  });
  it("lists recent jobs and opens one on click", async () => {
    vi.mocked(listJobs).mockResolvedValue([done]);
    render(<App />);
    const item = await screen.findByRole("button", { name: /INV-001\.pdf/ });
    await userEvent.click(item);
    expect(await screen.findByText("Reconciled")).toBeInTheDocument();
    expect(within(screen.getByRole("main")).getByRole("article")).toBeInTheDocument();
  });
});
```
- [ ] **Step 5:** `cd frontend && npm test` → PASS; `npm run build` → succeeds (tsc + vite). Fix real type errors; do not loosen tests.
- [ ] **Step 6: Design pass.** Run the impeccable critique/polish and taste-skill checks on the built UI (use the browser-automation skill to load `npm run preview` and look for console errors / take a screenshot at 375px and 1280px width, light and dark). Record findings and changes in the report.
- [ ] **Step 7:** commit `frontend/` (not `node_modules`, add `frontend/.gitignore` with `node_modules` and `dist`) on `stream/frontend`; push.

### Task O1: Trace sinks and logging (stream `obs-sinks`)

**Files:**
- Create: `src/ledger_agent/observability/{__init__,sinks}.py`
- Test: `tests/observability/test_sinks.py`

**Interfaces:**
- Consumes: `TraceEvent`/`TraceSink`/`ListTraceSink` (`tracing.py`), `JobStore`, `InMemoryJobStore`, `Deps`, `run_invoice`.
- Produces: `JsonLogSink(logger=None)`, `StoreTraceSink(store, job_id)`, `CompositeSink(*sinks)`, `configure_json_logging(level="INFO") -> None`.

- [ ] **Step 1: Tests** — `tests/observability/test_sinks.py`:
```python
import json
import logging

from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps, run_invoice
from ledger_agent.observability.sinks import CompositeSink, JsonLogSink, StoreTraceSink
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
```
- [ ] **Step 2:** FAIL. **Step 3: Implement** `observability/sinks.py`:
```python
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
```
`observability/__init__.py` empty. Add a README note (in the report; Wave I writes README): LangSmith tracing needs only `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in the environment.
- [ ] **Step 4:** `$PY -m pytest tests/observability -v` → PASS. **Step 5:** commit on `stream/obs-sinks`, push.

### Task O2: Evaluation harness (stream `eval`)

**Files:**
- Create: `src/ledger_agent/eval/{__init__,__main__,dataset,variants,metrics,runner,report}.py`
- Test: `tests/eval/test_eval_metrics.py`, `tests/eval/test_eval_run.py`

**Interfaces:**
- Consumes: `InvoiceSpec/ItemSpec/render_invoice`, `corrupting_builder`, `build_ledger`, `ingest_pdf`, `extract_tables`, `build_document`, `validate`, `set_field`, `Deps/run_invoice`, `build_index`, `build_query`, `HashingEmbedder`, `ChunkValueProposer`, `ValidationRules`.
- Produces: `Case`, `default_cases()`; `flatten(ledger) -> dict[str, Decimal]`, `Outcome`, `variant_metrics(outcomes) -> dict`, `retrieval_metrics(cases, mode, k) -> dict`; `run_no_rag(ledger, rules, max_revisions)`; `run_evaluation(cases=None, workdir=None) -> EvalResult`; `to_markdown(result) -> str`, `to_csv(result) -> str`; CLI `python -m ledger_agent.eval --out DIR`.

- [ ] **Step 1: Tests.** `tests/eval/test_eval_metrics.py`:
```python
from decimal import Decimal as D

import pytest

from ledger_agent.config import ValidationRules
from ledger_agent.eval.metrics import Outcome, flatten, variant_metrics
from ledger_agent.eval.variants import run_no_rag
from ledger_agent.paths import set_field
from ledger_agent.testing.ledgers import make_ledger
from ledger_agent.validation.arithmetic import validate


def test_flatten_covers_items_taxes_and_scalars():
    flat = flatten(make_ledger())
    assert flat["items[line_01].amount"] == D("1014.00")
    assert flat["tax_lines[tax_01].amount"] == D("104.40") and flat["total"] == D("1148.40")


def outcome(kind, orig, truth, final, corrections, status="RECONCILED", it=1):
    return Outcome(case="c", kind=kind, status=status, original=orig, truth=truth, final=final,
                   corrections=corrections, iterations=it, latency_ms=10.0)


def test_metrics_correct_and_false_correction():
    truth = make_ledger()
    bad = set_field(truth, "items[line_01].amount", D("1040.00"))
    wrong = set_field(truth, "items[line_01].amount", D("999.00"))
    ok = outcome("extraction_error", bad, truth, truth, 1)
    false = outcome("extraction_error", bad, truth, wrong, 1, status="MAX_REVISIONS_EXCEEDED", it=3)
    doc_err_fixed = outcome("document_error", bad, bad, truth, 1)
    abstained = outcome("document_error", bad, bad, bad, 0, status="UNRESOLVED", it=0)
    m = variant_metrics([ok, false, doc_err_fixed, abstained])
    assert m["n"] == 4 and m["correct_rate"] == 0.5          # ok + abstained
    assert m["false_correction_rate"] == 0.5                  # wrong value + fixed-the-document
    assert m["reconciled_rate"] == 0.5 and m["max_iterations"] == 3


def test_no_rag_trusts_arithmetic_even_when_the_invoice_is_right():
    # quantity was corrupted: arithmetic-repair rewrites the AMOUNT to fit the wrong quantity
    corrupted = set_field(make_ledger(), "items[line_01].quantity", D("13"))
    final, revs, status = run_no_rag(corrupted, ValidationRules(), max_revisions=3)
    assert final.items[0].quantity == D("13") and final.items[0].amount == D("1098.50")
    assert final.items[0].amount != make_ledger().items[0].amount
    assert revs >= 1


def test_no_rag_leaves_clean_ledgers_alone():
    final, revs, status = run_no_rag(make_ledger(), ValidationRules(), max_revisions=3)
    assert revs == 0 and status == "RECONCILED"
    assert validate(final, ValidationRules()) == []
```
`tests/eval/test_eval_run.py`:
```python
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
```
- [ ] **Step 2:** FAIL. **Step 3: Implement.**

`eval/dataset.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal as D

from ledger_agent.testing.invoices import InvoiceSpec, ItemSpec, default_spec


@dataclass(frozen=True)
class Case:
    name: str
    kind: str                                   # clean | extraction_error | document_error
    spec: InvoiceSpec
    corrupt: tuple[str, D] | None = None        # ledger corrupted AFTER extraction (extraction error)
    also: tuple[str, D] | None = None


def _s(name: str, **kw) -> InvoiceSpec:
    spec = default_spec(f"EV-{name}")
    for k, v in kw.items():
        setattr(spec, k, v)
    return spec


def default_cases() -> list[Case]:
    dup = [ItemSpec("Gasket", D("3"), D("10.00")) for _ in range(3)]
    doc_line = default_spec("EV-document_line_amount")
    doc_line.items[0].printed_amount = D("1040.00")
    return [
        Case("clean", "clean", _s("clean")),
        Case("line_amount", "extraction_error", _s("line_amount"), ("items[line_01].amount", D("1040.00"))),
        Case("decimal_error", "extraction_error", _s("decimal_error"), ("items[line_01].amount", D("10140.00"))),
        Case("quantity_error", "extraction_error", _s("quantity_error"), ("items[line_01].quantity", D("13"))),
        Case("unit_price_error", "extraction_error", _s("unit_price_error"), ("items[line_01].unit_price", D("845.00"))),
        Case("subtotal", "extraction_error", _s("subtotal"), ("subtotal", D("1050.00"))),
        Case("tax", "extraction_error", _s("tax"), ("tax_lines[tax_01].amount", D("100.00"))),
        Case("total", "extraction_error", _s("total"), ("total", D("1200.00"))),
        Case("duplicate_lines", "extraction_error", _s("duplicate_lines", items=dup), ("items[line_02].amount", D("99.00"))),
        Case("multi_tax", "extraction_error", _s("multi_tax", tax_rates=(D("0.05"), D("0.07"))),
             ("tax_lines[tax_02].amount", D("70.00"))),
        Case("discount", "extraction_error", _s("discount", discount=D("44.00")), ("total", D("1144.00"))),
        Case("shipping", "extraction_error", _s("shipping", shipping=D("15.00")), ("shipping", D("25.00"))),
        Case("two_errors", "extraction_error", _s("two_errors"), ("items[line_01].amount", D("1040.00")),
             also=("total", D("1200.00"))),
        Case("document_line_amount", "document_error", doc_line),
        Case("document_total", "document_error", _s("document_total", printed_total=D("1200.00"))),
        Case("document_subtotal", "document_error", _s("document_subtotal", printed_subtotal=D("1050.00"))),
    ]
```
`eval/variants.py`:
```python
from __future__ import annotations

from ledger_agent.config import ValidationRules
from ledger_agent.models import Ledger
from ledger_agent.paths import set_field
from ledger_agent.validation.arithmetic import validate

MODES = {"vector": "vector", "bm25": "bm25", "hybrid": "hybrid"}


def run_no_rag(ledger: Ledger, rules: ValidationRules, max_revisions: int) -> tuple[Ledger, int, str]:
    """No-RAG baseline: no retrieval, no evidence. Trusts arithmetic and rewrites the field a
    rule flagged to the value the rule expects. Stand-in for 'an LLM without retrieval'."""
    current, revisions = ledger, 0
    while revisions < max_revisions:
        found = validate(current, rules)
        if not found:
            return current, revisions, "RECONCILED"
        d = found[0]
        current = set_field(current, d.field, d.expected)
        revisions += 1
    return current, revisions, "RECONCILED" if not validate(current, rules) else "MAX_REVISIONS_EXCEEDED"
```
`eval/metrics.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ledger_agent.models import Ledger


def flatten(ledger: Ledger) -> dict[str, Decimal]:
    flat: dict[str, Decimal] = {}
    for it in ledger.items:
        for attr in ("quantity", "unit_price", "amount"):
            flat[f"items[{it.id}].{attr}"] = getattr(it, attr)
    for t in ledger.tax_lines:
        flat[f"tax_lines[{t.id}].amount"] = t.amount
    for name in ("subtotal", "discount", "tax", "shipping", "fees", "total"):
        value = getattr(ledger, name)
        if value is not None:
            flat[name] = value
    return flat


@dataclass
class Outcome:
    case: str
    kind: str
    status: str
    original: Ledger
    truth: Ledger
    final: Ledger | None
    corrections: int
    iterations: int
    latency_ms: float


def _correct(o: Outcome) -> bool:
    return o.final is not None and flatten(o.final) == flatten(o.truth)


def _false_correction(o: Outcome) -> bool:
    if o.final is None:
        return False
    orig, truth, final = flatten(o.original), flatten(o.truth), flatten(o.final)
    return any(final.get(k) != orig.get(k) and final.get(k) != truth.get(k) for k in set(final) | set(orig))


def variant_metrics(outcomes: list[Outcome]) -> dict:
    n = len(outcomes)
    rate = lambda pred: sum(1 for o in outcomes if pred(o)) / n if n else 0.0     # noqa: E731
    return {
        "n": n,
        "correct_rate": rate(_correct),
        "false_correction_rate": rate(_false_correction),
        "reconciled_rate": rate(lambda o: o.status == "RECONCILED"),
        "unresolved_rate": rate(lambda o: o.status in ("UNRESOLVED", "INSUFFICIENT_EVIDENCE", "NO_PROGRESS")),
        "mean_iterations": sum(o.iterations for o in outcomes) / n if n else 0.0,
        "max_iterations": max((o.iterations for o in outcomes), default=0),
        "mean_latency_ms": sum(o.latency_ms for o in outcomes) / n if n else 0.0,
    }
```
`eval/runner.py`:
```python
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
```
`eval/report.py`:
```python
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
```
`eval/__init__.py` empty. `eval/__main__.py`:
```python
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
```
- [ ] **Step 4:** `$PY -m pytest tests/eval -v` → PASS. If Hybrid does not reach `false_correction_rate == 0` or fails an extraction case, find the root cause (it may be a real core bug): report it, fix only inside `src/ledger_agent/eval/`, and escalate a core defect as BLOCKED instead of editing core files. Run `PYTHONPATH=src $PY -m ledger_agent.eval --out eval_report` once and paste the real table into the report.
- [ ] **Step 5:** commit on `stream/eval` (do not commit `eval_report/`), push.

---

## Gate between Wave P and Wave I (controller)

- [ ] Per stream: `bash scripts/review-package PLAN BASE HEAD` (BASE = the Wave-0 head), dispatch the six task reviewers **in parallel** (sonnet), run fix loops per the SDD skill (fix rounds are per stream and may also run in parallel).
- [ ] Merge the six `stream/*` branches into `feature/ui-api-persistence` one by one (`git merge --no-ff`), running `$PY -m pytest -q` after each; resolve conflicts (none expected: file ownership is disjoint).
- [ ] `cd frontend && npm ci && npm test && npm run build`; both must pass. Remove worktrees. Update `memory-bank/progress.md`; commit and push.

---

## Wave I — integration (after the merge)

### Task I1: Wire the real application (`build_app`)

**Files:**
- Create: `src/ledger_agent/api/main.py`
- Test: `tests/e2e/test_wiring.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `build_app(data_dir, *, ledger_builder=build_ledger, executor=None, max_upload_mb=20, frontend_dist=None) -> FastAPI` (Chroma at `data_dir/"chroma"`, uploads at `data_dir/"uploads"`; on construction: `store.mark_interrupted()` and `sweep_orphan_indexes(client)`); `build_app_from_env() -> FastAPI` reading `LEDGER_DATA_DIR` (default `./data`), `MAX_UPLOAD_MB` (default 20), `LEDGER_FRONTEND_DIST` (default `frontend/dist`); run with `uvicorn ledger_agent.api.main:build_app_from_env --factory --port 8000`.

- [ ] **Step 1: Test** — `tests/e2e/test_wiring.py`:
```python
from ledger_agent.api.main import build_app
from fastapi.testclient import TestClient


def test_build_app_reports_chroma_store(tmp_path):
    c = TestClient(build_app(tmp_path / "data"))
    assert c.get("/api/health").json() == {"status": "ok", "store": "chroma"}
    assert (tmp_path / "data" / "chroma").is_dir()
```
- [ ] **Step 2:** FAIL. **Step 3: Implement** `api/main.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

import chromadb
from fastapi import FastAPI

from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.api.app import create_app
from ledger_agent.extraction.ledger import build_ledger
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps
from ledger_agent.observability.sinks import CompositeSink, JsonLogSink, StoreTraceSink
from ledger_agent.retrieval.chroma_vector import chroma_vector_factory, sweep_orphan_indexes
from ledger_agent.storage.chroma_store import ChromaJobStore


def build_app(data_dir, *, ledger_builder=build_ledger, executor=None, max_upload_mb: float = 20,
              frontend_dist=None) -> FastAPI:
    data_dir = Path(data_dir)
    (data_dir / "chroma").mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(data_dir / "chroma"))
    store = ChromaJobStore(client)
    store.mark_interrupted()                 # jobs a crash left QUEUED/RUNNING must not spin forever
    sweep_orphan_indexes(client)             # per-invoice collections a crash left behind
    factory = chroma_vector_factory(client)

    def deps_factory(job_id: str) -> Deps:
        # HashingEmbedder / ChunkValueProposer keep the service offline; swap in real ones here.
        return Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer(), vector_factory=factory,
                    ledger_builder=ledger_builder,
                    trace_sink=CompositeSink(StoreTraceSink(store, job_id), JsonLogSink()))

    return create_app(store, deps_factory, max_upload_mb=max_upload_mb, upload_dir=data_dir / "uploads",
                      executor=executor, frontend_dist=frontend_dist, store_name="chroma")


def build_app_from_env() -> FastAPI:
    return build_app(os.environ.get("LEDGER_DATA_DIR", "./data"),
                     max_upload_mb=float(os.environ.get("MAX_UPLOAD_MB", "20")),
                     frontend_dist=os.environ.get("LEDGER_FRONTEND_DIST", "frontend/dist"))
```
- [ ] **Step 4:** pass. **Step 5:** commit and push.

### Task I2: End-to-end Python tests

**Files:** Test: `tests/e2e/test_e2e.py`

- [ ] **Step 1: Write the tests** (they exercise the real stack: FastAPI → thread pool → graph → Chroma store + Chroma vectors + trace sinks):
```python
import time
from decimal import Decimal as D

from fastapi.testclient import TestClient

from ledger_agent.api.main import build_app
from ledger_agent.retrieval.chroma_vector import list_index_collections
from ledger_agent.storage.base import Job
from ledger_agent.storage.chroma_store import ChromaJobStore
from ledger_agent.testing.corrupt import corrupting_builder
from ledger_agent.testing.invoices import InvoiceSpec, ItemSpec, default_spec, render_invoice

import chromadb


def wait_done(client, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/invoices/{job_id}").json()
        if job["state"] in ("DONE", "ERROR"):
            return job
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def upload(client, path, name):
    return client.post("/api/invoices", files={"file": (name, path.read_bytes(), "application/pdf")}).json()["job_id"]


def test_upload_correct_trace_and_no_leftover_collections(tmp_path):
    data = tmp_path / "data"
    app = build_app(data, ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00")))
    c = TestClient(app)
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    job = wait_done(c, upload(c, pdf, "INV-001.pdf"))
    assert job["state"] == "DONE" and job["result"]["status"] == "RECONCILED"
    assert job["result"]["corrections"][0]["new_value"] == "1014.00"
    trace = c.get(f"/api/invoices/{job['job_id']}/trace").json()
    assert [e["node"] for e in trace][:4] == ["ingest", "extract", "build_index", "build_ledger"]
    assert trace[-1]["node"] == "finalize"
    client = chromadb.PersistentClient(path=str(data / "chroma"))
    assert list_index_collections(client) == []                              # Review Focus 2


def test_failed_run_also_leaves_no_collection(tmp_path):
    data = tmp_path / "data"
    c = TestClient(build_app(data))
    spec = default_spec()
    spec.items[0].printed_amount = D("1040.00")                             # document itself wrong -> UNRESOLVED
    job = wait_done(c, upload(c, render_invoice(spec, tmp_path / "INV-002.pdf"), "INV-002.pdf"))
    assert job["result"]["status"] == "UNRESOLVED" and job["result"]["corrections"] == []
    assert list_index_collections(chromadb.PersistentClient(path=str(data / "chroma"))) == []


def test_jobs_survive_restart_and_interrupted_jobs_become_errors(tmp_path):  # Review Focus 4
    data = tmp_path / "data"
    c1 = TestClient(build_app(data))
    done_id = wait_done(c1, upload(c1, render_invoice(default_spec(), tmp_path / "A.pdf"), "A.pdf"))["job_id"]
    store = ChromaJobStore(chromadb.PersistentClient(path=str(data / "chroma")))
    store.create(Job(job_id="stuck", filename="stuck.pdf", state="RUNNING", created_at="2026-01-01T00:00:00.000+00:00"))
    c2 = TestClient(build_app(data))                                         # "restart"
    assert c2.get(f"/api/invoices/{done_id}").json()["state"] == "DONE"
    stuck = c2.get("/api/invoices/stuck").json()
    assert stuck["state"] == "ERROR" and stuck["error"] == "interrupted by restart"
    assert len(c2.get("/api/invoices").json()) >= 2


def test_orphan_collections_are_swept_at_startup(tmp_path):
    data = tmp_path / "data"
    (data / "chroma").mkdir(parents=True)
    client = chromadb.PersistentClient(path=str(data / "chroma"))
    client.create_collection("idx-deadbeefdeadbeef", embedding_function=None)
    build_app(data)
    assert list_index_collections(client) == []


def test_concurrent_uploads_keep_invoices_apart(tmp_path):                  # Review Focus 3
    c = TestClient(build_app(tmp_path / "data"))
    pdfs = {}
    for name in ("ALPHA", "BRAVO", "CHARLIE"):
        spec = InvoiceSpec(name, [ItemSpec(f"{name} part", D("2"), D("5.00"))])
        pdfs[name] = render_invoice(spec, tmp_path / f"{name}.pdf")
    ids = {name: upload(c, p, f"{name}.pdf") for name, p in pdfs.items()}
    for name, jid in ids.items():
        job = wait_done(c, jid)
        assert job["state"] == "DONE" and job["result"]["invoice_id"] == name
        assert job["result"]["ledger"]["items"][0]["description"] == f"{name} part"
```
- [ ] **Step 2:** `$PY -m pytest tests/e2e -v` → PASS. A failure here is a real integration bug: find the root cause (Chroma API drift, thread safety, dispose paths) and fix it in the owning module; add a regression test in that module's test file. **Step 3:** run the **full** suite `$PY -m pytest -q` (all areas green); commit and push.

### Task I3: Headless-browser check, docs and run scripts

**Files:** Modify `README.md`; Create `scripts/dev.ps1`, `scripts/serve.ps1`; (frontend already built)

- [ ] **Step 1: Build and serve.** `cd frontend && npm ci && npm run build`; then from the repo root (PowerShell) `$env:LEDGER_DATA_DIR="$PWD\data-demo"; .venv\Scripts\python -m uvicorn ledger_agent.api.main:build_app_from_env --factory --port 8000` in the background (FastAPI serves `frontend/dist` at `/`). Generate a demo PDF: `.venv\Scripts\python -c "from ledger_agent.testing.invoices import default_spec, render_invoice; render_invoice(default_spec(), 'demo-INV-001.pdf')"`.
- [ ] **Step 2: Browser verification** with the `browser-automation` skill against `http://localhost:8000`: assert the page title and drop zone render, there are no console errors and no failed network requests, then drive the upload. If the skill cannot set a file on the `<input type=file>`, fall back to Playwright (`cd frontend && npm i -D @playwright/test && npx playwright install chromium`, spec `frontend/e2e/upload.spec.ts` doing `page.setInputFiles('input[type=file]', '../demo-INV-001.pdf')` then expecting text "Reconciled"). Check screenshots at 375px and 1280px, light and dark. If neither tool can run in this environment, state that plainly in the report instead of claiming the UI was verified.
- [ ] **Step 3: Scripts.** `scripts/serve.ps1`: sets `LEDGER_DATA_DIR` (default `.\data`), builds the frontend if `frontend\dist` is missing, starts uvicorn on 8000. `scripts/dev.ps1`: starts uvicorn with `--reload` in a background job and `npm run dev` in `frontend/`.
- [ ] **Step 4: README.** Add: architecture diagram (browser → FastAPI → LangGraph → Chroma), quick start (`pip install -e ".[dev]"`, `npm ci`, `scripts\serve.ps1`, open http://localhost:8000), API table from the spec, where data lives (`LEDGER_DATA_DIR`), env vars (`LEDGER_DATA_DIR`, `MAX_UPLOAD_MB`, `LEDGER_FRONTEND_DIST`, optional `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY`), the evaluation command with the real table output from Task O2, test commands (`pytest`, `cd frontend && npm test`), and known limits (offline hashing embedder and arithmetic-free proposer by default; swap-in points `HashingEmbedder` / `ChunkValueProposer` in `api/main.py`; single-process thread pool).
- [ ] **Step 5:** stop the server, delete `data-demo/` and `demo-INV-001.pdf`, update `memory-bank/progress.md` (cycle-2 Definition-of-Done items now ticked with the test that proves each), commit and push.

### Task Final: Whole-branch review

- [ ] Dispatch the final reviewer (most capable model) on `feature/ui-api-persistence` vs `feature/core-loop`, with the Review Focus list, then one fix wave and one scoped re-review per the SDD skill. Probe especially: Chroma threading under concurrent jobs, dispose paths on every failure route, upload size handling (streaming vs reading into memory), CORS scope, XSS (the UI renders only text nodes; evidence `quote` is in `<pre>`), and any place money passes through `Number`/`float`.
- [ ] Collect all `Ruling:` ledger lines for the final message; delete the SDD workspace; leave the merge decision to the user.

---

## Self-Review

- **Spec coverage:** §3 decisions → W0-1/W0-2/P2; §4 seams/interfaces/HTTP contract → W0-1, W0-2, A; §5 streams → P1, P2, A, F, O1, O2, I1–I3; §6 frontend design → F (design skills mandated); §7 observability/eval → W0-1 (events), O1, O2; §8 error handling → A (limits/ERROR state), P2 (dispose/sweep), I1 (startup sweep, interrupted jobs); §9 testing → every task; §10 success criteria → I2 (+ I3 browser check).
- **Placeholders:** none; the two explicitly version-dependent Chroma calls (`configuration` vs `metadata` for the inner-product space, `where` operators / cache-clear import) name the check to perform and the fallback.
- **Type consistency:** `Job`/`JobStore` fields and `mark_interrupted` match across W0-2, P1, A, I1; `Deps.vector_factory/trace_sink/retrieval_mode` (W0-1) are the ones used by O2 (`retrieval_mode`), I1 (`vector_factory`, `trace_sink`); `TraceEvent` fields match `TraceEvent` in `frontend/src/api/types.ts` and `contracts/openapi.yaml`; money fields are strings in `example-job.json`, `types.ts` and API tests.
