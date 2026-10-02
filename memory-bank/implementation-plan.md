# Self-Correction Ledger Agent --- Implementation Plan

## 1. Implementation Objective

Build a production-oriented LangGraph workflow that accepts an invoice
PDF, extracts text and tables, constructs a structured ledger, creates a
document-scoped hybrid RAG index, validates arithmetic, retrieves raw
evidence for discrepancies, proposes corrections, and iteratively
re-validates until reconciliation or bounded failure.

Target execution model:

``` text
PDF → Extract → Index → Ledger → Validate
                                  │
                         ┌────────┴────────┐
                        PASS              FAIL
                         │                  │
                      Finalize            Audit
                                            ↓
                                        Reconcile
                                            ↓
                                         Validate
```

------------------------------------------------------------------------

## 2. Phase 0 --- Repository Setup

Suggested structure:

``` text
self-correction-ledger/
├── pyproject.toml
├── README.md
├── .env.example
├── configs/
│   └── default.yaml
├── src/
│   └── ledger_agent/
│       ├── __init__.py
│       ├── config.py
│       ├── state.py
│       ├── graph.py
│       ├── ingestion/
│       │   ├── pdf.py
│       │   ├── ocr.py
│       │   └── tables.py
│       ├── extraction/
│       │   ├── canonical.py
│       │   └── ledger.py
│       ├── retrieval/
│       │   ├── chunks.py
│       │   ├── bm25.py
│       │   ├── vector.py
│       │   └── hybrid.py
│       ├── agents/
│       │   ├── extraction.py
│       │   ├── audit.py
│       │   └── reconciliation.py
│       ├── validation/
│       │   ├── arithmetic.py
│       │   └── rules.py
│       └── persistence/
│           └── audit.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── notebooks/
```

------------------------------------------------------------------------

# 3. Phase 1 --- PDF Ingestion

## Goal

Determine whether each page is native or scanned and extract the raw
document efficiently.

### Tasks

1.  Load PDF using PyMuPDF.
2.  Extract page text.
3.  Calculate text density.
4.  Detect pages requiring OCR.
5.  Extract page metadata.
6.  Preserve bounding boxes.
7.  Run OCR only on scanned pages.

### Deliverable

A `DocumentPage` model:

``` python
class DocumentPage(BaseModel):
    page_number: int
    text: str
    blocks: list[dict]
    is_ocr: bool
```

### Acceptance criteria

-   Native PDFs require no OCR.
-   Scanned pages are automatically detected.
-   Page numbers are preserved.
-   Bounding boxes are retained.

------------------------------------------------------------------------

# 4. Phase 2 --- Table Extraction

## Goal

Extract invoice tables without flattening their structure.

### Tasks

1.  Detect tables.
2.  Extract headers.
3.  Extract rows and cells.
4.  Normalize whitespace.
5.  Preserve cell coordinates.
6.  Associate each table with its page.
7.  Detect whether extraction quality is sufficient.
8.  Send ambiguous tables to fallback extraction.

### Canonical table model

``` python
class TableCell(BaseModel):
    value: str
    row: int
    column: int
    bbox: list[float]

class DocumentTable(BaseModel):
    table_id: str
    page: int
    headers: list[str]
    cells: list[TableCell]
    bbox: list[float]
```

### Acceptance criteria

For a known invoice fixture, expected rows and columns are recovered
with high accuracy.

------------------------------------------------------------------------

# 5. Phase 3 --- Canonical Document

## Goal

Create a unified representation independent of the extraction backend.

Example:

``` python
{
    "document_id": "INV-123",
    "pages": [...],
    "tables": [...],
    "text_blocks": [...]
}
```

### Important requirement

Every extracted value must have provenance.

Minimum metadata:

``` text
document_id
page
block_id
table_id
row_id
column
bbox
```

### Acceptance criteria

Given any ledger value, the system can locate the source page and table
row.

------------------------------------------------------------------------

# 6. Phase 4 --- Ledger Extraction

## Goal

Convert the canonical document into a structured invoice ledger.

### Pydantic models

``` python
class LineItem(BaseModel):
    id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    source: dict

class Ledger(BaseModel):
    invoice_id: str
    currency: str
    items: list[LineItem]
    subtotal: Decimal | None
    discount: Decimal | None
    tax: Decimal | None
    shipping: Decimal | None
    total: Decimal
```

### Extraction strategy

Use deterministic extraction wherever the table structure is reliable.

Use an LLM/VLM only for:

