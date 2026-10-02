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
- [ ] Whole-branch review by controller (pending), then merge decision

## Build waves (cycle 1)
- [x] Wave 0 - scaffold + contracts (Task 1)
- [x] Wave 1 - extraction, validation, retrieval, fixtures (Tasks 2-6)
- [x] Wave 2 - agents, guards, graph, end-to-end scenarios (Tasks 7-11)
- [x] Task 12 - close-out: fresh full run 81 passed, 0 failed, 0 skipped, 0 warnings (1.83s); DoD audit below; README added
- [ ] Whole-branch review (controller) - pending

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
- [ ] Retrieval and correction accuracy are evaluated - cycle 2 (retrospective evaluation metrics; only scenario tests exist)
- [ ] No-RAG, vector-RAG, and hybrid-RAG baselines are compared - cycle 2 (retrieval modes exist and are unit-tested; no comparison harness)
- [ ] Full execution is observable through traces - cycle 2 (observability; only in-state `audit_trail`/`retrieval_events`)

## Cycle 2 (deferred)
Persistence (SQLite/PostgreSQL), observability/traces (Opik/LangSmith), No-RAG vs Vector vs Hybrid baseline comparison, retrospective evaluation metrics, real scanned-OCR backend, real-LLM adapter, FastAPI.

## Decisions and known limits
- 2026-10-02: Cycle 1 = core loop only. Approach A. LLM/Embedder behind protocols with offline fakes. Decimal-only money.
- Tax model: each tax rate applies to `subtotal - discount` (not compounded).
- OCR and Docling are interfaces only (`OcrBackend`, `TableExtractor`); no real OCR backend or Docling adapter ships. Scanned pages without an OCR backend end in FAILED.
- No real-LLM adapter yet: only the offline `FakeLLM` implements `LLMClient`; `HashingEmbedder` is an offline embedder, not semantic.
- claude-mem captures session observations automatically; its `observation_add` tool needs server mode (this environment runs worker mode).
- Terminal statuses: RECONCILED, UNRESOLVED, MAX_REVISIONS_EXCEEDED, INSUFFICIENT_EVIDENCE, NO_PROGRESS, plus FAILED for ingestion/extraction errors.
- `.gitignore` has an unrelated uncommitted `docs/` line; intentionally not committed in Task 12.

## Open issues
None known; whole-branch review pending.
