# Progress

Last updated: 2026-10-02

## Process (Superpowers)
- [x] Read memory-bank requirements
- [x] Brainstorming (architectural path): scope = core loop (cycle 1); approach A (PyMuPDF-first, rank-bm25 + numpy vectors, pluggable Docling/OCR)
- [x] Spec written: `docs/superpowers/specs/2026-10-02-ledger-agent-core-design.md`
- [x] User approved spec (2026-10-02)
- [x] Plan written: `docs/superpowers/plans/2026-10-02-ledger-agent-core.md` (12 tasks)
- [x] Execution method chosen: subagent-driven-development (fresh implementer per task, controller review)
- [x] Execute: all 12 tasks done on branch `feature/core-loop`
- [x] Whole-branch review (opus) found 5 Important issues; one fix wave (6 commits, 92 tests) + scoped re-review: all addressed
- [ ] Merge decision (user)

## Build waves (cycle 1)
- [x] Wave 0 - scaffold + contracts (Task 1)
- [x] Wave 1 - extraction, validation, retrieval, fixtures (Tasks 2-6)
- [x] Wave 2 - agents, guards, graph, end-to-end scenarios (Tasks 7-11)
- [x] Task 12 - close-out: fresh full run 81 passed, 0 failed, 0 skipped, 0 warnings (1.83s); DoD audit below; README added
- [x] Whole-branch review + fix wave complete (92 passed)

## Definition of Done audit (implementation-plan.md section 22)
All tests cited were verified to exist (grep) and pass in the fresh 81-test run. [~] = partly covered.

- [x] Native PDFs are extracted without unnecessary OCR - `tests/unit/test_ingestion.py::test_native_pdf_needs_no_ocr`
- [~] Scanned pages fall back to OCR - hook only: `test_ingestion.py::test_blank_page_flagged_when_no_ocr`, `::test_blank_page_uses_ocr_backend` (fake backend), `tests/integration/test_graph.py::test_scanned_pdf_without_ocr_fails_cleanly`. Real OCR backend: cycle 2.
- [x] Tables are represented structurally - `tests/unit/test_tables.py::test_extract_default_table`, `::test_multipage_tables_get_global_ids`
- [x] Every ledger value has provenance - `tests/unit/test_ledger_builder.py::test_real_pdf_roundtrip_has_provenance`, `tests/unit/test_canonical.py::test_document_and_provenance_roundtrip`
- [x] A structured ledger is generated automatically - `test_ledger_builder.py::test_hand_built_document_matches_reference_ledger`, `::test_discount_shipping_multi_tax`, `::test_multipage_item_ids_are_global`
- [x] Arithmetic validation is deterministic - `tests/unit/test_validation.py` (`test_correct_invoice_has_no_discrepancies`, `test_wrong_line_amount`, `test_wrong_total`, `test_multiple_tax_rates`, `test_rounding_within_tolerance_passes_but_two_cents_fails`, `test_custom_total_terms`)
- [x] RAG is scoped to the current invoice - `tests/unit/test_retrieval.py::test_cross_invoice_queries_are_rejected_and_never_leak`, `::test_dispose`
- [x] BM25 and vector retrieval can operate together - `test_retrieval.py::test_modes_return_results[hybrid]` (also `[bm25]`, `[vector]`), `::test_source_row_is_in_top_k`
- [x] Audit Agent retrieves source evidence for discrepancies - `tests/unit/test_audit.py::test_line_discrepancy_yields_verified_evidence_with_source_row`, `::test_build_query_targets_the_item`
- [x] Reconciliation requires evidence - `test_audit.py::test_verifier_rejects_low_confidence_foreign_and_tampered_evidence`, `tests/unit/test_reconciliation.py::test_safety_checks_reject`, `test_graph.py::test_weak_evidence_is_insufficient`
- [x] Corrections are stored as revisions - `test_reconciliation.py::test_apply_records_revision_and_does_not_mutate_input`, `test_graph.py::test_line_amount_extraction_error_is_corrected_with_provenance` (original ledger preserved)
- [~] Validation runs after every correction - covered by graph behaviour only: `test_line_amount_extraction_error_is_corrected_with_provenance` reaches RECONCILED only via a post-patch validate; `tests/unit/test_guards.py::test_changed_signature_continues_until_revisions_exhausted`. No test asserts the reconcile->validate edge directly.
- [x] Infinite loops are impossible - `test_graph.py::test_no_progress_terminates`, `::test_max_revisions_terminates`, `::test_zero_revisions_allowed_blocks_correction`; `test_guards.py::test_no_progress_takes_priority_over_max`
- [x] Low-confidence corrections terminate safely - `test_graph.py::test_weak_evidence_is_insufficient`, `test_reconciliation.py::test_gate_rejects_nan_confidence_and_nan_threshold`, `test_audit.py::test_verifier_rejects_nan_confidence`
- [~] Final output includes evidence and revision history - `ReconciliationResult` carries `corrections`, `evidence`, `original_ledger`; tests assert corrections, provenance and original ledger (`test_line_amount_extraction_error_is_corrected_with_provenance`) but none asserts the contents of the `evidence` list.
- [x] Retrieval and correction accuracy are evaluated - `tests/eval/test_eval_metrics.py::test_metrics_correct_and_false_correction`, `tests/eval/test_eval_run.py::test_run_produces_three_variants_plus_bm25_and_hybrid_is_safest`, `::test_reports_render` (`python -m ledger_agent.eval`; table in README). Caveat: 16 synthetic cases.
- [~] No-RAG, vector-RAG, and hybrid-RAG baselines are compared - harness and results: `test_eval_run.py::test_run_produces_three_variants_plus_bm25_and_hybrid_is_safest`, `test_eval_metrics.py::test_no_rag_trusts_arithmetic_even_when_the_invoice_is_right`. Gap: `no_rag` is an arithmetic-trust stand-in, not a real LLM.
- [x] Full execution is observable through traces - `tests/observability/test_sinks.py::test_full_run_is_traced_to_log_and_store`, `tests/unit/test_seams.py::test_graph_emits_one_ordered_trace_event_per_node`, `tests/api/test_api.py::test_trace_endpoint_returns_stored_events`. Gap: LangSmith export is env-var opt-in and untested here.