-   ambiguous columns
-   unusual layouts
-   semantic field mapping
-   missing labels
-   difficult OCR interpretation

### Acceptance criteria

The extracted ledger conforms to the Pydantic schema and all monetary
fields retain provenance.

------------------------------------------------------------------------

# 7. Phase 5 --- Document-Scoped RAG

## Goal

Create a temporary retrieval layer for the current invoice.

### Step 1 --- Generate retrieval chunks

For each line item:

``` text
Invoice INV-123 | Page 2 | Table 1 | Row 7

Description: Industrial Filter
Quantity: 12
Unit Price: 84.50 USD
Amount: 1014.00 USD
```

Also create chunks for:

-   invoice header
-   totals
-   taxes
-   discounts
-   shipping
-   payment terms
-   relevant free text

### Step 2 --- Build lexical index

Use BM25 for exact and lexical retrieval.

### Step 3 --- Build vector index

Embed retrieval chunks.

### Step 4 --- Add metadata

Every record must include:

``` text
invoice_id
page
table_id
row_id
field
```

### Step 5 --- Hybrid retrieval

``` text
query
 ↓
BM25 ─────┐
          ├── merge/rerank → top K
Vector ───┘
```

### Acceptance criteria

Given a discrepancy referring to a line item, the correct source row
appears in top-K retrieval results.

------------------------------------------------------------------------

# 8. Phase 6 --- Validation Engine

## Goal

Create deterministic invoice validation rules.

### Line validation

``` python
expected = quantity * unit_price
```

### Subtotal

``` python
expected = sum(item.amount for item in items)
```

### Total

Support configurable formulas:

``` text
subtotal
- discount
+ tax
+ shipping
+ fees
= total
```

### Monetary arithmetic

Use:

``` python
from decimal import Decimal
```

Never rely on binary floating-point equality for money.

### Discrepancy model

``` python
class Discrepancy(BaseModel):
    field: str
    expected: Decimal
    observed: Decimal
    difference: Decimal
    rule: str
```

### Acceptance criteria

Unit tests cover:

-   correct invoices
-   incorrect line amounts
-   incorrect subtotal
-   incorrect tax
-   incorrect grand total
-   discounts
-   shipping
-   multiple tax rates
-   rounding differences

------------------------------------------------------------------------

# 9. Phase 7 --- LangGraph State

Create the graph state:

``` python
class LedgerState(TypedDict):
    invoice_id: str
    raw_document: str
    document: dict
    ledger: dict

    discrepancies: list[dict]
    audit_evidence: list[dict]
    proposed_corrections: list[dict]

    revision: int
    max_revisions: int

    status: str
```

Recommended statuses:

``` text
INGESTED
EXTRACTED
INDEXED
VALIDATING
AUDITING
RECONCILING
RECONCILED
UNRESOLVED
FAILED
```

------------------------------------------------------------------------

# 10. Phase 8 --- Implement the Graph

Graph nodes:

``` text
ingest
extract
index
build_ledger
validate
audit
verify_evidence
reconcile
finalize
failed
```

Graph:

``` python
graph.add_edge(START, "ingest")
graph.add_edge("ingest", "extract")
graph.add_edge("extract", "index")
graph.add_edge("index", "build_ledger")
graph.add_edge("build_ledger", "validate")
```

Validation router:

``` text
validate
 ├── no discrepancies → finalize
 ├── discrepancies + revisions available → audit
 └── max revisions → failed
```

Then:

``` text
audit
 ↓
verify_evidence
 ↓
reconcile
 ↓
validate
```

------------------------------------------------------------------------

# 11. Phase 9 --- Audit Agent

## Input

``` text
invoice_id
ledger
discrepancy
```

## Process

1.  Convert discrepancy into a retrieval query.
2.  Apply invoice metadata filter.
3.  Run BM25.
4.  Run vector search.
5.  Merge/rerank results.
6.  Present top evidence to the LLM.
7.  Extract proposed evidence.
8.  Validate evidence provenance.

### Output

``` json
{
  "field": "items[line_07].amount",
  "value": 1014.00,
  "source": {
    "page": 2,
    "table": 1,
    "row": 7
  },
  "confidence": 0.97
}
```

### Acceptance criteria

The agent should not produce a correction without identifiable source
evidence.

------------------------------------------------------------------------

# 12. Phase 10 --- Reconciliation Agent

The Reconciliation Agent converts validated evidence into a patch.

