# UI, API, Chroma Persistence and Cycle-2 Observability/Eval — Design

Builds on `docs/superpowers/specs/2026-10-02-ledger-agent-core-design.md` (core loop, merged on branch `feature/core-loop`, 92 tests). Requirements source for deferred items: `memory-bank/implementation-plan.md` §14–§20.

## 1. Intent
Make the reconciliation agent usable and observable: a user drags an invoice PDF onto a minimal web page, the backend reconciles it through the existing LangGraph loop, every job/result/audit/trace is persisted, and an evaluation harness quantifies No-RAG vs Vector-RAG vs Hybrid-RAG. Correctness rules from the core spec are unchanged: LLM proposes, evidence supports, deterministic Python verifies; retrieval is invoice-scoped.

## 2. Scope
**In:** (1) `VectorStore` seam + Chroma vector backend, (2) Chroma persistence of jobs/results/audit trail/trace events, (3) FastAPI service, (4) React/Vite frontend with drag-and-drop upload, (5) observability (trace events, structured logging, LangSmith via env), (6) evaluation harness + report, (7) integration + end-to-end test.
**Out:** auth/multi-tenant, real OCR backend, real-LLM adapter (stays pluggable behind `LLMClient`), cross-invoice searchable history (explicitly rejected: it contradicts the core spec's per-invoice isolation), Docling, deployment/Docker.

## 3. Decisions
- **ChromaDB is both persistence and vector backend** (user decision). Persistence: records live in dedicated collections. Vectors: one Chroma collection per invoice, named from `invoice_id`+run id, **deleted on `dispose()`**; the `invoice_id` scope guard in `InvoiceIndex` is unchanged and still tested.
- Chroma stores records with an explicit dummy embedding (`[0.0]`) and no embedding function, so nothing is downloaded and no network is needed. Real chunk embeddings always come from our `Embedder` and are passed explicitly.
- Frontend: Vite + React + TypeScript, plain CSS design tokens, npm. Design skills: impeccable (design/critique/polish) and taste-skill (anti-generic styling).
- API: FastAPI, async job model (`POST` returns a job id; UI polls). Job execution in a background thread pool; the graph is synchronous.
- Defaults stay offline: `HashingEmbedder`, `ChunkValueProposer`. Chroma path is configurable (`LEDGER_DATA_DIR`, default `./data`).
- Branching: integration branch `feature/ui-api-persistence` (off `feature/core-loop`); parallel streams work in separate git worktrees on `stream/<name>` branches and merge into the integration branch.

## 4. Contracts (frozen in Wave 0, before parallel work)
**Seams added to the existing core (small, in `graph.py`, `retrieval/hybrid.py`):**
- `Deps.vector_factory: Callable[[str, list[Chunk], Embedder], VectorIndexLike]` — default builds the existing numpy `VectorIndex`. `VectorIndexLike` = `.scores(query) -> list[float]` (aligned to chunk order) and `.dispose()`.
- `Deps.trace_sink: TraceSink` — default `NullTraceSink`. `TraceSink.emit(event: TraceEvent)`.
- `Deps.retrieval_mode: Literal["hybrid","bm25","vector"] = "hybrid"` — passed to `InvoiceIndex.search`; used by the evaluation variants.
- Every graph node emits one `TraceEvent` through the sink (see §7).

**Storage interfaces (`ledger_agent/storage/base.py`):** `JobStore` with `create(job)`, `update(job_id, **fields)`, `get(job_id)`, `list(limit)`, `append_events(job_id, events)`, `get_events(job_id)`; `InMemoryJobStore` is the reference implementation and the default in tests.

**HTTP contract (`contracts/openapi.yaml` + `contracts/example-job.json`):**
| Endpoint | Behaviour |
|---|---|
| `POST /api/invoices` (multipart `file`) | 202 `{job_id, status: "QUEUED"}`; 415 if not a PDF (magic bytes `%PDF`, not just extension); 413 over `MAX_UPLOAD_MB` (default 20); 422 if no file |
| `GET /api/invoices/{job_id}` | `Job` (below); 404 unknown |
| `GET /api/invoices?limit=` | recent jobs, newest first |
| `GET /api/invoices/{job_id}/trace` | list of `TraceEvent` |
| `GET /api/health` | `{status:"ok", store:"chroma"|"memory"}` |

`Job = {job_id, filename, state: QUEUED|RUNNING|DONE|ERROR, created_at, finished_at|null, result: Result|null, error|null}`. `Result = {invoice_id, status (RECONCILED|UNRESOLVED|MAX_REVISIONS_EXCEEDED|INSUFFICIENT_EVIDENCE|NO_PROGRESS|FAILED), iterations, ledger, original_ledger, corrections[], evidence[], error}`; all money values are **strings** (Decimal-safe). `state=ERROR` means the service itself failed; `result.status=FAILED` means the invoice could not be processed.

## 5. Streams (disjoint file ownership → safe parallelism)
| Stream | Owns | Deliverable |
|---|---|---|
| **P — Persistence** | `src/ledger_agent/storage/chroma_store.py`, `retrieval/chroma_vector.py` | `ChromaJobStore` (collections `jobs`, `events`; JSON in documents, flat metadata for filtering); `ChromaVectorIndex` + `chroma_vector_factory`; persistent client at `LEDGER_DATA_DIR`; contract tests shared with `InMemoryJobStore`; scope/dispose tests |
| **A — API** | `src/ledger_agent/api/` | FastAPI app factory `create_app(store, deps_factory)`, upload validation, background runner, DTO mapping, CORS for `localhost:5173`, optional static mount of `frontend/dist`; tested with `TestClient` + `InMemoryJobStore` |
| **F — Frontend** | `frontend/` | Vite/React/TS app: drop zone (drag + click, PDF only, size check), upload with progress, job polling, result view; Vitest component tests with a mocked API built from `contracts/example-job.json`; designed with impeccable + taste-skill |
| **O — Observability & eval** | `src/ledger_agent/observability/`, `src/ledger_agent/eval/` | `JsonLogSink`, `StoreTraceSink`, run/latency fields; eval dataset runner over the synthetic error set; No-RAG / Vector / Hybrid variants; metrics + Markdown/CSV report CLI |
| **I — Integration** (after P, A, F, O merged) | `tests/e2e/`, `README.md`, `Makefile`/scripts | wire `create_app` with `ChromaJobStore` + `ChromaVectorIndex`; e2e pytest (real PDF → API → result persisted → trace readable, restart-safe); headless browser check of the UI upload flow |

Wave 0 (orchestrator, sequential): the seams, interfaces, `InMemoryJobStore`, OpenAPI + example fixtures, dependency additions (`chromadb`, `fastapi`, `uvicorn`, `python-multipart`, `httpx`). Existing 92 tests must stay green.

## 6. Frontend design (minimalist)
Single page, one column, generous whitespace. Header with product name only. Centered drop zone (dashed border, clear focus ring, keyboard-activatable file input); on drop → filename chip + indeterminate progress → status. Result panel: large status badge (colour + text + icon, never colour alone), "iterations" count, ledger table (description, qty, unit price, amount) with corrected cells marked, a "Corrections" list (field, old → new, `Page 1 · table_01 · Row 1`, confidence), an "Evidence" disclosure, and a "Trace" disclosure. Recent jobs list below. Light/dark via CSS tokens; WCAG AA contrast; responsive to phone width; respects `prefers-reduced-motion`. Error states: wrong file type, too large, network failure, job ERROR/FAILED each get specific copy. Typeface, spacing and colour chosen with the design skills; no component library.

## 7. Observability and evaluation
**TraceEvent** = `{run_id, invoice_id, node, revision, started_at, latency_ms, status, detail}` where `detail` carries node-specific fields from §15 of the implementation plan (retrieval query, retrieved chunk ids + scores, discrepancies count, corrections, validation result, final status). `JsonLogSink` writes one JSON log line per event; `StoreTraceSink` appends to the job's events; LangSmith tracing works through its standard environment variables with no code (documented in README). Opik is not integrated (YAGNI).

**Evaluation:** dataset = synthetic invoices from `ledger_agent.testing.invoices` covering: line multiplication, subtotal, tax, grand total, duplicate lines, decimal-point error, quantity error, unit-price error, multi-tax, discount, shipping, and invoices that are themselves wrong. Two error sources: **extraction errors** (ledger corrupted after extraction; ground truth = clean ledger) and **document errors** (printed invoice wrong; correct outcome = not "corrected"). Variants: **No-RAG** (baseline proposer that trusts arithmetic: sets the observed value to the expected one with no retrieval), **Vector-RAG** (`retrieval_mode="vector"`), **Hybrid-RAG** (`"hybrid"`; BM25-only is reported as an extra row). Metrics: correction accuracy (final ledger == ground truth), false-correction rate (a correct field changed, or a document error "fixed"), reconciliation/unresolved rate, mean/max iterations, retrieval Recall@K and MRR of the source row, latency. Output: Markdown + CSV table; headline = false-correction rate and evidence-backed correction accuracy.

## 8. Error handling
Upload validation errors are 4xx with a machine-readable `{code, message}`. The runner catches all exceptions: job → `ERROR` with a message, never an unhandled 500 from a worker thread. Chroma unavailable at startup → the app refuses to start with a clear error; transient write failure → job `ERROR`. Chroma collections created for a run are deleted in `finalize`/`failed` and by a startup sweep of orphaned `idx-*` collections. Temp upload files are deleted after the run. Duplicate uploads create separate jobs (no dedupe).

## 9. Testing
Python: contract test suite parameterised over `InMemoryJobStore` and `ChromaJobStore` (tmp dir); `ChromaVectorIndex` parity with the numpy index on rankings for the existing retrieval fixtures, plus leakage and dispose tests; API tests (valid PDF, non-PDF, oversize, unknown job, concurrent jobs, restart persistence); trace emission tests (one event per node, ordered); eval harness smoke test asserting the report's columns and that Hybrid's false-correction rate ≤ No-RAG's on the dataset. Frontend: Vitest + Testing Library (drop zone accepts PDF / rejects others, progress, result rendering for each terminal status, error states) and a headless-browser check (browser-automation skill) of the built app against the running API. Everything runs offline.

## 10. Success criteria
User drags `INV-001.pdf` onto the page and sees a RECONCILED result with correction provenance; refreshing the page or restarting the server keeps the job and its trace; `pytest` and `npm test` pass; the eval report prints the three-variant table; per-invoice Chroma collections are gone after each run; cross-invoice retrieval is still impossible.