## Cycle 2 (ui-api-persistence) status
Done: FastAPI service, ChromaDB persistence (jobs/events/per-invoice vectors), trace sinks, eval harness, React UI, run scripts, README. Verified in a headless browser against the real stack (clean invoice RECONCILED, wrong printed amount UNRESOLVED / "Needs review", reload and uvicorn restart keep both jobs in Recent).
- Persistence: `tests/e2e/test_e2e.py::test_jobs_survive_restart_and_interrupted_jobs_become_errors`
- No Chroma leaks: `test_e2e.py::test_upload_correct_trace_and_no_leftover_collections`, `tests/vector/test_chroma_vector.py::test_dispose_deletes_the_collection_and_is_idempotent`, `::test_sweep_removes_orphans_but_not_other_collections`
- Unsafe uploads: `tests/api/test_api.py::test_text_file_named_pdf_is_rejected_415`, `::test_oversize_upload_is_413`
- Concurrency: `test_api.py::test_concurrent_uploads_do_not_mix_invoices`, `test_e2e.py::test_concurrent_uploads_keep_invoices_apart`
Remaining gaps: real scanned-OCR backend, real-LLM adapter and embedder (offline defaults only), SQL stores, `shipping` eval case abstains for bm25/hybrid (rank>=3 confidence 0.80 < 0.90), frontend polish (XHR abort/timeout, non-JSON 413, 'Reconnecting...' hint), UI shows raw "Tax 0.1" label and lowercase reason text.

## Decisions and known limits
- 2026-10-02: Cycle 1 = core loop only. Approach A. LLM/Embedder behind protocols with offline fakes. Decimal-only money.
- Tax model: each tax rate applies to `subtotal - discount` (not compounded).
- OCR and Docling are interfaces only (`OcrBackend`, `TableExtractor`); no real OCR backend or Docling adapter ships. Scanned pages without an OCR backend end in FAILED.
- No real-LLM adapter yet: only the offline `FakeLLM` implements `LLMClient`; `HashingEmbedder` is an offline embedder, not semantic.
- claude-mem captures session observations automatically; its `observation_add` tool needs server mode (this environment runs worker mode).
- Terminal statuses: RECONCILED, UNRESOLVED, MAX_REVISIONS_EXCEEDED, INSUFFICIENT_EVIDENCE, NO_PROGRESS, plus FAILED for ingestion/extraction errors.
- `.gitignore` has an unrelated uncommitted `docs/` line; intentionally not committed in Task 12.