``` json
{
  "operation": "UPDATE",
  "path": "items[line_07].amount",
  "old_value": 1040.00,
  "new_value": 1014.00,
  "reason": "Source invoice evidence",
  "source_page": 2,
  "confidence": 0.97
}
```

### Safety checks

Before applying:

``` text
field exists
old value matches current state
new value has valid type
source evidence exists
confidence >= threshold
```

If any check fails, terminate as unresolved.

------------------------------------------------------------------------

# 13. Phase 11 --- Self-Correction Loop

Implement three guards.

## Guard 1 --- Maximum revisions

``` text
MAX_REVISIONS = 3
```

## Guard 2 --- No-progress detection

Compare discrepancy signatures:

``` text
(field, expected, observed, difference)
```

If the same signature persists, stop.

## Guard 3 --- Evidence confidence

Example:

``` text
confidence >= 0.90
```

The threshold should be configurable.

### Termination states

``` text
RECONCILED
UNRESOLVED
MAX_REVISIONS_EXCEEDED
INSUFFICIENT_EVIDENCE
NO_PROGRESS
```

------------------------------------------------------------------------

# 14. Phase 12 --- Audit Trail

Persist every correction.

Example:

``` json
{
  "invoice_id": "INV-123",
  "revision": 1,
  "field": "items[line_07].amount",
  "old_value": 1040.00,
  "new_value": 1014.00,
  "reason": "Source invoice evidence",
  "page": 2,
  "table": 1,
  "row": 7,
  "confidence": 0.97
}
```

Recommended persistence:

``` text
PostgreSQL
```

Store:

-   invoice metadata
-   extraction result
-   validation results
-   retrieval events
-   corrections
-   final state

------------------------------------------------------------------------

# 15. Phase 13 --- Observability

Instrument every graph node.

Track:

``` text
graph_run_id
invoice_id
node
revision
latency
retrieval_query
retrieved_documents
retrieval_scores
discrepancies
corrections
validation_result
final_status
```

Use:

``` text
Opik or LangSmith
```

for traces and agent evaluation.

------------------------------------------------------------------------

# 16. Phase 14 --- Evaluation Dataset

Create synthetic invoices with controlled errors.

### Error categories

  Category              Example
  --------------------- ----------------------------
  Line multiplication   Qty × price mismatch
  Subtotal              Incorrect sum
  Tax                   Wrong tax
  Total                 Incorrect grand total
  Missing line          Line omitted
  Duplicate line        Line repeated
  OCR error             1000 → 10000
  Decimal error         12.50 → 1250
  Quantity error        2 → 3
  Unit price error      500 → 5000
  Multiple tax rates    Mixed tax
  Discount              Wrong discount application
  Shipping              Missing shipping
  Ambiguous layout      Difficult table

------------------------------------------------------------------------

# 17. Phase 15 --- Evaluation Metrics

Track at least:

### Extraction

``` text
field extraction accuracy
table extraction accuracy
OCR accuracy
```

### Retrieval

``` text
Recall@K
MRR
source-row retrieval accuracy
```

### Validation

``` text
discrepancy detection rate
false-positive rate
```

### Correction

``` text
correction accuracy
evidence-backed correction accuracy
false-correction rate
```

### Agent loop

``` text
reconciliation success rate
average iterations
maximum iterations
unresolved rate
```

The most important safety metric is:

> Evidence-backed correction accuracy.

A system that reconciles every invoice by changing values
indiscriminately is not successful.

------------------------------------------------------------------------

# 18. Phase 16 --- Baseline and Ablation

Run three versions.

## Baseline A --- No RAG

``` text
PDF
 ↓
LLM
 ↓
Correction
 ↓
Validation
```

## Baseline B --- Vector RAG

``` text
PDF
 ↓
Vector retrieval
 ↓
LLM correction
 ↓
Validation
```

## Final --- Hybrid RAG

``` text
PDF
 ↓
BM25 + Vector
 ↓
Evidence validation
 ↓
LLM correction
 ↓
Deterministic validation
```

Compare:

``` text
retrieval accuracy
correction accuracy
false correction rate
iterations
latency
cost
```

This gives the project a measurable technical contribution instead of
simply demonstrating an agent loop.

------------------------------------------------------------------------

# 19. Phase 17 --- Performance Optimization

Optimize in this order:

