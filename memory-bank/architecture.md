# Self-Correction Ledger Agent --- Architecture

## 1. Overview

The Self-Correction Ledger Agent is a document-scoped, evidence-grounded
reconciliation system for invoices.

Each incoming PDF is treated as an independent unit of work:

``` text
Incoming PDF
    ↓
Document Ingestion
    ↓
Text + Table Extraction
    ↓
Canonical Document
    ├── Structured Ledger
    └── Ephemeral Hybrid RAG Index
             ↓
        LangGraph State Machine
             ↓
        Deterministic Validation
             ↓
      ┌──────┴──────┐
      │             │
    PASS           FAIL
      │             │
   Finalize       Audit
                    ↓
               Reconcile
                    ↓
                 Validate ↺
```

The central design principle is:

> LLMs interpret documents and propose evidence-backed corrections;
> deterministic Python code decides mathematical correctness.

------------------------------------------------------------------------

## 2. Goals

### Primary goals

-   Extract normal PDF text and tables efficiently.
-   Preserve page/table/row/column provenance.
-   Convert invoice content into a structured ledger.
-   Detect arithmetic inconsistencies deterministically.
-   Retrieve supporting evidence from the current invoice when
    discrepancies occur.
-   Propose evidence-backed corrections.
-   Re-run validation after every correction.
-   Reconcile automatically without human intervention when sufficient
    evidence exists.
-   Prevent infinite correction loops.
-   Produce an auditable revision and evidence trail.

### Non-goals

-   Maintaining a permanent global invoice vector database for the core
    reconciliation flow.
-   Allowing an LLM to perform final arithmetic validation.
-   Automatically correcting a value when supporting evidence is weak or
    ambiguous.
-   Treating semantic similarity as proof of numerical correctness.

------------------------------------------------------------------------

## 3. High-Level Architecture

``` text
                           ┌──────────────────────┐
                           │   Incoming Invoice   │
                           │         PDF          │
                           └──────────┬───────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │ Document Ingestion   │
                           │ PDF classification   │
                           └──────────┬───────────┘
                                      │
                       ┌──────────────┴──────────────┐
                       │                             │
                 Native PDF                      Scanned PDF
                       │                             │
                       ▼                             ▼
                   PyMuPDF                         OCR
                       │                             │
                       └──────────────┬──────────────┘
                                      ▼
                           ┌──────────────────────┐
                           │ Canonical Document   │
                           │                      │
                           │ Text                 │
                           │ Tables               │
                           │ Cells                │
                           │ BBoxes               │
                           │ Provenance            │
                           └──────────┬───────────┘
                                      │
                    ┌─────────────────┴──────────────────┐
                    │                                    │
                    ▼                                    ▼
          ┌───────────────────┐                ┌───────────────────┐
          │ Structured Ledger │                │ Ephemeral RAG     │
          │                   │                │                   │
          │ Line items        │                │ BM25              │
          │ Subtotal          │                │ Embeddings        │
          │ Tax               │                │ Metadata filters  │
          │ Discounts         │                │                   │
          │ Total             │                │ Current invoice   │
          └─────────┬─────────┘                └─────────┬─────────┘
                    │                                    │
                    └─────────────────┬──────────────────┘
                                      ▼
                           ╔══════════════════╗
                           ║    LangGraph     ║
                           ╚════════╤═════════╝
                                    ▼
                           ┌──────────────────┐
                           │ Validation Agent │
                           │ Python rules     │
                           └────────┬─────────┘
                                    │
                           ┌────────┴────────┐
                           │                 │
                         PASS              FAIL
                           │                 │
                           ▼                 ▼
                       Finalize       ┌──────────────┐
                                      │ Audit Agent  │
                                      │ Hybrid RAG   │
                                      └──────┬───────┘
                                             ▼
                                      ┌──────────────┐
                                      │ Evidence     │
                                      │ Validation   │
                                      └──────┬───────┘
                                             ▼
                                      ┌──────────────┐
                                      │ Reconcile    │
                                      │ Agent        │
                                      └──────┬───────┘
                                             │
                                             ▼
                                        Validation
                                             │
                                             └── FAIL → Audit
```

------------------------------------------------------------------------

## 4. Document Processing Layer

### 4.1 PDF classification

The ingestion layer determines whether each page contains usable native
text.

