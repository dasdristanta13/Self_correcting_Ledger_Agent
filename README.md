# Self-Correcting Ledger Agent

Document-scoped, evidence-grounded invoice reconciliation. A proposer (an LLM, or the offline `ChunkValueProposer`) suggests evidence-backed corrections; deterministic Python decides whether the arithmetic is right. Upload a PDF in the browser, watch the job run, and read the reconciled ledger, the corrections and the evidence behind each one.

## Architecture

```text
Browser (React/Vite SPA, served from frontend/dist)
   |  POST /api/invoices (PDF)  .  GET /api/invoices, /{id}, /{id}/trace  (polling)
   v
FastAPI  (api/app.py: validation, size/magic-byte checks, thread pool of 2)
   |  run_job -> run_invoice
   v
LangGraph core:  Validate --PASS--> Finalize
                    ^
                    +--FAIL--> Audit (hybrid RAG) -> Reconcile --> back to Validate
   |
   v
ChromaDB (PersistentClient in LEDGER_DATA_DIR/chroma)
   - jobs collection    : one record per upload, with the JSON result
   - events collection  : ordered trace events per job
   - idx-<16 hex>       : per-invoice vectors, deleted on dispose, orphans swept at startup
```

## Quick start (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
cd frontend; npm ci; cd ..
scripts\serve.ps1          # builds frontend/dist if missing, serves UI + API
# open http://localhost:8787
```

`scripts\dev.ps1` runs uvicorn with `--reload` (background job) plus the Vite dev server on http://localhost:5173, which proxies `/api` to `http://localhost:8787` (override with `VITE_API_PROXY`). Port 8787 is used instead of 8000 because 8000 is commonly taken.

No API keys and no network are needed: the default embedder and proposer are offline.

## API

| Method and path | Success | Errors |
|---|---|---|
| `GET /api/health` | `200 {"status":"ok","store":"chroma"}` | |
| `POST /api/invoices` (multipart field `file`) | `202 {"job_id","status":"QUEUED"}` | `422 missing_file` / `invalid_request` (malformed body), `415 not_a_pdf` (no `%PDF` magic; extension is ignored), `413 too_large` (over `MAX_UPLOAD_MB`), `503 unavailable` (could not queue) |
| `GET /api/invoices?limit=50` | `200` list of jobs, newest first (limit clamped to 1..200) | |
| `GET /api/invoices/{job_id}` | `200` job: `state` (`QUEUED/RUNNING/DONE/ERROR`), `result` (core status, ledger, corrections, evidence), `error` | `404 not_found` |
| `GET /api/invoices/{job_id}/trace` | `200` ordered trace events | `404 not_found` |

Every error body is `{"code": str, "message": str}`. Money is always a JSON string. `ERROR` means a service failure (including "interrupted by restart"); `result.status = FAILED` means the invoice itself could not be processed.

## Data and configuration

All state lives under `LEDGER_DATA_DIR` (default `./data`): `chroma/` (jobs, events, vectors) and `uploads/` (transient PDFs, removed after each job and swept at startup). `scripts\serve.ps1` writes `data\.gitignore` containing `*` when it creates the folder.

| Variable | Default | Meaning |
|---|---|---|
| `LEDGER_DATA_DIR` | `./data` | Data directory |
| `MAX_UPLOAD_MB` | `20` | Upload size limit |
| `LEDGER_FRONTEND_DIST` | `frontend/dist` | Built UI served at `/` |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` | unset | Optional: set `LANGSMITH_TRACING=true` plus a key to also send LangGraph traces to LangSmith |
| `VITE_API_PROXY` | `http://localhost:8787` | Vite dev-server proxy target |

Jobs left `QUEUED`/`RUNNING` by a crash become `ERROR` ("interrupted by restart") on the next start.

## Tests

```powershell
.venv\Scripts\python -m pytest        # 181 tests
cd frontend; npm test                  # 28 tests (vitest)
```

## Evaluation

```powershell
$env:PYTHONPATH="src"; .venv\Scripts\python -m ledger_agent.eval --out eval_report
```

Generates a labelled invoice set with known extraction errors and compares four variants (output also written to `eval_report/report.md` and `results.csv`). Real output:

| variant | n | correct | false-correction | reconciled | unresolved | mean iters | max iters | latency ms |
|---|---|---|---|---|---|---|---|---|
| no_rag | 16 | 62% | 38% | 81% | 0% | 1.50 | 3 | 0.3 |
| vector | 16 | 100% | 0% | 81% | 19% | 0.75 | 1 | 27.1 |
| bm25 | 16 | 94% | 0% | 75% | 25% | 0.69 | 1 | 25.9 |
| hybrid | 16 | 94% | 0% | 75% | 25% | 0.69 | 1 | 26.0 |

Retrieval of the source row (line-item cases):

| mode | n | recall@1 | recall@3 | MRR |
|---|---|---|---|---|
| vector | 6 | 100% | 100% | 1.000 |
| bm25 | 6 | 100% | 100% | 1.000 |
| hybrid | 6 | 100% | 100% | 1.000 |

`no_rag` is an arithmetic-trust baseline (no LLM, no retrieval): a stand-in for 'an LLM without retrieval'. Swap a real LLM client in later.

## Known limits

- Defaults are offline: `HashingEmbedder` (not semantic) and `ChunkValueProposer` (reads the retrieved chunk, no LLM). The swap points are in `deps_factory` in `src/ledger_agent/api/main.py`.
- Jobs run on a thread pool of 2 inside one process; there is no external queue or multi-worker coordination.
- The eval's `no_rag` variant is an arithmetic-trust stand-in for an LLM without retrieval, not a real LLM.
- `hybrid` and `bm25` abstain on the `shipping` eval case: `ChunkValueProposer` maps retrieval rank >= 3 to confidence 0.80, below the 0.90 threshold. That is a safe abstention and a cycle-3 candidate.
- Real scanned-PDF OCR and Docling are interfaces only; scanned pages without an OCR backend end in `FAILED`.
- Deferred frontend polish: XHR abort/timeout handling, a non-JSON 413 fallback, and no "Reconnecting..." hint when polling fails mid-job.

## Using the core loop from Python

```bash
pip install -e ".[dev]"   # dev extra includes pytest and reportlab (used to render test invoices)
pytest
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

Output (the first line is a PyMuPDF layout notice printed to stderr on import/first use; it is harmless):

```text
Consider using the pymupdf_layout package for a greatly improved page layout analysis.
RECONCILED after 1 revision(s)
items[line_01].amount: 1040.00 -> 1014.00 (page 1, row 1, conf 0.97)
```

Omit `ledger_builder` to run the real PDF extractor (`build_ledger`).

## Core loop internals

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

`RECONCILED`, `UNRESOLVED` (the evidence agrees with the extracted values, or a patch was rejected: needs human review), `MAX_REVISIONS_EXCEEDED`, `INSUFFICIENT_EVIDENCE`, `NO_PROGRESS`, and `FAILED` (e.g. scanned PDF with no OCR backend, or no line-item table).

See `memory-bank/progress.md` for the Definition-of-Done audit and `docs/superpowers/` for the spec and plan.