## Open issues
Parked for cycle 2 (final-review minors): label/amount in separate PDF text blocks, wider currency symbols, fuzzy header matching (e.g. 'Unit Price (USD)'), `low_quality` flag unused, mixed native/scanned document silently omits scanned pages (no warning recorded), headerless-continuation heuristic can ingest a same-width non-item table.

- Summary tables (Net Worth/VAT/Gross Worth) supported; multi-rate summaries drop per-rate checking.

- Currency suffixes/symbols other than a 3-letter prefix (e.g. '220.00 INR', 'Rs. 220.00' - parse_money raises on 'Rs.') are not handled in summary tables; rate row with blank VAT cell drops tax; summary labels outside column 0 unsupported.


## UI / API / persistence cycle (branch `feature/ui-api-persistence`)
- [x] Spec, plan, Wave 0 contracts, six parallel streams (job store, vector backend, API, frontend, trace sinks, eval), integration, whole-branch review (opus) + one fix wave with scoped re-review.
- Final state: 194 Python tests, 50 frontend tests, `npm run build` OK; real-browser check of upload -> result -> reload -> server restart done on port 8787.
- [ ] Merge decision (user): `feature/core-loop` and `feature/ui-api-persistence` are unmerged; remote `stream/*` branches still exist on origin.

## UI refactor cycle (mockup parity) — started 2026-10-02
Source: untracked `scripts/ledger-ui.html` mockup. Process: superpowers brainstorming (architectural path) + impeccable + taste-skill redesign.
- [x] Context explored: existing `frontend/` is single-page minimalist (rose OKLCH tokens); API serves only health/upload/get/list/trace; `PRODUCT.md` missing (impeccable init needed).
- [x] Decisions (user): full mockup parity (6 views + bulk upload + Settings); keep mockup identity but de-slop (no glass/gradients/Inter/hero stats); hash router, no new deps; no backend changes (derive or label "Preview").
- [x] Design approved in chat; spec written: `docs/superpowers/specs/2026-10-02-ui-refactor-design.md` (not yet committed)
- [x] User approved written spec (2026-10-02)
- [x] Plan written (9 tasks): `docs/superpowers/plans/2026-10-02-ui-refactor.md`; execution method chosen by user: subagent-driven-development
- [x] User approved plan; executed via subagent-driven-development on branch `feature/ui-refactor` (off `feature/ui-api-persistence` @ 4c69fa0): 9 tasks, per-task reviews + fix rounds, whole-branch opus review (6 Important) + one fix wave + scoped re-review: all addressed
- Final state (HEAD 8e5df98): 208 frontend tests (19 files), `npm run build` OK; Python untouched (194 tests); browser-verified 12 routes x 1440/768/390 x light/dark, 0 console errors / failed requests / horizontal scroll; core flow (upload -> corrected -> detail -> replay -> reload) and bulk upload verified on the real stack
- Fix: net-worth invoice layout (branch fix/net-worth-layout): Net Price/Net Worth synonyms, summary-table reader, summary chunks + provenance-aware evidence matching; real fixtures in tests/fixtures/net_worth/.
- [ ] Merge decision (user): `feature/ui-refactor` unmerged; `docs/` is gitignored locally (spec/plan not committed)
- Parked (needs backend): server-side Settings endpoints, PDF serving (Document tab is a ledger reconstruction), stats endpoint (dashboard derives from the jobs list)
- Parked (frontend minors): shared LoadError component, useJobs request-sequence guard, audit trace refetch on job completion, mb() edge cases, nodeLabel hasOwn, Google Fonts CSP/size-adjusted fallback, impeccable critique/audit/polish ran single-context (no scored snapshot)

- Cycle-3 candidates: rank-based confidence in `ChunkValueProposer` (hybrid/bm25 abstain on the `shipping` eval case), chunked-upload size bound, job pruning/pagination, async I/O in the upload handler, real LLM/embedder adapters, real OCR backend.