For native PDFs:

-   Extract text directly.
-   Extract tables using a table-aware parser.
-   Preserve coordinates and page numbers.

For scanned pages:

-   Run OCR only where required.
-   Recover text and table structure.
-   Preserve OCR confidence where available.

This avoids unnecessarily OCR'ing digitally generated invoices.

### 4.2 Recommended extraction stack

  Requirement              Primary approach
  ------------------------ -----------------------------------
  Native PDF text          PyMuPDF
  Native PDF tables        PyMuPDF table extraction
  OCR fallback             PaddleOCR or equivalent
  Complex layouts/tables   Docling or dedicated table parser
  Structured output        Pydantic

The implementation should benchmark a lightweight PyMuPDF-first pipeline
against Docling before committing to a heavier parser.

------------------------------------------------------------------------

## 5. Canonical Document Model

Extraction should produce a normalized document representation rather
than a single flattened text string.

Example:

``` python
{
    "document_id": "INV-123",
    "pages": [
        {
            "page": 2,
            "blocks": [
                {
                    "type": "text",
                    "text": "Invoice #INV-123",
                    "bbox": [...]
                },
                {
                    "type": "table",
                    "table_id": "table_01",
                    "bbox": [...],
                    "rows": [...]
                }
            ]
        }
    ]
}
```

Every extracted value should retain provenance:

``` text
document_id
page
block_id
table_id
row_id
column
bounding_box
```

This allows an audit result to identify the exact source:

``` text
Invoice INV-123
Page 2
Table 1
Row 7
Column: Amount
```

------------------------------------------------------------------------

## 6. Structured Ledger

The structured ledger is the machine-checkable representation used by
the validation layer.

Example:

``` json
{
  "currency": "USD",
  "items": [
    {
      "id": "line_01",
      "description": "Industrial Filter",
      "quantity": 12,
      "unit_price": 84.50,
      "amount": 1014.00
    }
  ],
  "subtotal": 1014.00,
  "tax": 101.40,
  "total": 1115.40
}
```

The ledger should preserve the link between each value and its document
provenance.

------------------------------------------------------------------------

## 7. Ephemeral Document-Scoped RAG

The RAG system is not a permanent knowledge base for this workflow.

For every incoming invoice:

``` text
PDF
 ↓
Extract chunks
 ↓
Generate embeddings
 ↓
Build temporary lexical + vector indexes
 ↓
Use during reconciliation
 ↓
Dispose after processing
```

Each retrieval record should contain metadata such as:

``` text
invoice_id
page
table_id
row_id
field
chunk_type
```

### Why hybrid retrieval?

Invoice data is highly numerical and structured.

-   BM25/exact retrieval is useful for invoice numbers, line
    identifiers, product names, and exact numeric tokens.
-   Dense embeddings are useful for semantically phrased discrepancies.
-   Metadata filtering ensures retrieval remains scoped to the current
    invoice.

Therefore:

``` text
Hybrid Retrieval = BM25 + Dense Embeddings + Metadata Filtering
```

------------------------------------------------------------------------

## 8. LangGraph State Machine

The state should contain the current ledger, discrepancies, audit
evidence, corrections, and loop-control information.

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

### Graph

``` text
START
  ↓
INGEST
  ↓
EXTRACT
  ↓
INDEX
  ↓
BUILD LEDGER
  ↓
VALIDATE
  ├── PASS → FINALIZE → END
  └── FAIL
        ↓
      AUDIT
        ↓
   EVIDENCE CHECK
        ↓
    RECONCILE
        ↓
     VALIDATE
        └── FAIL → AUDIT
```

------------------------------------------------------------------------

## 9. Validation Agent

Validation should be deterministic.

### Line-item validation

``` text
expected_amount = quantity × unit_price
```

### Subtotal validation

``` text
expected_subtotal = Σ line_amounts
```

### Tax validation

Tax logic depends on the invoice model and may include:

-   percentage tax
-   tax per line
-   multiple tax rates
-   tax-inclusive prices

### Grand total validation

For a simple invoice:

``` text
expected_total = subtotal - discount + tax + shipping + fees
```

The validation layer should support configurable invoice formulas.

Use `Decimal` rather than binary floating-point arithmetic for monetary
values.

------------------------------------------------------------------------

## 10. Audit Agent