1.  Avoid OCR for native PDFs.
2.  Extract and index the invoice once.
3.  Reuse the ephemeral index throughout the graph run.
4.  Retrieve only top-K evidence.
5.  Use deterministic validation before invoking an LLM.
6.  Route only ambiguous extraction to an LLM/VLM.
7.  Cache embeddings within the document lifetime.
8.  Use smaller models for classification/extraction where adequate.
9.  Keep prompts focused on the discrepancy.
10. Terminate early on no-progress cases.

------------------------------------------------------------------------

# 20. Phase 18 --- Production API

Expose the workflow through an API.

Example:

``` text
POST /invoices/reconcile
```

Input:

``` text
multipart/form-data
invoice: invoice.pdf
```

Response:

``` json
{
  "invoice_id": "INV-123",
  "status": "RECONCILED",
  "iterations": 1,
  "ledger": {},
  "corrections": [],
  "evidence": []
}
```

For asynchronous processing:

``` text
POST /invoices
    ↓
job_id
    ↓
GET /invoices/{job_id}
```

------------------------------------------------------------------------

# 21. Suggested Implementation Order

Build vertically rather than implementing every subsystem independently.

## Milestone 1 --- Deterministic core

``` text
PDF
 ↓
PyMuPDF
 ↓
Manual/structured ledger
 ↓
Validation
```

Goal: reliably detect arithmetic errors.

## Milestone 2 --- Real extraction

``` text
PDF
 ↓
Text + table extraction
 ↓
Pydantic ledger
 ↓
Validation
```

Goal: automatically build the ledger.

## Milestone 3 --- Document-scoped RAG

``` text
PDF
 ↓
Chunks
 ↓
BM25 + vector
 ↓
Evidence retrieval
```

Goal: retrieve the exact source row.

## Milestone 4 --- LangGraph

``` text
Extract
 ↓
Validate
 ↓
Audit
 ↓
Reconcile
 ↓
Validate
```

Goal: complete autonomous loop.

## Milestone 5 --- Guardrails

Add:

``` text
max revisions
no-progress detection
confidence threshold
evidence verification
```

## Milestone 6 --- Observability

Add:

``` text
Opik/LangSmith
PostgreSQL
structured logging
```

## Milestone 7 --- Evaluation

Build the synthetic error dataset and compare:

``` text
No RAG
vs
Vector RAG
vs
Hybrid RAG
```

------------------------------------------------------------------------

# 22. Definition of Done

The first production-quality version is complete when:

-   [ ] Native PDFs are extracted without unnecessary OCR.
-   [ ] Scanned pages fall back to OCR.
-   [ ] Tables are represented structurally.
-   [ ] Every ledger value has provenance.
-   [ ] A structured ledger is generated automatically.
-   [ ] Arithmetic validation is deterministic.
-   [ ] RAG is scoped to the current invoice.
-   [ ] BM25 and vector retrieval can operate together.
-   [ ] Audit Agent retrieves source evidence for discrepancies.
-   [ ] Reconciliation requires evidence.
-   [ ] Corrections are stored as revisions.
-   [ ] Validation runs after every correction.
-   [ ] Infinite loops are impossible.
-   [ ] Low-confidence corrections terminate safely.
-   [ ] Final output includes evidence and revision history.
-   [ ] Retrieval and correction accuracy are evaluated.
-   [ ] No-RAG, vector-RAG, and hybrid-RAG baselines are compared.
-   [ ] Full execution is observable through traces.

------------------------------------------------------------------------

# 23. Final Execution Flow

The completed system should behave as follows:

``` text
                  INVOICE PDF
                       │
                       ▼
                  INGESTION
                       │
                       ▼
              TEXT + TABLE EXTRACTION
                       │
                       ▼
               CANONICAL DOCUMENT
                       │
              ┌────────┴────────┐
              ▼                 ▼
           LEDGER          EPHEMERAL RAG
              │                 │
              └────────┬────────┘
                       ▼
                   VALIDATE
                       │
             ┌─────────┴─────────┐
             │                   │
           VALID               INVALID
             │                   │
             ▼                   ▼
         FINALIZE              AUDIT
                                  │
                           RETRIEVE EVIDENCE
                                  │
                           VERIFY EVIDENCE
                                  │
                              RECONCILE
                                  │
                              VALIDATE
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                  PASS                         FAIL
                    │                           │
                    ▼                           ▼
                FINALIZE                  AUDIT AGAIN
                    │
                    ▼
              AUDIT TRAIL
```

The final architecture is therefore a **document-scoped RAG +
deterministic validation + evidence-backed correction + LangGraph
feedback loop**, rather than a generic persistent RAG chatbot.
