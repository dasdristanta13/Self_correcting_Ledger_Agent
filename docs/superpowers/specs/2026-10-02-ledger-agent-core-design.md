# Self-Correcting Ledger Agent — Core Loop Design (Cycle 1)

Source of truth for requirements: `memory-bank/architecture.md`, `memory-bank/implementation-plan.md`. This spec fixes the scope and decisions for cycle 1.

## 1. Intent
Reconcile a single invoice PDF automatically: extract → build a structured ledger → deterministically validate → on discrepancy, retrieve evidence from *that same invoice*, propose an evidence-backed patch, re-validate; bounded and auditable. Principle: **LLM proposes, evidence supports, deterministic Python verifies (Decimal), LangGraph decides.**

## 2. Scope
**In (cycle 1):** contracts, extraction, validation, document-scoped hybrid retrieval, audit/reconcile agents with guards, LangGraph, synthetic fixtures, offline tests.
**Out (cycle 2):** PostgreSQL/SQLite persistence, Opik/LangSmith observability, No-RAG/Vector/Hybrid evaluation comparison, HTTP API, performance tuning. (The in-memory audit trail inside graph state *is* in scope.)

## 3. Decisions
- Python 3.11+, Pydantic v2, LangGraph.
- Extraction: PyMuPDF first (text, tables, bboxes). OCR and Docling are optional plug-ins behind an `Extractor`/`OcrBackend` interface; tests do not require them.
- Retrieval: `rank-bm25` + in-memory numpy vector index behind an `Embedder` protocol. Indexes are per-invoice objects with `dispose()`; every query takes `invoice_id` and filters on it.
- LLM behind `LLMClient` protocol (structured-output call). Tests use deterministic fakes; a real Anthropic adapter is a thin optional class.
- Money is `Decimal` everywhere; no float comparisons.

## 4. Components (one purpose, one interface each)
| Unit | Package | Interface | Depends on |
|---|---|---|---|
| Contracts | `models.py`, `state.py`, `config.py`, `protocols.py` | Pydantic models, `LedgerState`, enums, `LLMClient`, `Embedder` | — |
| Ingestion | `ingestion/` | `ingest(pdf) -> list[DocumentPage]`, scanned-page detection by text density | contracts |
| Tables/canonical | `ingestion/tables.py`, `extraction/canonical.py` | `build_document(pages, tables) -> Document` with provenance (doc, page, block, table, row, column, bbox) | ingestion |
| Ledger builder | `extraction/ledger.py` | `build_ledger(Document, LLMClient|None) -> Ledger`; deterministic first, LLM only for ambiguous columns/labels | canonical |
| Validation | `validation/` | `validate(Ledger, rules) -> list[Discrepancy]`; line, subtotal, discount, tax (multi-rate), shipping/fees, total; configurable formula | contracts |
| Retrieval | `retrieval/` | `build_index(Document, Embedder) -> InvoiceIndex`; `search(invoice_id, query, k) -> list[Chunk]`; chunk types: line item, header, totals, tax, discount, shipping, terms, free text | contracts |
| Audit agent | `agents/audit.py` | `audit(discrepancy, ledger, index, llm) -> list[Evidence]` | retrieval |
| Evidence verifier | `agents/audit.py` | accepts evidence only if same invoice, relevant page/table/row/field, complete, confidence ≥ threshold | contracts |
| Reconcile agent | `agents/reconciliation.py` | `propose_patch(evidence) -> Patch`; `apply_patch(ledger, patch) -> (Ledger, AuditRecord)` after safety checks | validation |
| Guards | `agents/guards.py` | max revisions, no-progress signature `(field, expected, observed, difference)`, confidence threshold | contracts |
| Graph | `graph.py` | `build_graph(deps) -> CompiledGraph`; nodes ingest, extract, index, build_ledger, validate, audit, verify_evidence, reconcile, finalize, failed | all |
| Fixtures | `tests/fixtures/`, `eval/generate.py` | reportlab generator + ground-truth JSON for the 14 error categories | — |

## 5. Data flow and control
`ingest → extract → index → build_ledger → validate`. Validate router: no discrepancies → `finalize`; discrepancies and revisions left → `audit → verify_evidence → reconcile → validate`; guard trip → `failed`. Patches are stored as revisions (`AuditRecord`: revision, field, old, new, reason, page, table, row, confidence); the original extraction is never overwritten. The index is built once per run and disposed in `finalize`/`failed`.

Terminal statuses: `RECONCILED`, `UNRESOLVED`, `MAX_REVISIONS_EXCEEDED`, `INSUFFICIENT_EVIDENCE`, `NO_PROGRESS`.

## 6. Error handling
- Patch safety checks (field exists, old value matches current state, new value type-valid, source evidence exists, confidence ≥ threshold); any failure → `UNRESOLVED`/`INSUFFICIENT_EVIDENCE`, never a guess.
- Weak/ambiguous evidence never produces a correction.
- Loop is provably bounded: revision counter increments each reconcile; no-progress signature repeat terminates.
- Extraction failure on a page → recorded in state, status `FAILED`, no partial silent ledger.

## 7. Testing
Offline, TDD. Unit: validation matrix (correct, line, subtotal, tax, total, discount, shipping, multi-tax, rounding); retrieval (top-K contains source row; **cross-invoice leakage test**); guards; patch safety. Integration (graph + fake LLM + generated PDFs): single line error → `RECONCILED` with one revision citing page/table/row; weak evidence → `INSUFFICIENT_EVIDENCE`; unfixable → `NO_PROGRESS`; revisions exhausted → `MAX_REVISIONS_EXCEEDED`; clean invoice → `RECONCILED` with zero revisions.

## 8. Build plan (parallel agents)
Wave 0 (orchestrator): scaffold + contracts. Wave 1 (parallel, disjoint dirs): A extraction, B validation, C retrieval, D fixtures. Wave 2: E agents+guards, F graph. progress.md and claude-mem updated after each wave.

## 9. Success criteria (cycle 1)
Definition-of-Done items from implementation-plan §22 that do not involve persistence, observability or baselines: native PDFs without OCR; scanned fallback hook; structural tables; provenance on every ledger value; deterministic validation; per-invoice scoped RAG; BM25+vector together; evidence-required reconciliation; revisions stored; validation after every correction; no infinite loops; low-confidence terminates safely; final output includes evidence and revision history.