The Audit Agent is invoked only when validation finds a discrepancy.

Input:

``` text
invoice_id
discrepancy
current ledger
```

Example discrepancy:

``` text
line_07.amount:
expected = 1014.00
observed = 1040.00
difference = 26.00
```

The Audit Agent creates a targeted retrieval query and searches the
current invoice.

Expected evidence:

``` text
Page 2 / Table 1 / Row 7

Industrial Filter
Qty: 12
Unit Price: $84.50
Amount: $1,014.00
```

------------------------------------------------------------------------

## 11. Evidence Validation

Retrieved evidence should not automatically become a correction.

The system should verify:

-   Same invoice.
-   Relevant page.
-   Relevant table/row.
-   Relevant field.
-   Evidence is sufficiently complete.
-   Confidence exceeds the configured threshold.

Audit output:

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

------------------------------------------------------------------------

## 12. Reconciliation Agent

The Reconciliation Agent converts validated evidence into a patch.

Example:

``` json
{
  "operation": "UPDATE",
  "path": "items[line_07].amount",
  "old_value": 1040.00,
  "new_value": 1014.00,
  "reason": "Raw invoice evidence",
  "source_page": 2,
  "confidence": 0.97
}
```

Corrections should be stored as revisions rather than silently
overwriting the original extraction.

------------------------------------------------------------------------

## 13. Self-Correction Controls

The loop must be bounded.

### Maximum revisions

Example:

``` text
max_revisions = 3
```

### No-progress detection

If the same discrepancy persists across iterations, terminate.

``` text
Revision 1 → $26 discrepancy
Revision 2 → $26 discrepancy
→ FAILED
```

### Evidence threshold

If retrieval confidence is insufficient, do not guess.

``` text
low confidence
      ↓
FAILED_RECONCILIATION
```

### Final states

``` text
RECONCILED
UNRESOLVED
MAX_REVISIONS_EXCEEDED
INSUFFICIENT_EVIDENCE
```

------------------------------------------------------------------------

## 14. Audit Trail

Every correction should record:

``` python
{
    "revision": 1,
    "field": "line_07.amount",
    "old_value": 1040.00,
    "new_value": 1014.00,
    "reason": "Raw invoice evidence",
    "source_page": 2,
    "source_table": 1,
    "source_row": 7,
    "confidence": 0.97
}
```

This produces a complete lineage:

``` text
Extraction
    ↓
Validation discrepancy
    ↓
Retrieval query
    ↓
Retrieved evidence
    ↓
Correction
    ↓
Re-validation
    ↓
Final state
```

------------------------------------------------------------------------

## 15. Observability

Trace every graph execution and node transition.

Recommended tooling:

-   LangSmith or Opik for traces.
-   PostgreSQL for durable invoice/reconciliation state.
-   Structured logs for extraction and validation events.

Important trace fields:

``` text
invoice_id
graph_run_id
revision
node
latency
retrieval_query
retrieved_chunks
retrieval_scores
discrepancies
corrections
validation_result
final_status
```

------------------------------------------------------------------------

## 16. Security and Data Isolation

The ephemeral retrieval index must be scoped by invoice.

Never allow:

``` text
Invoice A query → Invoice B evidence
```

Enforce:

``` text
invoice_id metadata filter
```

before retrieval.

For sensitive invoices, temporary embeddings and extracted content
should be deleted after the configured retention period.

------------------------------------------------------------------------

## 17. Final Technology Stack

``` text
Python
├── PyMuPDF
├── OCR engine
├── Docling / table parser where required
├── Pydantic
├── LangGraph
├── LangChain
├── BM25
├── Qdrant / Chroma
├── PostgreSQL
└── Opik / LangSmith
```

LLM/VLM:

``` text
Document interpretation
Evidence interpretation
Correction proposal
```

Python:

``` text
Arithmetic
Validation
Tolerance handling
State transitions
Loop termination
Patch application
```

------------------------------------------------------------------------

## 18. Core Design Principle

The system should follow:

``` text
LLM proposes
     ↓
Evidence supports
     ↓
Deterministic validator verifies
     ↓
LangGraph decides whether to continue
```

Not:

``` text
LLM
 ↓
LLM
 ↓
LLM
 ↓
"Looks correct"
```

The result is a bounded, evidence-grounded self-correction system rather
than an unconstrained autonomous agent.
