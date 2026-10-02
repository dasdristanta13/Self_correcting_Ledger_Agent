# Progress

Last updated: 2026-10-02

## Process (Superpowers)
- [x] Read memory-bank requirements
- [x] Brainstorming (architectural path): scope = core loop (cycle 1); approach A (PyMuPDF-first, rank-bm25 + numpy vectors, pluggable Docling/OCR)
- [x] Spec written: `docs/superpowers/specs/2026-10-02-ledger-agent-core-design.md`
- [x] User approved spec (2026-10-02)
- [x] Plan written: `docs/superpowers/plans/2026-10-02-ledger-agent-core.md` (12 tasks)
- [ ] **User reviews plan + picks execution method** ← current gate
- [ ] Execute (subagent-driven-development)

## Build waves (cycle 1)
- [ ] Wave 0 — scaffold + contracts (orchestrator)
- [ ] Wave 1 — A extraction | B validation | C retrieval | D fixtures (parallel)
- [ ] Wave 2 — E agents+guards | F graph
- [ ] Final review (requesting-code-review) + DoD check

## Cycle 2 (deferred)
Persistence (SQLite/PostgreSQL), observability (Opik/LangSmith), No-RAG vs Vector vs Hybrid eval, FastAPI.

## Decisions
- 2026-10-02: Cycle 1 = core loop only. Approach A. LLM/Embedder behind protocols with offline fakes. Decimal-only money. No git repo → agents get disjoint directories.

## Open issues
None.
