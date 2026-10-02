# Self-Correcting Ledger Agent

Document-scoped, evidence-grounded invoice reconciliation. An LLM (or any proposer) suggests evidence-backed corrections; deterministic Python decides whether the arithmetic is right. Cycle 1 (this branch) implements the core loop with offline fakes.

## Quick start

```bash
pip install -e ".[dev]"
pytest            # 81 tests
```

```python
from decimal import Decimal
from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps, run_invoice
from ledger_agent.testing.corrupt import corrupting_builder
from ledger_agent.testing.invoices import default_spec, render_invoice

pdf = render_invoice(default_spec(), "INV-001.pdf")
# Simulate an extraction error: line_01 amount read as 1040.00 instead of 1014.00
deps = Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer(),
            ledger_builder=corrupting_builder("items[line_01].amount", Decimal("1040.00")))
res = run_invoice(str(pdf), deps)
print(res.status.value, "after", res.iterations, "revision(s)")
for c in res.corrections:
    print(f"{c.field}: {c.old_value} -> {c.new_value} (page {c.source_page}, row {c.source_row}, conf {c.confidence:.2f})")
```

Output:

```text
RECONCILED after 1 revision(s)
items[line_01].amount: 1040.00 -> 1014.00 (page 1, row 1, conf 0.97)
```

Omit `ledger_builder` to run the real PDF extractor (`build_ledger`).

## Architecture

```text
Incoming PDF -> Ingestion -> Text + Table Extraction -> Canonical Document
                                   |-- Structured Ledger
                                   +-- Ephemeral hybrid RAG index (BM25 + vectors, per invoice)

LangGraph:  Validate --PASS--> Finalize
               ^
               +--FAIL--> Audit -> Reconcile --> back to Validate
```

Guards (max revisions, no-progress signature, evidence confidence) bound the loop. Every correction is stored as a revision with page/table/row provenance; the original ledger is preserved.

## Terminal statuses

`RECONCILED`, `UNRESOLVED` (invoice itself is inconsistent), `MAX_REVISIONS_EXCEEDED`, `INSUFFICIENT_EVIDENCE`, `NO_PROGRESS`, and `FAILED` (e.g. scanned PDF with no OCR backend, or no line-item table).

## Cycle 2 (not yet implemented)

Persistence (SQLite/PostgreSQL), observability/traces, No-RAG vs vector vs hybrid baseline comparison, retrospective evaluation metrics, real scanned-OCR backend (OCR/Docling are interfaces only), real-LLM adapter, FastAPI.

See `memory-bank/progress.md` for the Definition-of-Done audit and `docs/superpowers/` for the spec and plan.
