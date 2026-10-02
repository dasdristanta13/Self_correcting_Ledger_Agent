# Self-Correcting Ledger Agent — Core Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the cycle-1 core loop: invoice PDF → canonical document → Pydantic ledger + per-invoice hybrid index → deterministic validation → evidence-backed, bounded self-correction in LangGraph.

**Architecture:** PyMuPDF extracts text, blocks and tables with provenance. A deterministic builder makes the `Ledger`; Decimal-only validation finds discrepancies. A per-invoice `InvoiceIndex` (BM25 + hashed/numpy vectors, RRF fusion, hard `invoice_id` scope) supplies evidence. A proposer (deterministic or LLM) suggests values; a verifier gates them; patches are applied as audited revisions; guards bound the loop. LangGraph wires the nodes.

**Tech Stack:** Python 3.11+, pydantic v2, pymupdf, langgraph, rank-bm25, numpy, pyyaml, reportlab (test data), pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-ledger-agent-core-design.md` (requirements source: `memory-bank/architecture.md`, `memory-bank/implementation-plan.md`)

## Global Constraints

- Python `>=3.11`; package `ledger_agent` under `src/`; tests under `tests/{unit,integration}`.
- All money is `decimal.Decimal`; never `float` for money; quantize with `ROUND_HALF_UP` to `0.01`; default tolerance `Decimal("0.01")`.
- `max_revisions = 3`, `confidence_threshold = 0.90` (configurable).
- LLM only behind `LLMClient`, embeddings only behind `Embedder`; every test runs offline with `FakeLLM` / `HashingEmbedder`.
- Every retrieval call takes `invoice_id` and is rejected unless it equals the index's invoice.
- Corrections are revisions (`AuditRecord`); the original ledger is never mutated (`set_field` returns a copy).
- Terminal statuses: `RECONCILED`, `UNRESOLVED`, `MAX_REVISIONS_EXCEEDED`, `INSUFFICIENT_EVIDENCE`, `NO_PROGRESS`, plus `FAILED` for extraction errors.
- LangGraph: no node name may equal a state key (state key is `retrieval_index`, node is `build_index`).
- **No git repo exists.** "Checkpoint" steps tick the task in `memory-bank/progress.md` instead of committing. (Optionally `git init` first and commit at each checkpoint.)
- Run tests from the project root with `python -m pytest ...` inside the project venv (Task 1 creates it).

## Review Focus

1. **Multi-page invoice** whose table header repeats on each page: item ids must be global (`line_01…line_80`), not restart per table. Test: Task 6.
2. **Two identical line items** (same description/qty/price): retrieval and patching must hit the right row via `item_id`, not the first look-alike. Tests: Task 5, Task 11.
3. **Scanned / text-less PDF with no OCR backend**: graph ends `FAILED` with an error message, never a crash or a partial ledger. Tests: Task 4, Task 11.
4. **Missing line-item table or missing grand total**: `ExtractionError` → `FAILED`. Test: Task 6, Task 11.
5. **Invoice that is itself arithmetically wrong** (evidence agrees with the bad value): must end `UNRESOLVED`, not "corrected" to a guess. Test: Task 11.

## File Structure

```
pyproject.toml
configs/default.yaml
src/ledger_agent/
  __init__.py
  money.py            # q2, parse_money
  textparse.py        # tokenize, parse_labeled_line
  models.py           # all Pydantic contracts
  config.py           # ValidationRules, Config
  protocols.py        # LLMClient, Embedder, OcrBackend, TableExtractor
  state.py            # Status, LedgerState
  paths.py            # parse_path/get_field/set_field
  columns.py          # canonical_column, column_map, iter_line_item_rows
  fakes.py            # HashingEmbedder, FakeLLM
  ingestion/{__init__,pdf,tables}.py
  extraction/{__init__,canonical,ledger}.py
  validation/{__init__,arithmetic}.py
  retrieval/{__init__,chunks,bm25,vector,hybrid}.py
  agents/{__init__,guards,audit,reconciliation}.py
  graph.py
  testing/{__init__,ledgers,invoices,corrupt}.py
tests/unit/...  tests/integration/test_graph.py
```

## Execution order and parallelism

| Group | Tasks | Notes |
|---|---|---|
| Sequential | T1 contracts → T2 test-data factory | everything depends on these |
| Parallel P1 | T3 validation · T4 ingestion/tables/canonical · T5 retrieval | disjoint dirs; T5 uses hand-built `make_document` from T2 |
| After T4 | T6 ledger builder | needs canonical doc |
| Parallel P2 | T7 guards · T8 audit · T9 reconciliation | T8 needs T5 |
| Sequential | T10 graph → T11 end-to-end → T12 close-out | |

After each task and group: update `memory-bank/progress.md`.

---

### Task 1: Scaffold and contracts

**Files:**
- Create: `pyproject.toml`, `configs/default.yaml`, `src/ledger_agent/{__init__,money,textparse,models,config,protocols,state,paths,columns,fakes}.py`
- Test: `tests/unit/test_money.py`, `tests/unit/test_textparse.py`, `tests/unit/test_paths.py`, `tests/unit/test_config.py`, `tests/unit/test_columns.py`

**Interfaces:**
- Produces: everything listed under File Structure for these modules. Exact signatures are in the code below and are relied on by all later tasks.

- [ ] **Step 1: Environment**

Run (PowerShell, project root):
```powershell
python --version   # must be 3.11+
python -m venv .venv
.venv\Scripts\python -m pip install -U pip
```
Create `pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "ledger-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2.6", "pymupdf>=1.24", "langgraph>=0.2", "rank-bm25>=0.2.2",
  "numpy>=1.26", "pyyaml>=6", "reportlab>=4",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```
Run: `.venv\Scripts\python -m pip install -e ".[dev]"` — Expected: installs without error.

- [ ] **Step 2: Write failing tests**

`tests/unit/test_money.py`:
```python
from decimal import Decimal
import pytest
from ledger_agent.money import parse_money, q2

def test_parse_money_formats():
    assert parse_money("$1,014.00") == Decimal("1014.00")
    assert parse_money("(5.00)") == Decimal("-5.00")
    assert parse_money("-$10.00") == Decimal("-10.00")
    assert parse_money("12 pcs") == Decimal("12")

def test_parse_money_rejects_garbage():
    for bad in ["", "abc", "1.2.3"]:
        with pytest.raises(ValueError):
            parse_money(bad)

def test_q2_rounds_half_up():
    assert q2(Decimal("1.005")) == Decimal("1.01")
    assert q2(Decimal("9.999")) == Decimal("10.00")
```
`tests/unit/test_textparse.py`:
```python
from decimal import Decimal
from ledger_agent.textparse import parse_labeled_line, tokenize

def test_tokenize_normalizes_thousands_commas():
    assert tokenize("Amount: $1,014.00 | Row 7") == ["amount", "1014.00", "row", "7"]
    assert "line_07" in tokenize("line_07 Gasket")

def test_labeled_lines():
    a = parse_labeled_line("Subtotal: $1,044.00")
    assert (a.field, a.amount, a.rate) == ("subtotal", Decimal("1044.00"), None)
    t = parse_labeled_line("Tax (10%): $104.40")
    assert (t.field, t.amount, t.rate) == ("tax", Decimal("104.40"), Decimal("0.10"))
    assert parse_labeled_line("Grand Total: $5.00").field == "total"
    assert parse_labeled_line("Discount: -$10.00").amount == Decimal("10.00")
    assert parse_labeled_line("Industrial Filter") is None
    assert parse_labeled_line("Total") is None
```
`tests/unit/test_paths.py`:
```python
from decimal import Decimal
import pytest
from ledger_agent.paths import PathError, get_field, parse_path, set_field
from ledger_agent.testing.ledgers import make_ledger

def test_parse_path():
    assert parse_path("items[line_01].amount").kind == "item"
    assert parse_path("tax_lines[tax_01].amount").kind == "tax"
    assert parse_path("total").kind == "scalar"
    with pytest.raises(PathError):
        parse_path("items[line_01].description")
    with pytest.raises(PathError):
        parse_path("bogus")

def test_get_set_do_not_mutate_original():
    led = make_ledger()
    new = set_field(led, "items[line_01].amount", Decimal("1040.00"))
    assert get_field(led, "items[line_01].amount") == Decimal("1014.00")
    assert get_field(new, "items[line_01].amount") == Decimal("1040.00")

def test_set_tax_line_recomputes_tax_total():
    led = make_ledger(tax_rates=(Decimal("0.05"), Decimal("0.07")))
    new = set_field(led, "tax_lines[tax_01].amount", Decimal("1.00"))
    assert new.tax == Decimal("1.00") + led.tax_lines[1].amount

def test_missing_element():
    with pytest.raises(PathError):
        get_field(make_ledger(), "items[line_99].amount")
```
`tests/unit/test_config.py`:
```python
from decimal import Decimal
from ledger_agent.config import Config

def test_defaults():
    c = Config()
    assert c.max_revisions == 3 and c.confidence_threshold == 0.90
    assert c.validation.tolerance == Decimal("0.01")

def test_from_yaml(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("max_revisions: 5\nvalidation:\n  tolerance: 0.05\n")
    c = Config.from_yaml(p)
    assert c.max_revisions == 5 and c.validation.tolerance == Decimal("0.05")
```
`tests/unit/test_columns.py` (uses `make_document` from Task 2 — write it now, it fails until Task 2; mark with the Task 2 note below). Create it in Task 2 instead. For Task 1 only write the first four test files.

Note: `test_paths.py` imports `ledger_agent.testing.ledgers` (Task 2). Implement `testing/ledgers.py` (Task 2, Step 3) before running `test_paths.py`; run the other three now.

- [ ] **Step 3: Run tests, verify they fail**

Run: `python -m pytest tests/unit/test_money.py tests/unit/test_textparse.py tests/unit/test_config.py -v`
Expected: FAIL (ModuleNotFoundError: ledger_agent.money …).

- [ ] **Step 4: Implement**

`src/ledger_agent/__init__.py`: empty.

`money.py`:
```python
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_CENT = Decimal("0.01")


def q2(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def parse_money(text: str) -> Decimal:
    t = text.strip()
    negative = (t.startswith("(") and t.endswith(")")) or t.startswith("-")
    digits = re.sub(r"[^\d.]", "", t)
    if not digits:
        raise ValueError(f"not a money value: {text!r}")
    try:
        value = Decimal(digits)
    except InvalidOperation as exc:
        raise ValueError(f"not a money value: {text!r}") from exc
    return -value if negative else value
```
`textparse.py`:
```python
import re
from dataclasses import dataclass
from decimal import Decimal

from ledger_agent.money import parse_money

_LINE = re.compile(
    r"^\s*(?P<label>sub\s*total|discount|shipping|fees?|grand\s+total|total|tax|vat|gst)"
    r"\s*(?:\(\s*(?P<rate>\d+(?:\.\d+)?)\s*%\s*\))?\s*[:\-]?\s*"
    r"(?P<amount>[-(]?\s*[$€£]?\s*[\d,]+\.\d{2}\)?)\s*(?:[A-Z]{3})?\s*$",
    re.IGNORECASE,
)
_FIELD = {
    "subtotal": "subtotal", "discount": "discount", "shipping": "shipping",
    "fee": "fees", "fees": "fees", "grandtotal": "total", "total": "total",
    "tax": "tax", "vat": "tax", "gst": "tax",
}


@dataclass(frozen=True)
class LabeledAmount:
    field: str            # subtotal|discount|shipping|fees|total|tax
    amount: Decimal       # discount is normalised to a positive number
    rate: Decimal | None  # 0.10 for "(10%)"
    raw: str


def parse_labeled_line(line: str) -> LabeledAmount | None:
    m = _LINE.match(line)
    if not m:
        return None
    field = _FIELD[re.sub(r"\s+", "", m.group("label").lower())]
    amount = parse_money(m.group("amount"))
    if field == "discount":
        amount = abs(amount)
    rate = Decimal(m.group("rate")) / 100 if m.group("rate") else None
    return LabeledAmount(field=field, amount=amount, rate=rate, raw=line.strip())


_NUM_COMMA = re.compile(r"(?<=\d),(?=\d)")
_TOKEN = re.compile(r"[a-z0-9_]+(?:\.[a-z0-9_]+)*")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(_NUM_COMMA.sub("", text.lower()))
```
`models.py`:
```python
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    document_id: str
    page: int
    block_id: str | None = None
    table_id: str | None = None
    row: int | None = None        # data rows start at 1; row 0 is the header
    column: str | None = None     # printed header text or canonical field name
    bbox: list[float] | None = None


class DocumentPage(BaseModel):
    page_number: int
    text: str
    blocks: list[dict] = Field(default_factory=list)  # {block_id, bbox, text}
    is_ocr: bool = False
    needs_ocr: bool = False


class TextBlock(BaseModel):
    block_id: str
    page: int
    text: str
    bbox: list[float]


class TableCell(BaseModel):
    value: str
    row: int
    column: int
    bbox: list[float]


class DocumentTable(BaseModel):
    table_id: str
    page: int
    headers: list[str]
    cells: list[TableCell]  # includes header cells at row 0
    bbox: list[float]
    low_quality: bool = False

    def rows(self) -> dict[int, dict[int, TableCell]]:
        out: dict[int, dict[int, TableCell]] = {}
        for c in self.cells:
            if c.row >= 1:
                out.setdefault(c.row, {})[c.column] = c
        return dict(sorted(out.items()))


class Document(BaseModel):
    document_id: str
    pages: list[DocumentPage]
    tables: list[DocumentTable]
    text_blocks: list[TextBlock]
    column_overrides: dict[str, dict[str, int]] = Field(default_factory=dict)

    def table(self, table_id: str) -> DocumentTable | None:
        return next((t for t in self.tables if t.table_id == table_id), None)


class LineItem(BaseModel):
    id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    source: dict[str, Provenance] = Field(default_factory=dict)


class TaxLine(BaseModel):
    id: str
    rate: Decimal | None = None
    amount: Decimal
    source: dict[str, Provenance] = Field(default_factory=dict)


class Ledger(BaseModel):
    invoice_id: str
    currency: str = "USD"
    items: list[LineItem]
    subtotal: Decimal | None = None
    discount: Decimal | None = None
    tax: Decimal | None = None          # sum of tax_lines when present
    tax_lines: list[TaxLine] = Field(default_factory=list)
    shipping: Decimal | None = None
    fees: Decimal | None = None
    total: Decimal
    sources: dict[str, Provenance] = Field(default_factory=dict)


class Discrepancy(BaseModel):
    field: str                  # path, e.g. items[line_07].amount
    expected: Decimal
    observed: Decimal
    difference: Decimal         # observed - expected
    rule: str                   # line_amount|subtotal_sum|tax_rate|grand_total
    related_fields: list[str] = Field(default_factory=list)


class Chunk(BaseModel):
    chunk_id: str
    invoice_id: str
    chunk_type: str             # line_item|totals|tax|discount|shipping|header|text
    text: str
    page: int
    table_id: str | None = None
    row_id: int | None = None
    item_id: str | None = None  # line_NN / tax_NN
    field: str | None = None    # subtotal|total|tax|discount|shipping|fees
    values: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance


class ScoredChunk(BaseModel):
    chunk: Chunk
    score: float


class Evidence(BaseModel):
    field: str
    value: Decimal
    source: Provenance
    confidence: float
    chunk_id: str
    quote: str = ""


class Patch(BaseModel):
    operation: Literal["UPDATE"] = "UPDATE"
    path: str
    old_value: Decimal
    new_value: Decimal
    reason: str
    source_page: int | None = None
    source_table: str | None = None
    source_row: int | None = None
    confidence: float


class AuditRecord(BaseModel):
    revision: int
    field: str
    old_value: Decimal
    new_value: Decimal
    reason: str
    source_page: int | None
    source_table: str | None
    source_row: int | None
    confidence: float
```
`config.py`:
```python
from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ValidationRules(BaseModel):
    tolerance: Decimal = Decimal("0.01")
    total_terms: dict[str, int] = Field(default_factory=lambda: {
        "subtotal": 1, "discount": -1, "tax": 1, "shipping": 1, "fees": 1,
    })


class Config(BaseModel):
    max_revisions: int = 3
    confidence_threshold: float = 0.90
    top_k: int = 5
    ocr_min_chars: int = 30
    validation: ValidationRules = Field(default_factory=ValidationRules)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        return cls(**(yaml.safe_load(Path(path).read_text()) or {}))
```
`configs/default.yaml`:
```yaml
max_revisions: 3
confidence_threshold: 0.90
top_k: 5
ocr_min_chars: 30
validation:
  tolerance: 0.01
```
`protocols.py`:
```python
from typing import Protocol

from ledger_agent.models import DocumentTable


class LLMClient(Protocol):
    def complete_json(self, system: str, prompt: str, schema: dict) -> dict: ...


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OcrBackend(Protocol):
    def recognize(self, page_png: bytes) -> tuple[str, list[dict]]:
        """Return (text, blocks[{block_id,bbox,text}]) for one page image."""


class TableExtractor(Protocol):
    def extract(self, pdf_path: str) -> list[DocumentTable]: ...
```
`state.py`:
```python
from enum import Enum
from typing import Any, TypedDict


class Status(str, Enum):
    INGESTED = "INGESTED"
    EXTRACTED = "EXTRACTED"
    INDEXED = "INDEXED"
    VALIDATING = "VALIDATING"
    AUDITING = "AUDITING"
    RECONCILING = "RECONCILING"
    RECONCILED = "RECONCILED"
    UNRESOLVED = "UNRESOLVED"
    MAX_REVISIONS_EXCEEDED = "MAX_REVISIONS_EXCEEDED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NO_PROGRESS = "NO_PROGRESS"
    FAILED = "FAILED"


class LedgerState(TypedDict, total=False):
    pdf_path: str
    invoice_id: str
    pages: list
    document: Any
    ledger: Any
    original_ledger: Any
    retrieval_index: Any
    discrepancies: list
    last_signatures: Any
    audit_candidates: list
    audit_evidence: list
    retrieval_events: list
    proposed_corrections: list
    audit_trail: list
    revision: int
    max_revisions: int
    status: Status
    route: str
    error: str | None
```
`paths.py`:
```python
import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from ledger_agent.models import Ledger

SCALARS = ("subtotal", "discount", "tax", "shipping", "fees", "total")
_ITEM_ATTRS = ("quantity", "unit_price", "amount")
_TAX_ATTRS = ("amount", "rate")
_COLL = re.compile(r"^(items|tax_lines)\[([^\]]+)\]\.(\w+)$")


class PathError(ValueError):
    pass


class PathRef(BaseModel):
    kind: Literal["item", "tax", "scalar"]
    id: str | None = None
    attr: str


def parse_path(path: str) -> PathRef:
    m = _COLL.match(path)
    if m:
        coll, id_, attr = m.groups()
        allowed = _ITEM_ATTRS if coll == "items" else _TAX_ATTRS
        if attr not in allowed:
            raise PathError(f"unsupported attribute in path: {path!r}")
        return PathRef(kind="item" if coll == "items" else "tax", id=id_, attr=attr)
    if path in SCALARS:
        return PathRef(kind="scalar", attr=path)
    raise PathError(f"unknown field path: {path!r}")


def _find(ledger: Ledger, ref: PathRef):
    coll = ledger.items if ref.kind == "item" else ledger.tax_lines
    for element in coll:
        if element.id == ref.id:
            return element
    raise PathError(f"no such element for path with id {ref.id!r}")


def get_field(ledger: Ledger, path: str) -> Decimal | None:
    ref = parse_path(path)
    if ref.kind == "scalar":
        return getattr(ledger, ref.attr)
    return getattr(_find(ledger, ref), ref.attr)


def set_field(ledger: Ledger, path: str, value: Decimal) -> Ledger:
    ref = parse_path(path)
    new = ledger.model_copy(deep=True)
    if ref.kind == "scalar":
        setattr(new, ref.attr, value)
        return new
    setattr(_find(new, ref), ref.attr, value)
    if ref.kind == "tax" and ref.attr == "amount":
        new.tax = sum((t.amount for t in new.tax_lines), Decimal("0"))
    return new
```
`columns.py`:
```python
import re
from dataclasses import dataclass

from ledger_agent.models import Document, DocumentTable, TableCell, TextBlock

REQUIRED = frozenset({"description", "quantity", "unit_price", "amount"})
_SYNONYMS = {
    "description": {"description", "item", "product", "details", "name"},
    "quantity": {"qty", "quantity", "units"},
    "unit_price": {"unit price", "price", "rate", "unit cost"},
    "amount": {"amount", "total", "line total", "ext", "extended"},
}


def canonical_column(header: str) -> str | None:
    h = re.sub(r"[^a-z ]", "", header.lower()).strip()
    for canon, names in _SYNONYMS.items():
        if h in names:
            return canon
    return None


def column_map(headers: list[str], override: dict[str, int] | None = None) -> dict[str, int]:
    if override:
        return dict(override)
    out: dict[str, int] = {}
    for idx, header in enumerate(headers):
        canon = canonical_column(header)
        if canon and canon not in out:
            out[canon] = idx
    return out


@dataclass(frozen=True)
class LineItemRow:
    item_id: str                 # global across tables: line_01, line_02, ...
    table: DocumentTable
    row: int
    cells: dict[str, TableCell]  # canonical field -> cell
    headers: dict[str, str]      # canonical field -> printed header


def iter_line_item_rows(doc: Document):
    n = 0
    for table in sorted(doc.tables, key=lambda t: (t.page, t.table_id)):
        cmap = column_map(table.headers, doc.column_overrides.get(table.table_id))
        if not REQUIRED <= cmap.keys():
            continue
        for row_no, cells in table.rows().items():
            by_field = {f: cells[i] for f, i in cmap.items() if i in cells}
            if not REQUIRED <= by_field.keys():
                continue
            if not any(c.value.strip() for c in by_field.values()):
                continue
            n += 1
            yield LineItemRow(
                item_id=f"line_{n:02d}", table=table, row=row_no, cells=by_field,
                headers={f: table.headers[cmap[f]] for f in by_field},
            )


def inside_any_table(doc: Document, block: TextBlock) -> bool:
    cx = (block.bbox[0] + block.bbox[2]) / 2
    cy = (block.bbox[1] + block.bbox[3]) / 2
    return any(
        t.page == block.page and t.bbox[0] <= cx <= t.bbox[2] and t.bbox[1] <= cy <= t.bbox[3]
        for t in doc.tables
    )
```
`fakes.py`:
```python
import zlib
from typing import Callable

from ledger_agent.textparse import tokenize


class HashingEmbedder:
    """Deterministic offline embedder: hashed bag of tokens."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in tokenize(text):
                vec[zlib.crc32(tok.encode()) % self.dim] += 1.0
            out.append(vec)
        return out


class FakeLLM:
    """responses: a list of dicts returned in order, or a callable(system, prompt) -> dict."""

    def __init__(self, responses: list[dict] | Callable[[str, str], dict]):
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, prompt: str, schema: dict) -> dict:
        self.calls.append((system, prompt))
        if callable(self._responses):
            return self._responses(system, prompt)
        return self._responses[len(self.calls) - 1]
```

- [ ] **Step 5: Run tests, verify pass**

Run: `python -m pytest tests/unit/test_money.py tests/unit/test_textparse.py tests/unit/test_config.py -v`
Expected: PASS. (`test_paths.py` passes after Task 2 Step 3.)

- [ ] **Step 6: Checkpoint** — tick Task 1 (except `test_paths.py`, closed in Task 2) in `memory-bank/progress.md`.

---

### Task 2: Test-data factory (ledgers, documents, PDF invoices)

**Files:**
- Create: `src/ledger_agent/testing/{__init__,ledgers,invoices}.py`
- Test: `tests/unit/test_invoice_factory.py`, `tests/unit/test_columns.py`, (and run `tests/unit/test_paths.py`)

**Interfaces:**
- Consumes: Task 1 models, `q2`.
- Produces:
  - `make_ledger(items=None, discount=None, tax_rates=(Decimal("0.10"),), shipping=None, invoice_id="INV-001") -> Ledger` — internally consistent; default items `("Industrial Filter", 12, 84.50)`, `("Gasket", 3, 10.00)` ⇒ amounts 1014.00 / 30.00, subtotal 1044.00, tax 104.40, total 1148.40. Item ids `line_01…`, tax ids `tax_01…`.
  - `make_document(items=None, discount=None, tax_rates=..., shipping=None, invoice_id="INV-001") -> Document` — hand-built canonical document consistent with `make_ledger`.
  - `ItemSpec`, `InvoiceSpec`, `default_spec(invoice_id="INV-001")`, `many_items_spec(n, invoice_id="INV-MANY")`, `render_invoice(spec, path) -> Path`.

- [ ] **Step 1: Write failing tests**

`tests/unit/test_invoice_factory.py`:
```python
import pymupdf
from ledger_agent.testing.invoices import default_spec, many_items_spec, render_invoice

def test_render_default_invoice(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    with pymupdf.open(pdf) as doc:
        text = doc[0].get_text()
        assert "Invoice #INV-001" in text
        assert "Total: $1,148.40" in text
        tables = doc[0].find_tables().tables
        assert len(tables) == 1
        rows = tables[0].extract()
        assert rows[0] == ["Description", "Qty", "Unit Price", "Amount"]
        assert len(rows) == 3

def test_many_items_spans_pages_with_repeated_header(tmp_path):
    pdf = render_invoice(many_items_spec(80), tmp_path / "INV-MANY.pdf")
    with pymupdf.open(pdf) as doc:
        assert doc.page_count >= 2
        for page in doc:
            tables = page.find_tables().tables
            assert tables and tables[0].extract()[0][0] == "Description"
```
`tests/unit/test_columns.py`:
```python
from ledger_agent.columns import canonical_column, iter_line_item_rows
from ledger_agent.testing.ledgers import make_document

def test_canonical_column():
    assert canonical_column("Unit Price") == "unit_price"
    assert canonical_column("QTY") == "quantity"
    assert canonical_column("Notes") is None

def test_item_ids_are_global_and_ordered():
    rows = list(iter_line_item_rows(make_document()))
    assert [r.item_id for r in rows] == ["line_01", "line_02"]
    assert rows[0].cells["amount"].value == "1,014.00"
    assert rows[0].headers["unit_price"] == "Unit Price"
```

- [ ] **Step 2: Run, verify failure** — `python -m pytest tests/unit/test_invoice_factory.py tests/unit/test_columns.py -v` → FAIL (module not found).

- [ ] **Step 3: Implement**

`testing/__init__.py`: empty.

`testing/ledgers.py`:
```python
from decimal import Decimal

from ledger_agent.models import (
    Document, DocumentPage, DocumentTable, Ledger, LineItem, Provenance, TableCell,
    TaxLine, TextBlock,
)
from ledger_agent.money import q2

_DEFAULT_ITEMS = (
    ("Industrial Filter", Decimal("12"), Decimal("84.50")),
    ("Gasket", Decimal("3"), Decimal("10.00")),
)
_HEADERS = ["Description", "Qty", "Unit Price", "Amount"]


def make_ledger(items=None, discount=None, tax_rates=(Decimal("0.10"),), shipping=None,
                invoice_id="INV-001") -> Ledger:
    items = items or _DEFAULT_ITEMS
    line_items = []
    for n, (desc, qty, price) in enumerate(items, start=1):
        src = {"amount": Provenance(document_id=invoice_id, page=1, table_id="table_01",
                                    row=n, column="Amount")}
        line_items.append(LineItem(id=f"line_{n:02d}", description=desc, quantity=qty,
                                   unit_price=price, amount=q2(qty * price), source=src))
    subtotal = sum((i.amount for i in line_items), Decimal("0"))
    base = subtotal - (discount or Decimal("0"))
    tax_lines = [TaxLine(id=f"tax_{n:02d}", rate=r, amount=q2(base * r))
                 for n, r in enumerate(tax_rates, start=1)]
    tax = sum((t.amount for t in tax_lines), Decimal("0")) if tax_lines else None
    total = q2(subtotal - (discount or 0) + (tax or 0) + (shipping or 0))
    return Ledger(invoice_id=invoice_id, items=line_items, subtotal=subtotal,
                  discount=discount, tax=tax, tax_lines=tax_lines, shipping=shipping,
                  total=total)


def _fmt(v: Decimal) -> str:
    return f"{v:,.2f}"


def make_document(items=None, discount=None, tax_rates=(Decimal("0.10"),), shipping=None,
                  invoice_id="INV-001") -> Document:
    led = make_ledger(items, discount, tax_rates, shipping, invoice_id)
    cells = [TableCell(value=h, row=0, column=c, bbox=[50 + 100 * c, 100, 150 + 100 * c, 120])
             for c, h in enumerate(_HEADERS)]
    for r, it in enumerate(led.items, start=1):
        vals = [it.description, f"{it.quantity:f}", _fmt(it.unit_price), _fmt(it.amount)]
        for c, v in enumerate(vals):
            y = 100 + 20 * r
            cells.append(TableCell(value=v, row=r, column=c,
                                   bbox=[50 + 100 * c, y, 150 + 100 * c, y + 20]))
    y_end = 100 + 20 * (len(led.items) + 1)
    table = DocumentTable(table_id="table_01", page=1, headers=list(_HEADERS), cells=cells,
                          bbox=[50, 100, 450, y_end])
    lines = [f"Invoice #{invoice_id}", "Currency: USD", f"Subtotal: ${_fmt(led.subtotal)}"]
    if discount:
        lines.append(f"Discount: ${_fmt(discount)}")
    for t in led.tax_lines:
        lines.append(f"Tax ({(t.rate * 100).normalize():f}%): ${_fmt(t.amount)}")
    if shipping:
        lines.append(f"Shipping: ${_fmt(shipping)}")
    lines.append(f"Total: ${_fmt(led.total)}")
    blocks = [TextBlock(block_id=f"p1_b{n}", page=1, text=t,
                        bbox=[50, y_end + 20 * (n + 1), 300, y_end + 20 * (n + 2)])
              for n, t in enumerate(lines)]
    page = DocumentPage(page_number=1, text="\n".join(lines))
    return Document(document_id=invoice_id, pages=[page], tables=[table], text_blocks=blocks)
```
`testing/invoices.py`:
```python
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from ledger_agent.money import q2


@dataclass
class ItemSpec:
    description: str
    quantity: Decimal
    unit_price: Decimal
    printed_amount: Decimal | None = None   # override to print a wrong amount


@dataclass
class InvoiceSpec:
    invoice_id: str
    items: list[ItemSpec]
    currency: str = "USD"
    discount: Decimal = Decimal("0")
    tax_rates: tuple[Decimal, ...] = (Decimal("0.10"),)
    shipping: Decimal = Decimal("0")
    printed_subtotal: Decimal | None = None
    printed_taxes: tuple[Decimal | None, ...] = ()
    printed_total: Decimal | None = None

    def resolved(self):
        amounts = [i.printed_amount if i.printed_amount is not None
                   else q2(i.quantity * i.unit_price) for i in self.items]
        subtotal = (self.printed_subtotal if self.printed_subtotal is not None
                    else sum(amounts, Decimal("0")))
        base = subtotal - self.discount
        taxes = []
        for n, rate in enumerate(self.tax_rates):
            over = self.printed_taxes[n] if n < len(self.printed_taxes) else None
            taxes.append((rate, over if over is not None else q2(base * rate)))
        total = (self.printed_total if self.printed_total is not None
                 else q2(subtotal - self.discount + sum((t for _, t in taxes), Decimal("0"))
                         + self.shipping))
        return amounts, subtotal, taxes, total


def default_spec(invoice_id: str = "INV-001") -> InvoiceSpec:
    return InvoiceSpec(invoice_id, [
        ItemSpec("Industrial Filter", Decimal("12"), Decimal("84.50")),
        ItemSpec("Gasket", Decimal("3"), Decimal("10.00")),
    ])


def many_items_spec(n: int, invoice_id: str = "INV-MANY") -> InvoiceSpec:
    return InvoiceSpec(invoice_id, [
        ItemSpec(f"Part {i:03d}", Decimal(i % 5 + 1), Decimal("2.50")) for i in range(1, n + 1)
    ])


def _m(v: Decimal) -> str:
    return f"${v:,.2f}"


def render_invoice(spec: InvoiceSpec, path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    amounts, subtotal, taxes, total = spec.resolved()
    styles = getSampleStyleSheet()
    flow = [Paragraph(f"Invoice #{spec.invoice_id}", styles["Title"]),
            Paragraph(f"Currency: {spec.currency}", styles["Normal"]), Spacer(1, 12)]
    data = [["Description", "Qty", "Unit Price", "Amount"]]
    for it, amt in zip(spec.items, amounts):
        data.append([it.description, f"{it.quantity:f}", f"{it.unit_price:,.2f}", f"{amt:,.2f}"])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    flow += [table, Spacer(1, 12), Paragraph(f"Subtotal: {_m(subtotal)}", styles["Normal"])]
    if spec.discount:
        flow.append(Paragraph(f"Discount: {_m(spec.discount)}", styles["Normal"]))
    for rate, amt in taxes:
        flow.append(Paragraph(f"Tax ({(rate * 100).normalize():f}%): {_m(amt)}", styles["Normal"]))
    if spec.shipping:
        flow.append(Paragraph(f"Shipping: {_m(spec.shipping)}", styles["Normal"]))
    flow.append(Paragraph(f"Total: {_m(total)}", styles["Normal"]))
    path = Path(path)
    SimpleDocTemplate(str(path), pagesize=letter).build(flow)
    return path
```
(Remove the unused `field` import if your linter complains.)

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/unit/test_invoice_factory.py tests/unit/test_columns.py tests/unit/test_paths.py -v`
Expected: PASS. If `find_tables` finds no table, confirm reportlab grid lines are drawn (the `GRID` style is required) and PyMuPDF is ≥1.24.

- [ ] **Step 5: Checkpoint** — tick Task 1 and Task 2 in `memory-bank/progress.md`.

---

### Task 3: Validation engine (parallel group P1)

**Files:**
- Create: `src/ledger_agent/validation/{__init__,arithmetic}.py`
- Test: `tests/unit/test_validation.py`

**Interfaces:**
- Consumes: `Ledger`, `Discrepancy`, `ValidationRules`, `q2`, `make_ledger`.
- Produces: `validate(ledger: Ledger, rules: ValidationRules) -> list[Discrepancy]`. Order: lines, subtotal, tax lines, total. `difference = observed - expected`. `related_fields`: line → `[items[ID].amount, items[ID].quantity, items[ID].unit_price]`; subtotal → `["subtotal"]`; tax line → `[tax_lines[ID].amount]`; total → `["total"]` + each present of `subtotal, discount, tax, shipping, fees`. Tax rule base = `(subtotal or sum(items)) - discount`; each tax line with a rate is checked; total uses `ledger.tax` if set else sum of tax lines.

- [ ] **Step 1: Write failing tests** — `tests/unit/test_validation.py`:
```python
from decimal import Decimal as D
from ledger_agent.config import ValidationRules
from ledger_agent.paths import set_field
from ledger_agent.testing.ledgers import make_ledger
from ledger_agent.validation.arithmetic import validate

R = ValidationRules()

def fields(ledger):
    return {d.field for d in validate(ledger, R)}

def test_correct_invoice_has_no_discrepancies():
    assert validate(make_ledger(), R) == []

def test_wrong_line_amount():
    led = set_field(make_ledger(), "items[line_01].amount", D("1040.00"))
    ds = validate(led, R)
    d = next(x for x in ds if x.field == "items[line_01].amount")
    assert (d.expected, d.observed, d.difference, d.rule) == (D("1014.00"), D("1040.00"), D("26.00"), "line_amount")
    assert "items[line_01].quantity" in d.related_fields
    assert "subtotal" in {x.field for x in ds}

def test_wrong_subtotal():
    led = make_ledger().model_copy(update={"subtotal": D("1050.00")})
    assert "subtotal" in fields(led)

def test_wrong_tax_line():
    led = set_field(make_ledger(), "tax_lines[tax_01].amount", D("100.00"))
    fs = fields(led)
    assert "tax_lines[tax_01].amount" in fs and "total" in fs

def test_wrong_total():
    led = make_ledger().model_copy(update={"total": D("1200.00")})
    ds = validate(led, R)
    assert [d.field for d in ds] == ["total"]
    assert {"total", "subtotal", "tax"} <= set(ds[0].related_fields)

def test_discount_applies_before_tax():
    assert validate(make_ledger(discount=D("44.00")), R) == []

def test_shipping_included_in_total():
    assert validate(make_ledger(shipping=D("15.00")), R) == []
    bad = make_ledger(shipping=D("15.00")).model_copy(update={"total": D("1148.40")})
    assert fields(bad) == {"total"}

def test_multiple_tax_rates():
    led = make_ledger(tax_rates=(D("0.05"), D("0.07")))
    assert validate(led, R) == []
    assert led.tax == D("52.20") + D("73.08")

def test_rounding_within_tolerance_passes_but_two_cents_fails():
    items = (("Widget", D("3"), D("3.333")),)
    led = make_ledger(items=items, tax_rates=())
    assert led.items[0].amount == D("10.00")
    near = set_field(led, "items[line_01].amount", D("10.01"))
    assert "items[line_01].amount" not in fields(near)
    far = set_field(led, "items[line_01].amount", D("10.02"))
    assert "items[line_01].amount" in fields(far)

def test_custom_total_terms():
    rules = ValidationRules(total_terms={"subtotal": 1})
    led = make_ledger()  # total includes tax, so a subtotal-only formula must flag it
    assert [d.field for d in validate(led, rules)] == ["total"]
```
- [ ] **Step 2:** `python -m pytest tests/unit/test_validation.py -v` → FAIL (import error).
- [ ] **Step 3: Implement** `validation/__init__.py` (empty), `validation/arithmetic.py`:
```python
from decimal import Decimal

from ledger_agent.config import ValidationRules
from ledger_agent.models import Discrepancy, Ledger
from ledger_agent.money import q2

ZERO = Decimal("0")


def _check(field, expected, observed, rule, related, tol):
    diff = observed - expected
    if abs(diff) > tol:
        return Discrepancy(field=field, expected=expected, observed=observed,
                           difference=diff, rule=rule, related_fields=related)
    return None


def validate(ledger: Ledger, rules: ValidationRules) -> list[Discrepancy]:
    tol = rules.tolerance
    out: list[Discrepancy] = []

    def add(d):
        if d:
            out.append(d)

    for it in ledger.items:
        base = f"items[{it.id}]"
        add(_check(f"{base}.amount", q2(it.quantity * it.unit_price), it.amount, "line_amount",
                   [f"{base}.amount", f"{base}.quantity", f"{base}.unit_price"], tol))

    items_sum = sum((i.amount for i in ledger.items), ZERO)
    if ledger.subtotal is not None:
        add(_check("subtotal", items_sum, ledger.subtotal, "subtotal_sum", ["subtotal"], tol))

    subtotal = ledger.subtotal if ledger.subtotal is not None else items_sum
    tax_base = subtotal - (ledger.discount or ZERO)
    for t in ledger.tax_lines:
        if t.rate is not None:
            add(_check(f"tax_lines[{t.id}].amount", q2(tax_base * t.rate), t.amount, "tax_rate",
                       [f"tax_lines[{t.id}].amount"], tol))

    tax_total = ledger.tax if ledger.tax is not None else sum((t.amount for t in ledger.tax_lines), ZERO)
    values = {"subtotal": subtotal, "discount": ledger.discount, "tax": tax_total,
              "shipping": ledger.shipping, "fees": ledger.fees}
    expected = q2(sum((sign * (values.get(name) or ZERO) for name, sign in rules.total_terms.items()), ZERO))
    present = [n for n in ("subtotal", "discount", "tax", "shipping", "fees")
               if n in rules.total_terms and getattr(ledger, n) is not None]
    add(_check("total", expected, ledger.total, "grand_total", ["total", *present], tol))
    return out
```
- [ ] **Step 4:** `python -m pytest tests/unit/test_validation.py -v` → PASS.
- [ ] **Step 5: Checkpoint** — tick Task 3 in `progress.md`.

---

### Task 4: Ingestion, tables, canonical document (parallel group P1)

**Files:**
- Create: `src/ledger_agent/ingestion/{__init__,pdf,tables}.py`, `src/ledger_agent/extraction/{__init__,canonical}.py`
- Test: `tests/unit/test_ingestion.py`, `tests/unit/test_tables.py`, `tests/unit/test_canonical.py`

**Interfaces:**
- Consumes: models, protocols, `render_invoice`, `column_map`.
- Produces:
  - `ingest_pdf(path, min_chars: int = 30, ocr: OcrBackend | None = None) -> list[DocumentPage]` (block ids `p{page}_b{n}`; `needs_ocr=True` when text shorter than `min_chars` and no OCR; with OCR, `is_ocr=True`).
  - `extract_tables(path) -> list[DocumentTable]` (ids `table_01…` global; header cells at row 0; `low_quality` if <60% non-empty cells or any empty header) and `PyMuPDFTableExtractor().extract(path)` (satisfies `TableExtractor`).
  - `build_document(document_id: str, pages, tables) -> Document`; `locate_cell(doc, prov) -> TableCell | None`; `describe(prov) -> str` (e.g. `"Invoice INV-001 / Page 1 / table_01 / Row 1 / Column: Amount"`).

- [ ] **Step 1: Write failing tests**

`tests/unit/test_ingestion.py`:
```python
import pymupdf
from ledger_agent.ingestion.pdf import ingest_pdf
from ledger_agent.testing.invoices import default_spec, render_invoice

class FakeOcr:
    def recognize(self, page_png):
        return "Total: $1.00 scanned text that is long enough", [
            {"block_id": "ocr_b0", "bbox": [0, 0, 1, 1], "text": "Total: $1.00"}]

def blank_pdf(path):
    d = pymupdf.open(); d.new_page(); d.save(path); d.close()
    return path

def test_native_pdf_needs_no_ocr(tmp_path):
    pages = ingest_pdf(render_invoice(default_spec(), tmp_path / "a.pdf"))
    assert len(pages) == 1 and not pages[0].is_ocr and not pages[0].needs_ocr
    assert "Invoice #INV-001" in pages[0].text
    assert pages[0].blocks and len(pages[0].blocks[0]["bbox"]) == 4
    assert pages[0].blocks[0]["block_id"].startswith("p1_b")

def test_blank_page_flagged_when_no_ocr(tmp_path):
    pages = ingest_pdf(blank_pdf(tmp_path / "b.pdf"))
    assert pages[0].needs_ocr and not pages[0].is_ocr

def test_blank_page_uses_ocr_backend(tmp_path):
    pages = ingest_pdf(blank_pdf(tmp_path / "c.pdf"), ocr=FakeOcr())
    assert pages[0].is_ocr and not pages[0].needs_ocr and "scanned" in pages[0].text
```
`tests/unit/test_tables.py`:
```python
from ledger_agent.ingestion.tables import PyMuPDFTableExtractor, extract_tables
from ledger_agent.testing.invoices import default_spec, many_items_spec, render_invoice

def test_extract_default_table(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "a.pdf")
    [t] = extract_tables(pdf)
    assert (t.table_id, t.page) == ("table_01", 1)
    assert t.headers == ["Description", "Qty", "Unit Price", "Amount"]
    row1 = t.rows()[1]
    assert row1[0].value == "Industrial Filter" and row1[3].value == "1,014.00"
    assert len(row1[3].bbox) == 4 and not t.low_quality

def test_multipage_tables_get_global_ids(tmp_path):
    pdf = render_invoice(many_items_spec(80), tmp_path / "m.pdf")
    tables = PyMuPDFTableExtractor().extract(str(pdf))
    assert len(tables) >= 2
    assert [t.table_id for t in tables] == [f"table_{i:02d}" for i in range(1, len(tables) + 1)]
    assert all(t.headers[0] == "Description" for t in tables)
```
`tests/unit/test_canonical.py`:
```python
from ledger_agent.extraction.canonical import build_document, describe, locate_cell
from ledger_agent.ingestion.pdf import ingest_pdf
from ledger_agent.ingestion.tables import extract_tables
from ledger_agent.models import Provenance
from ledger_agent.testing.invoices import default_spec, render_invoice

def test_document_and_provenance_roundtrip(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    doc = build_document("INV-001", ingest_pdf(pdf), extract_tables(pdf))
    assert doc.document_id == "INV-001" and doc.text_blocks and doc.tables
    prov = Provenance(document_id="INV-001", page=1, table_id="table_01", row=1, column="Amount")
    assert locate_cell(doc, prov).value == "1,014.00"
    canon = prov.model_copy(update={"column": "amount"})
    assert locate_cell(doc, canon).value == "1,014.00"
    assert describe(prov) == "Invoice INV-001 / Page 1 / table_01 / Row 1 / Column: Amount"
    assert locate_cell(doc, Provenance(document_id="INV-001", page=1)) is None
```
- [ ] **Step 2:** run the three files → FAIL.
- [ ] **Step 3: Implement**

`ingestion/__init__.py`, `extraction/__init__.py`: empty.

`ingestion/pdf.py`:
```python
import pymupdf

from ledger_agent.models import DocumentPage
from ledger_agent.protocols import OcrBackend


def ingest_pdf(path, min_chars: int = 30, ocr: OcrBackend | None = None) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    with pymupdf.open(str(path)) as doc:
        for number, page in enumerate(doc, start=1):
            text = page.get_text("text")
            blocks = [
                {"block_id": f"p{number}_b{n}", "bbox": [x0, y0, x1, y1], "text": t.strip()}
                for (x0, y0, x1, y1, t, n, kind) in page.get_text("blocks")
                if kind == 0 and t.strip()
            ]
            scanned = len(text.strip()) < min_chars
            if scanned and ocr is not None:
                text, blocks = ocr.recognize(page.get_pixmap(dpi=200).tobytes("png"))
                pages.append(DocumentPage(page_number=number, text=text, blocks=blocks, is_ocr=True))
            else:
                pages.append(DocumentPage(page_number=number, text=text, blocks=blocks,
                                          needs_ocr=scanned))
    return pages
```
`ingestion/tables.py`:
```python
import pymupdf

from ledger_agent.models import DocumentTable, TableCell


def _clean(value) -> str:
    return " ".join((value or "").split())


def extract_tables(path) -> list[DocumentTable]:
    out: list[DocumentTable] = []
    with pymupdf.open(str(path)) as doc:
        for page_no, page in enumerate(doc, start=1):
            for t in page.find_tables().tables:
                rows = t.extract()
                if len(rows) < 2:
                    continue
                headers = [_clean(h) for h in rows[0]]
                cells: list[TableCell] = []
                for r, trow in enumerate(t.rows):
                    for c, bbox in enumerate(trow.cells):
                        box = list(bbox) if bbox else list(trow.bbox)
                        cells.append(TableCell(value=_clean(rows[r][c]), row=r, column=c, bbox=box))
                filled = sum(1 for c in cells if c.value)
                low = (filled / len(cells) < 0.6) or any(not h for h in headers)
                out.append(DocumentTable(table_id=f"table_{len(out) + 1:02d}", page=page_no,
                                         headers=headers, cells=cells, bbox=list(t.bbox),
                                         low_quality=low))
    return out


class PyMuPDFTableExtractor:
    def extract(self, pdf_path: str) -> list[DocumentTable]:
        return extract_tables(pdf_path)
```
`extraction/canonical.py`:
```python
from ledger_agent.columns import column_map
from ledger_agent.models import Document, DocumentPage, DocumentTable, Provenance, TableCell, TextBlock


def build_document(document_id: str, pages: list[DocumentPage], tables: list[DocumentTable]) -> Document:
    blocks = [TextBlock(block_id=b["block_id"], page=p.page_number, text=b["text"], bbox=list(b["bbox"]))
              for p in pages for b in p.blocks]
    return Document(document_id=document_id, pages=pages, tables=tables, text_blocks=blocks)


def locate_cell(doc: Document, prov: Provenance) -> TableCell | None:
    if prov.table_id is None or prov.row is None or prov.column is None:
        return None
    table = doc.table(prov.table_id)
    if table is None:
        return None
    if prov.column in table.headers:
        col = table.headers.index(prov.column)
    else:
        col = column_map(table.headers, doc.column_overrides.get(table.table_id)).get(prov.column)
    if col is None:
        return None
    return next((c for c in table.cells if c.row == prov.row and c.column == col), None)


def describe(prov: Provenance) -> str:
    parts = [f"Invoice {prov.document_id}", f"Page {prov.page}"]
    if prov.table_id:
        parts.append(prov.table_id)
    if prov.row is not None:
        parts.append(f"Row {prov.row}")
    if prov.column:
        parts.append(f"Column: {prov.column}")
    return " / ".join(parts)
```
- [ ] **Step 4:** `python -m pytest tests/unit/test_ingestion.py tests/unit/test_tables.py tests/unit/test_canonical.py -v` → PASS. If `trow.cells` is unavailable in your PyMuPDF, upgrade to ≥1.24.
- [ ] **Step 5: Checkpoint** — tick Task 4.

---

### Task 5: Document-scoped hybrid retrieval (parallel group P1)

**Files:**
- Create: `src/ledger_agent/retrieval/{__init__,chunks,bm25,vector,hybrid}.py`
- Test: `tests/unit/test_retrieval.py`

**Interfaces:**
- Consumes: `Document`, `Chunk`, `ScoredChunk`, `Embedder`, `iter_line_item_rows`, `inside_any_table`, `parse_labeled_line`, `tokenize`, `make_document`, `HashingEmbedder`.
- Produces:
  - `build_chunks(doc) -> list[Chunk]`: one `line_item` chunk per row (`chunk_id=f"{doc_id}:{item_id}"`, `item_id`, `row_id`, `values` with printed strings for description/quantity/unit_price/amount, `provenance` with row bbox); one chunk per labeled totals line (`chunk_type` ∈ totals/tax/discount/shipping; `field`; `values={"amount": str(decimal)}`; tax chunks get `item_id=tax_NN` in order); other non-table blocks become `header`/`text`.
  - `InvoiceIndex(invoice_id, chunks, embedder)`; `.invoice_id`; `.search(invoice_id, query, k=5, mode="hybrid", chunk_types=None) -> list[ScoredChunk]` (mode ∈ hybrid|bm25|vector; RRF k=60); `.dispose()`; errors `InvoiceScopeError`, `IndexDisposedError`; `build_index(doc, embedder) -> InvoiceIndex`.

- [ ] **Step 1: Write failing tests** — `tests/unit/test_retrieval.py`:
```python
from decimal import Decimal as D
import pytest
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.retrieval.chunks import build_chunks
from ledger_agent.retrieval.hybrid import IndexDisposedError, InvoiceScopeError, build_index
from ledger_agent.testing.ledgers import make_document

EMB = HashingEmbedder()
TEN = tuple((f"Part {i:02d}", D("2"), D("5.00")) for i in range(1, 11))

def test_chunks_cover_rows_and_totals():
    chunks = build_chunks(make_document())
    by_type = {}
    for c in chunks:
        by_type.setdefault(c.chunk_type, []).append(c)
    li = by_type["line_item"]
    assert [c.item_id for c in li] == ["line_01", "line_02"]
    assert li[0].values["amount"] == "1,014.00" and li[0].row_id == 1 and li[0].table_id == "table_01"
    assert li[0].provenance.page == 1 and li[0].provenance.row == 1
    assert {c.field for c in by_type["totals"]} == {"subtotal", "total"}
    [tax] = by_type["tax"]
    assert tax.item_id == "tax_01" and tax.values["amount"] == "104.40"
    assert all(c.invoice_id == "INV-001" for c in chunks)
    assert not any("Industrial Filter" in c.text for c in by_type.get("text", []))

def test_source_row_is_in_top_k():
    idx = build_index(make_document(items=TEN), EMB)
    res = idx.search("INV-001", "line_07 Part 07 quantity unit price amount", k=3,
                     chunk_types=["line_item"])
    assert "line_07" in [r.chunk.item_id for r in res]

@pytest.mark.parametrize("mode", ["hybrid", "bm25", "vector"])
def test_modes_return_results(mode):
    idx = build_index(make_document(items=TEN), EMB)
    assert idx.search("INV-001", "Part 03 line_03", k=2, mode=mode)

def test_identical_line_items_resolve_by_item_id():
    same = (("Gasket", D("3"), D("10.00")),) * 3
    idx = build_index(make_document(items=same), EMB)
    top = idx.search("INV-001", "line_02 Gasket quantity unit price amount", k=3,
                     chunk_types=["line_item"])[0]
    assert top.chunk.item_id == "line_02"

def test_cross_invoice_queries_are_rejected_and_never_leak():
    a = build_index(make_document(invoice_id="INV-A"), EMB)
    b = build_index(make_document(invoice_id="INV-B"), EMB)
    with pytest.raises(InvoiceScopeError):
        a.search("INV-B", "total")
    assert all(r.chunk.invoice_id == "INV-A" for r in a.search("INV-A", "total", k=10))
    assert all(r.chunk.invoice_id == "INV-B" for r in b.search("INV-B", "total", k=10))

def test_dispose():
    idx = build_index(make_document(), EMB)
    idx.dispose()
    with pytest.raises(IndexDisposedError):
        idx.search("INV-001", "total")
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement**

`retrieval/__init__.py`: empty.

`retrieval/chunks.py`:
```python
from ledger_agent.columns import inside_any_table, iter_line_item_rows
from ledger_agent.models import Chunk, Document, Provenance
from ledger_agent.textparse import parse_labeled_line

_TYPE = {"subtotal": "totals", "total": "totals", "tax": "tax", "discount": "discount",
         "shipping": "shipping", "fees": "shipping"}


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def build_chunks(doc: Document) -> list[Chunk]:
    inv = doc.document_id
    chunks: list[Chunk] = []
    for r in iter_line_item_rows(doc):
        values = {f: c.value for f, c in r.cells.items()}
        text = (f"Invoice {inv} | Page {r.table.page} | {r.table.table_id} | Row {r.row} | {r.item_id}\n"
                f"Description: {values['description']}\nQuantity: {values['quantity']}\n"
                f"Unit Price: {values['unit_price']}\nAmount: {values['amount']}")
        prov = Provenance(document_id=inv, page=r.table.page, table_id=r.table.table_id,
                          row=r.row, bbox=_union([c.bbox for c in r.cells.values()]))
        chunks.append(Chunk(chunk_id=f"{inv}:{r.item_id}", invoice_id=inv, chunk_type="line_item",
                            text=text, page=r.table.page, table_id=r.table.table_id,
                            row_id=r.row, item_id=r.item_id, values=values, provenance=prov))
    tax_n = 0
    for block in sorted(doc.text_blocks, key=lambda b: (b.page, b.bbox[1], b.bbox[0])):
        if inside_any_table(doc, block):
            continue
        for n, line in enumerate(block.text.splitlines()):
            prov = Provenance(document_id=inv, page=block.page, block_id=block.block_id,
                              bbox=block.bbox)
            la = parse_labeled_line(line)
            if la is None:
                kind = "header" if "invoice #" in line.lower() else "text"
                chunks.append(Chunk(chunk_id=f"{inv}:{block.block_id}:{n}", invoice_id=inv,
                                    chunk_type=kind, text=f"Invoice {inv} | Page {block.page} | {line}",
                                    page=block.page, provenance=prov))
                continue
            item_id = None
            if la.field == "tax":
                tax_n += 1
                item_id = f"tax_{tax_n:02d}"
            chunks.append(Chunk(
                chunk_id=f"{inv}:{block.block_id}:{n}", invoice_id=inv, chunk_type=_TYPE[la.field],
                text=f"Invoice {inv} | Page {block.page} | {item_id or la.field} | {line.strip()}",
                page=block.page, item_id=item_id, field=la.field,
                values={"amount": str(la.amount)}, provenance=prov))
    return chunks
```
`retrieval/bm25.py`:
```python
from rank_bm25 import BM25Okapi

from ledger_agent.models import Chunk
from ledger_agent.textparse import tokenize


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        self._chunks = chunks
        self._bm25 = BM25Okapi([tokenize(c.text) or ["_"] for c in chunks]) if chunks else None

    def scores(self, query: str) -> list[float]:
        if self._bm25 is None:
            return []
        return [float(s) for s in self._bm25.get_scores(tokenize(query))]
```
`retrieval/vector.py`:
```python
import numpy as np

from ledger_agent.models import Chunk
from ledger_agent.protocols import Embedder


class VectorIndex:
    def __init__(self, chunks: list[Chunk], embedder: Embedder):
        self._embedder = embedder
        m = np.array(embedder.embed([c.text for c in chunks]), dtype=float) if chunks else np.zeros((0, 1))
        norms = np.linalg.norm(m, axis=1, keepdims=True) if len(m) else m
        self._m = m / np.where(norms == 0, 1, norms) if len(m) else m

    def scores(self, query: str) -> list[float]:
        if len(self._m) == 0:
            return []
        q = np.array(self._embedder.embed([query])[0], dtype=float)
        n = np.linalg.norm(q)
        q = q / n if n else q
        return [float(s) for s in self._m @ q]
```
`retrieval/hybrid.py`:
```python
from ledger_agent.models import Chunk, Document, ScoredChunk
from ledger_agent.protocols import Embedder
from ledger_agent.retrieval.bm25 import BM25Index
from ledger_agent.retrieval.chunks import build_chunks
from ledger_agent.retrieval.vector import VectorIndex

RRF_K = 60


class InvoiceScopeError(Exception):
    pass


class IndexDisposedError(Exception):
    pass


def _ranks(scores: list[float]) -> dict[int, int]:
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    return {idx: rank for rank, idx in enumerate(order)}


class InvoiceIndex:
    def __init__(self, invoice_id: str, chunks: list[Chunk], embedder: Embedder):
        stray = [c.chunk_id for c in chunks if c.invoice_id != invoice_id]
        if stray:
            raise InvoiceScopeError(f"chunks from another invoice: {stray}")
        self.invoice_id = invoice_id
        self._chunks: list[Chunk] | None = chunks
        self._bm25: BM25Index | None = BM25Index(chunks)
        self._vec: VectorIndex | None = VectorIndex(chunks, embedder)

    def search(self, invoice_id: str, query: str, k: int = 5, mode: str = "hybrid",
               chunk_types: list[str] | None = None) -> list[ScoredChunk]:
        if self._chunks is None:
            raise IndexDisposedError("index was disposed")
        if invoice_id != self.invoice_id:
            raise InvoiceScopeError(f"query for {invoice_id!r} on index of {self.invoice_id!r}")
        lists = []
        if mode in ("hybrid", "bm25"):
            lists.append(_ranks(self._bm25.scores(query)))
        if mode in ("hybrid", "vector"):
            lists.append(_ranks(self._vec.scores(query)))
        if not lists:
            raise ValueError(f"unknown mode {mode!r}")
        fused = {i: sum(1.0 / (RRF_K + r[i]) for r in lists) for i in range(len(self._chunks))}
        keep = [i for i in fused if chunk_types is None or self._chunks[i].chunk_type in chunk_types]
        keep.sort(key=lambda i: (-fused[i], i))
        return [ScoredChunk(chunk=self._chunks[i], score=fused[i]) for i in keep[:k]]

    def dispose(self) -> None:
        self._chunks = self._bm25 = self._vec = None


def build_index(doc: Document, embedder: Embedder) -> InvoiceIndex:
    return InvoiceIndex(doc.document_id, build_chunks(doc), embedder)
```
- [ ] **Step 4:** `python -m pytest tests/unit/test_retrieval.py -v` → PASS.
- [ ] **Step 5: Checkpoint** — tick Task 5.

---

### Task 6: Deterministic ledger builder (after Task 4)

**Files:**
- Create: `src/ledger_agent/extraction/ledger.py`
- Test: `tests/unit/test_ledger_builder.py`

**Interfaces:**
- Consumes: `Document`, `iter_line_item_rows`, `column_map`, `REQUIRED`, `inside_any_table`, `parse_labeled_line`, `parse_money`, `LLMClient`, `FakeLLM`.
- Produces: `ExtractionError`; `build_ledger(doc: Document) -> Ledger` (every item field has `source[field]` provenance with printed header as `column`; header-level values carry `sources[field]` with `block_id`; tax lines `tax_NN` in order; `tax` = sum of tax lines; `currency` from `Currency: XXX`, default USD; `invoice_id = doc.document_id`); `resolve_column_overrides(doc, llm: LLMClient | None) -> dict[str, dict[str, int]]`.

- [ ] **Step 1: Write failing tests** — `tests/unit/test_ledger_builder.py`:
```python
from decimal import Decimal as D
import pytest
from ledger_agent.config import ValidationRules
from ledger_agent.extraction.canonical import build_document, locate_cell
from ledger_agent.extraction.ledger import ExtractionError, build_ledger, resolve_column_overrides
from ledger_agent.fakes import FakeLLM
from ledger_agent.ingestion.pdf import ingest_pdf
from ledger_agent.ingestion.tables import extract_tables
from ledger_agent.testing.invoices import InvoiceSpec, ItemSpec, default_spec, many_items_spec, render_invoice
from ledger_agent.testing.ledgers import make_document, make_ledger
from ledger_agent.validation.arithmetic import validate

def doc_from(spec, tmp_path):
    pdf = render_invoice(spec, tmp_path / f"{spec.invoice_id}.pdf")
    return build_document(spec.invoice_id, ingest_pdf(pdf), extract_tables(pdf))

def test_hand_built_document_matches_reference_ledger():
    led = build_ledger(make_document())
    ref = make_ledger()
    assert (led.subtotal, led.tax, led.total) == (ref.subtotal, ref.tax, ref.total)
    assert led.items[0].amount == D("1014.00") and led.tax_lines[0].rate == D("0.10")

def test_real_pdf_roundtrip_has_provenance(tmp_path):
    spec = default_spec()
    doc = doc_from(spec, tmp_path)
    led = build_ledger(doc)
    assert led.invoice_id == "INV-001" and led.currency == "USD"
    assert validate(led, ValidationRules()) == []
    src = led.items[0].source["amount"]
    assert (src.page, src.table_id, src.row, src.column) == (1, "table_01", 1, "Amount")
    assert locate_cell(doc, src).value == "1,014.00"
    assert led.sources["total"].block_id

def test_discount_shipping_multi_tax(tmp_path):
    spec = default_spec()
    spec.discount, spec.shipping = D("44.00"), D("15.00")
    spec.tax_rates = (D("0.05"), D("0.07"))
    led = build_ledger(doc_from(spec, tmp_path))
    assert led.discount == D("44.00") and led.shipping == D("15.00") and len(led.tax_lines) == 2
    assert validate(led, ValidationRules()) == []

def test_multipage_item_ids_are_global(tmp_path):                      # Review Focus 1
    led = build_ledger(doc_from(many_items_spec(80), tmp_path))
    assert [i.id for i in led.items] == [f"line_{n:02d}" for n in range(1, 81)]
    assert validate(led, ValidationRules()) == []

def test_missing_total_or_table_raises(tmp_path):                      # Review Focus 4
    doc = make_document()
    doc.text_blocks = [b for b in doc.text_blocks if not b.text.startswith("Total")]
    with pytest.raises(ExtractionError, match="grand total"):
        build_ledger(doc)
    doc2 = make_document()
    doc2.tables = []
    with pytest.raises(ExtractionError, match="line-item"):
        build_ledger(doc2)

def test_llm_maps_unknown_headers():
    doc = make_document()
    t = doc.tables[0]
    t.headers = ["Part", "Count", "Each", "Line Cost"]
    assert resolve_column_overrides(doc, None) == {}
    llm = FakeLLM([{"mapping": {"Part": "description", "Count": "quantity",
                                "Each": "unit_price", "Line Cost": "amount"}}])
    doc.column_overrides = resolve_column_overrides(doc, llm)
    assert doc.column_overrides == {"table_01": {"description": 0, "quantity": 1, "unit_price": 2, "amount": 3}}
    assert build_ledger(doc).items[0].amount == D("1014.00")

def test_llm_incomplete_mapping_is_ignored():
    doc = make_document()
    doc.tables[0].headers = ["Part", "Count", "Each", "Line Cost"]
    llm = FakeLLM([{"mapping": {"Part": "description"}}])
    assert resolve_column_overrides(doc, llm) == {}
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** `extraction/ledger.py`:
```python
import json
import re
from decimal import Decimal

from ledger_agent.columns import REQUIRED, column_map, inside_any_table, iter_line_item_rows
from ledger_agent.models import Document, Ledger, LineItem, Provenance, TaxLine
from ledger_agent.money import parse_money
from ledger_agent.protocols import LLMClient
from ledger_agent.textparse import parse_labeled_line

_CCY = re.compile(r"Currency:\s*([A-Z]{3})")
_SYSTEM = "Map each invoice table header to one of: description, quantity, unit_price, amount, or null."
_SCHEMA = {"type": "object", "properties": {"mapping": {"type": "object"}}, "required": ["mapping"]}


class ExtractionError(Exception):
    pass


def resolve_column_overrides(doc: Document, llm: LLMClient | None) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    if llm is None:
        return out
    for t in doc.tables:
        if REQUIRED <= column_map(t.headers).keys() or len(t.headers) < 3:
            continue
        mapping = llm.complete_json(_SYSTEM, json.dumps({"headers": t.headers}), _SCHEMA).get("mapping", {})
        cmap: dict[str, int] = {}
        for header, canon in mapping.items():
            if canon in REQUIRED and header in t.headers and canon not in cmap:
                cmap[canon] = t.headers.index(header)
        if REQUIRED <= cmap.keys():
            out[t.table_id] = cmap
    return out


def build_ledger(doc: Document) -> Ledger:
    inv = doc.document_id
    items: list[LineItem] = []
    for r in iter_line_item_rows(doc):
        def prov(field: str, _r=r) -> Provenance:
            return Provenance(document_id=inv, page=_r.table.page, table_id=_r.table.table_id,
                              row=_r.row, column=_r.headers[field], bbox=_r.cells[field].bbox)
        try:
            qty = parse_money(r.cells["quantity"].value)
            price = parse_money(r.cells["unit_price"].value)
            amount = parse_money(r.cells["amount"].value)
        except ValueError as exc:
            raise ExtractionError(f"{r.item_id}: {exc}") from exc
        items.append(LineItem(id=r.item_id, description=r.cells["description"].value,
                              quantity=qty, unit_price=price, amount=amount,
                              source={f: prov(f) for f in REQUIRED}))
    if not items:
        raise ExtractionError("no line-item table found")

    scalars: dict[str, Decimal] = {}
    sources: dict[str, Provenance] = {}
    tax_lines: list[TaxLine] = []
    currency = "USD"
    for block in sorted(doc.text_blocks, key=lambda b: (b.page, b.bbox[1], b.bbox[0])):
        if inside_any_table(doc, block):
            continue
        for line in block.text.splitlines():
            m = _CCY.search(line)
            if m:
                currency = m.group(1)
            la = parse_labeled_line(line)
            if la is None:
                continue
            src = Provenance(document_id=inv, page=block.page, block_id=block.block_id, bbox=block.bbox)
            if la.field == "tax":
                tax_lines.append(TaxLine(id=f"tax_{len(tax_lines) + 1:02d}", rate=la.rate,
                                         amount=la.amount, source={"amount": src}))
            elif la.field not in scalars:
                scalars[la.field] = la.amount
                sources[la.field] = src
    if "total" not in scalars:
        raise ExtractionError("no grand total found")
    tax = sum((t.amount for t in tax_lines), Decimal("0")) if tax_lines else None
    return Ledger(invoice_id=inv, currency=currency, items=items, subtotal=scalars.get("subtotal"),
                  discount=scalars.get("discount"), tax=tax, tax_lines=tax_lines,
                  shipping=scalars.get("shipping"), fees=scalars.get("fees"),
                  total=scalars["total"], sources=sources)
```
- [ ] **Step 4:** `python -m pytest tests/unit/test_ledger_builder.py -v` → PASS.
- [ ] **Step 5: Checkpoint** — tick Task 6; end of Wave 1 — update `progress.md` with test counts.

---

### Task 7: Self-correction guards (parallel group P2)

**Files:**
- Create: `src/ledger_agent/agents/{__init__,guards}.py`
- Test: `tests/unit/test_guards.py`

**Interfaces:**
- Produces: `signatures(ds: list[Discrepancy]) -> frozenset[tuple]` of `(field, expected, observed, difference)`; `decide_after_validate(discrepancies, prev_signatures, revision, max_revisions) -> Literal["finalize","audit","no_progress","max_revisions"]`.

- [ ] **Step 1: Test** — `tests/unit/test_guards.py`:
```python
from decimal import Decimal as D
from ledger_agent.agents.guards import decide_after_validate, signatures
from ledger_agent.models import Discrepancy

def disc(obs="1040.00"):
    return Discrepancy(field="items[line_01].amount", expected=D("1014.00"), observed=D(obs),
                       difference=D(obs) - D("1014.00"), rule="line_amount")

def test_no_discrepancies_finalizes():
    assert decide_after_validate([], None, 0, 3) == "finalize"

def test_first_failure_audits():
    assert decide_after_validate([disc()], None, 0, 3) == "audit"

def test_same_signature_is_no_progress():
    assert decide_after_validate([disc()], signatures([disc()]), 1, 3) == "no_progress"

def test_changed_signature_continues_until_revisions_exhausted():
    prev = signatures([disc("1040.00")])
    assert decide_after_validate([disc("1050.00")], prev, 2, 3) == "audit"
    assert decide_after_validate([disc("1050.00")], prev, 3, 3) == "max_revisions"

def test_zero_max_revisions_blocks_correction():
    assert decide_after_validate([disc()], None, 0, 0) == "max_revisions"

def test_no_progress_takes_priority_over_max():
    assert decide_after_validate([disc()], signatures([disc()]), 3, 3) == "no_progress"
```
- [ ] **Step 2:** FAIL. **Step 3:** `agents/__init__.py` empty; `agents/guards.py`:
```python
from typing import Literal

from ledger_agent.models import Discrepancy

Outcome = Literal["finalize", "audit", "no_progress", "max_revisions"]


def signatures(discrepancies: list[Discrepancy]) -> frozenset[tuple]:
    return frozenset((d.field, d.expected, d.observed, d.difference) for d in discrepancies)


def decide_after_validate(discrepancies: list[Discrepancy], prev_signatures,
                          revision: int, max_revisions: int) -> Outcome:
    if not discrepancies:
        return "finalize"
    if prev_signatures is not None and signatures(discrepancies) == prev_signatures:
        return "no_progress"
    if revision >= max_revisions:
        return "max_revisions"
    return "audit"
```
- [ ] **Step 4:** `python -m pytest tests/unit/test_guards.py -v` → PASS. **Step 5:** checkpoint — tick Task 7.

---

### Task 8: Audit agent and evidence verification (parallel group P2; needs Task 5)

**Files:**
- Create: `src/ledger_agent/agents/audit.py`
- Test: `tests/unit/test_audit.py`

**Interfaces:**
- Consumes: `InvoiceIndex`, `Discrepancy`, `Evidence`, `ScoredChunk`, `parse_path`, `parse_money`, `LLMClient`, `FakeLLM`.
- Produces:
  - `EvidenceProposer` protocol: `propose(discrepancy, chunks: list[ScoredChunk]) -> list[Evidence]`.
  - `ChunkValueProposer` (deterministic): for each path in `discrepancy.related_fields`, takes the first retrieved chunk that structurally matches (item: `line_item` with same `item_id`; tax line: `tax` chunk with same `item_id`; scalar: chunk with `field == name`, and **never** scalar `tax`); evidence value is the chunk's printed value; confidence = 0.97 rank 0, 0.92 rank 1–2, else 0.80; `source = chunk.provenance` with `column` set to the attribute name.
  - `LLMProposer(llm)`: same output type from `llm.complete_json` returning `{"evidence":[{"field","value","chunk_id","confidence"}]}`; provenance always taken from the retrieved chunk with that `chunk_id` (unknown ids dropped).
  - `build_query(discrepancy, ledger) -> tuple[str, list[str] | None]`; `AuditCandidates(discrepancy, query, retrieved, evidence)` dataclass; `retrieve_and_propose(discrepancy, ledger, index, proposer, k) -> AuditCandidates`; `verify_evidence(ev, discrepancy, chunks, invoice_id, threshold) -> str | None` (reason or None); `verify_candidates(cand, invoice_id, threshold) -> tuple[list[Evidence], list[tuple[Evidence, str]]]`.
  - Verification rules, in order: field ∈ `related_fields`; chunk (by `chunk_id`) is in the retrieved set; `chunk.invoice_id == invoice_id == ev.source.document_id`; page/table/row match chunk; structural target match (as above); value equals `parse_money(chunk.values[attr])`; confidence ≥ threshold.

- [ ] **Step 1: Tests** — `tests/unit/test_audit.py`:
```python
from decimal import Decimal as D
from ledger_agent.agents.audit import (ChunkValueProposer, LLMProposer, build_query,
                                       retrieve_and_propose, verify_candidates, verify_evidence)
from ledger_agent.fakes import FakeLLM, HashingEmbedder
from ledger_agent.paths import set_field
from ledger_agent.retrieval.hybrid import build_index
from ledger_agent.testing.ledgers import make_document, make_ledger
from ledger_agent.validation.arithmetic import validate
from ledger_agent.config import ValidationRules

EMB = HashingEmbedder()

def setup(items=None):
    doc = make_document(items=items)
    ledger = set_field(make_ledger(items=items), "items[line_01].amount", D("1040.00"))
    d = next(x for x in validate(ledger, ValidationRules()) if x.field == "items[line_01].amount")
    return doc, ledger, d, build_index(doc, EMB)

def test_build_query_targets_the_item():
    _, ledger, d, _ = setup()
    q, types = build_query(d, ledger)
    assert "line_01" in q and "Industrial Filter" in q and types == ["line_item"]

def test_line_discrepancy_yields_verified_evidence_with_source_row():
    _, ledger, d, idx = setup()
    cand = retrieve_and_propose(d, ledger, idx, ChunkValueProposer(), k=5)
    ok, rejected = verify_candidates(cand, "INV-001", 0.90)
    by_field = {e.field: e for e in ok}
    amt = by_field["items[line_01].amount"]
    assert amt.value == D("1014.00") and amt.confidence >= 0.97
    assert (amt.source.page, amt.source.table_id, amt.source.row) == (1, "table_01", 1)
    assert not rejected

def test_total_discrepancy_never_proposes_derived_tax_scalar():
    doc = make_document(tax_rates=(D("0.05"), D("0.07")))
    ledger = make_ledger(tax_rates=(D("0.05"), D("0.07"))).model_copy(update={"total": D("1.00")})
    d = validate(ledger, ValidationRules())[0]
    idx = build_index(doc, EMB)
    cand = retrieve_and_propose(d, ledger, idx, ChunkValueProposer(), k=5)
    assert "tax" not in {e.field for e in cand.evidence}
    assert "total" in {e.field for e in cand.evidence}

def test_verifier_rejects_low_confidence_foreign_and_tampered_evidence():
    _, ledger, d, idx = setup()
    cand = retrieve_and_propose(d, ledger, idx, ChunkValueProposer(), k=5)
    ev = next(e for e in cand.evidence if e.field == "items[line_01].amount")
    chunks = cand.retrieved
    assert verify_evidence(ev, d, chunks, "INV-001", 0.90) is None
    assert "confidence" in verify_evidence(ev.model_copy(update={"confidence": 0.5}), d, chunks, "INV-001", 0.90)
    assert "invoice" in verify_evidence(ev, d, chunks, "INV-OTHER", 0.90)
    assert "value" in verify_evidence(ev.model_copy(update={"value": D("999.00")}), d, chunks, "INV-001", 0.90)
    assert "related" in verify_evidence(ev.model_copy(update={"field": "total"}), d, chunks, "INV-001", 0.90)
    assert "retrieved" in verify_evidence(ev.model_copy(update={"chunk_id": "nope"}), d, chunks, "INV-001", 0.90)
    src = ev.source.model_copy(update={"row": 2})
    assert "source" in verify_evidence(ev.model_copy(update={"source": src}), d, chunks, "INV-001", 0.90)

def test_llm_proposer_cannot_invent_provenance_or_values():
    _, ledger, d, idx = setup()
    cand = retrieve_and_propose(d, ledger, idx, ChunkValueProposer(), k=5)
    real = next(s.chunk for s in cand.retrieved if s.chunk.item_id == "line_01")
    llm = FakeLLM([{"evidence": [
        {"field": "items[line_01].amount", "value": "1014.00", "chunk_id": real.chunk_id, "confidence": 0.95},
        {"field": "items[line_01].amount", "value": "1014.00", "chunk_id": "ghost", "confidence": 0.99},
        {"field": "items[line_01].amount", "value": "oops", "chunk_id": real.chunk_id, "confidence": 0.99},
    ]}])
    evs = LLMProposer(llm).propose(d, cand.retrieved)
    assert len(evs) == 1 and evs[0].source.row == 1 and evs[0].value == D("1014.00")
    ok, _ = verify_candidates(type(cand)(d, cand.query, cand.retrieved, evs), "INV-001", 0.90)
    assert len(ok) == 1
```
- [ ] **Step 2:** FAIL. **Step 3: Implement** `agents/audit.py`:
```python
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from ledger_agent.models import Chunk, Discrepancy, Evidence, Ledger, ScoredChunk
from ledger_agent.money import parse_money
from ledger_agent.paths import PathRef, parse_path
from ledger_agent.protocols import LLMClient
from ledger_agent.retrieval.hybrid import InvoiceIndex

_SCALAR_TYPES = ["totals", "tax", "discount", "shipping"]


class EvidenceProposer(Protocol):
    def propose(self, discrepancy: Discrepancy, chunks: list[ScoredChunk]) -> list[Evidence]: ...


@dataclass
class AuditCandidates:
    discrepancy: Discrepancy
    query: str
    retrieved: list[ScoredChunk]
    evidence: list[Evidence]


def _attr(ref: PathRef) -> str:
    return ref.attr if ref.kind == "item" else "amount"


def _targets(chunk: Chunk, ref: PathRef) -> bool:
    if ref.kind == "item":
        return chunk.chunk_type == "line_item" and chunk.item_id == ref.id
    if ref.kind == "tax":
        return ref.attr == "amount" and chunk.chunk_type == "tax" and chunk.item_id == ref.id
    if ref.attr == "tax":           # scalar tax is derived from tax lines; never evidence
        return False
    return chunk.chunk_type != "line_item" and chunk.field == ref.attr


def build_query(discrepancy: Discrepancy, ledger: Ledger) -> tuple[str, list[str] | None]:
    ref = parse_path(discrepancy.field)
    if ref.kind == "item":
        item = next((i for i in ledger.items if i.id == ref.id), None)
        desc = item.description if item else ""
        return f"{ref.id} {desc} quantity unit price amount", ["line_item"]
    if ref.kind == "tax":
        return f"{ref.id} tax rate amount", ["tax"]
    return f"{ref.attr} " + " ".join(discrepancy.related_fields), _SCALAR_TYPES


def retrieve_and_propose(discrepancy, ledger, index: InvoiceIndex, proposer, k: int) -> AuditCandidates:
    query, types = build_query(discrepancy, ledger)
    k = max(k, len(discrepancy.related_fields) + 3)
    retrieved = index.search(index.invoice_id, query, k=k, chunk_types=types)
    return AuditCandidates(discrepancy, query, retrieved, proposer.propose(discrepancy, retrieved))


class ChunkValueProposer:
    def propose(self, discrepancy: Discrepancy, chunks: list[ScoredChunk]) -> list[Evidence]:
        out: list[Evidence] = []
        for path in discrepancy.related_fields:
            ref = parse_path(path)
            for rank, sc in enumerate(chunks):
                ch = sc.chunk
                if not _targets(ch, ref):
                    continue
                raw = ch.values.get(_attr(ref))
                try:
                    value = parse_money(raw) if raw is not None else None
                except ValueError:
                    value = None
                if value is not None:
                    conf = 0.97 if rank == 0 else 0.92 if rank < 3 else 0.80
                    out.append(Evidence(field=path, value=value, confidence=conf,
                                        chunk_id=ch.chunk_id, quote=ch.text,
                                        source=ch.provenance.model_copy(update={"column": _attr(ref)})))
                break
        return out


class LLMProposer:
    _SYSTEM = ("You are auditing one invoice. Using ONLY the provided chunks, report the printed "
               "value for each requested field. Return JSON {evidence:[{field,value,chunk_id,confidence}]}.")

    def __init__(self, llm: LLMClient):
        self._llm = llm

    def propose(self, discrepancy: Discrepancy, chunks: list[ScoredChunk]) -> list[Evidence]:
        prompt = json.dumps({
            "discrepancy": discrepancy.model_dump(mode="json"),
            "chunks": [{"chunk_id": s.chunk.chunk_id, "text": s.chunk.text} for s in chunks],
        })
        resp = self._llm.complete_json(self._SYSTEM, prompt, {"type": "object"})
        by_id = {s.chunk.chunk_id: s.chunk for s in chunks}
        out: list[Evidence] = []
        for item in resp.get("evidence", []):
            ch = by_id.get(item.get("chunk_id"))
            if ch is None:
                continue
            try:
                value = parse_money(str(item["value"]))
                conf = float(item["confidence"])
                path = item["field"]
                attr = _attr(parse_path(path))
            except (KeyError, ValueError, TypeError):
                continue
            out.append(Evidence(field=path, value=value, confidence=conf, chunk_id=ch.chunk_id,
                                quote=ch.text, source=ch.provenance.model_copy(update={"column": attr})))
        return out


def verify_evidence(ev: Evidence, discrepancy: Discrepancy, chunks: list[ScoredChunk],
                    invoice_id: str, threshold: float) -> str | None:
    if ev.field not in discrepancy.related_fields:
        return "field not related to discrepancy"
    chunk = next((s.chunk for s in chunks if s.chunk.chunk_id == ev.chunk_id), None)
    if chunk is None:
        return "evidence chunk was not retrieved"
    if not (chunk.invoice_id == invoice_id == ev.source.document_id):
        return "evidence is from a different invoice"
    if (ev.source.page, ev.source.table_id, ev.source.row) != (chunk.page, chunk.table_id, chunk.row_id):
        return "source location does not match chunk"
    ref = parse_path(ev.field)
    if not _targets(chunk, ref):
        return "chunk does not describe the target field"
    raw = chunk.values.get(_attr(ref))
    try:
        if raw is None or parse_money(raw) != ev.value:
            return "value does not match chunk"
    except ValueError:
        return "value does not match chunk"
    if ev.confidence < threshold:
        return f"confidence {ev.confidence:.2f} below threshold {threshold:.2f}"
    return None


def verify_candidates(cand: AuditCandidates, invoice_id: str, threshold: float):
    ok: list[Evidence] = []
    rejected: list[tuple[Evidence, str]] = []
    for ev in cand.evidence:
        reason = verify_evidence(ev, cand.discrepancy, cand.retrieved, invoice_id, threshold)
        (rejected.append((ev, reason)) if reason else ok.append(ev))
    return ok, rejected
```
Verifier messages must contain the substrings asserted in the test: "confidence", "invoice", "value", "related", "retrieved", "source" — they do ("different invoice", "value does not match", "not related", "was not retrieved", "source location").
- [ ] **Step 4:** `python -m pytest tests/unit/test_audit.py -v` → PASS. **Step 5:** checkpoint — tick Task 8.

---

### Task 9: Reconciliation — patches with safety checks (parallel group P2)

**Files:**
- Create: `src/ledger_agent/agents/reconciliation.py`
- Test: `tests/unit/test_reconciliation.py`

**Interfaces:**
- Consumes: `Ledger`, `Evidence`, `Patch`, `AuditRecord`, `get_field`, `set_field`, `PathError`.
- Produces: `PatchRejected(Exception)`; `propose_patches(ledger, evidence) -> list[Patch]` (skips evidence whose value equals the current value or whose path doesn't exist; one patch per path, highest confidence wins); `check_patch(ledger, patch, threshold) -> None` (raises `PatchRejected`: field missing, `old_value` ≠ current, source missing, confidence < threshold); `apply_patches(ledger, patches, revision, threshold) -> tuple[Ledger, list[AuditRecord]]` (sequential; original not mutated).

- [ ] **Step 1: Tests** — `tests/unit/test_reconciliation.py`:
```python
from decimal import Decimal as D
import pytest
from ledger_agent.agents.reconciliation import PatchRejected, apply_patches, check_patch, propose_patches
from ledger_agent.models import Evidence, Patch, Provenance
from ledger_agent.paths import get_field, set_field
from ledger_agent.testing.ledgers import make_ledger

def ev(field="items[line_01].amount", value="1014.00", conf=0.97):
    return Evidence(field=field, value=D(value), confidence=conf, chunk_id="c1",
                    source=Provenance(document_id="INV-001", page=1, table_id="table_01", row=1))

def bad_ledger():
    return set_field(make_ledger(), "items[line_01].amount", D("1040.00"))

def test_propose_skips_equal_values_and_unknown_paths():
    led = make_ledger()
    assert propose_patches(led, [ev()]) == []
    assert propose_patches(bad_ledger(), [ev(field="items[line_99].amount")]) == []

def test_propose_dedupes_by_highest_confidence():
    ps = propose_patches(bad_ledger(), [ev(conf=0.91), ev(conf=0.99)])
    assert len(ps) == 1 and ps[0].confidence == 0.99
    assert (ps[0].old_value, ps[0].new_value, ps[0].source_table, ps[0].source_row) == (D("1040.00"), D("1014.00"), "table_01", 1)

def test_apply_records_revision_and_does_not_mutate_input():
    led = bad_ledger()
    new, records = apply_patches(led, propose_patches(led, [ev()]), revision=1, threshold=0.90)
    assert get_field(new, "items[line_01].amount") == D("1014.00")
    assert get_field(led, "items[line_01].amount") == D("1040.00")
    r = records[0]
    assert (r.revision, r.field, r.old_value, r.new_value, r.source_page, r.source_row) == \
           (1, "items[line_01].amount", D("1040.00"), D("1014.00"), 1, 1)

def patch(**kw):
    base = dict(path="items[line_01].amount", old_value=D("1040.00"), new_value=D("1014.00"),
                reason="r", source_page=1, source_table="table_01", source_row=1, confidence=0.97)
    base.update(kw)
    return Patch(**base)

@pytest.mark.parametrize("kw", [
    {"confidence": 0.5}, {"old_value": D("1.00")}, {"source_page": None}, {"path": "items[line_99].amount"},
])
def test_safety_checks_reject(kw):
    with pytest.raises(PatchRejected):
        check_patch(bad_ledger(), patch(**kw), 0.90)

def test_check_passes_for_valid_patch():
    check_patch(bad_ledger(), patch(), 0.90)
```
- [ ] **Step 2:** FAIL. **Step 3:** `agents/reconciliation.py`:
```python
from ledger_agent.models import AuditRecord, Evidence, Ledger, Patch
from ledger_agent.paths import PathError, get_field, set_field


class PatchRejected(Exception):
    pass


def propose_patches(ledger: Ledger, evidence: list[Evidence]) -> list[Patch]:
    best: dict[str, Patch] = {}
    for ev in evidence:
        try:
            current = get_field(ledger, ev.field)
        except PathError:
            continue
        if current is None or current == ev.value:
            continue
        patch = Patch(path=ev.field, old_value=current, new_value=ev.value,
                      reason="Source invoice evidence", source_page=ev.source.page,
                      source_table=ev.source.table_id, source_row=ev.source.row,
                      confidence=ev.confidence)
        if ev.field not in best or patch.confidence > best[ev.field].confidence:
            best[ev.field] = patch
    return list(best.values())


def check_patch(ledger: Ledger, patch: Patch, threshold: float) -> None:
    try:
        current = get_field(ledger, patch.path)
    except PathError as exc:
        raise PatchRejected(f"field does not exist: {patch.path}") from exc
    if current is None:
        raise PatchRejected(f"field is not set: {patch.path}")
    if current != patch.old_value:
        raise PatchRejected(f"old value mismatch for {patch.path}")
    if patch.source_page is None:
        raise PatchRejected(f"no source evidence for {patch.path}")
    if patch.confidence < threshold:
        raise PatchRejected(f"confidence {patch.confidence:.2f} below threshold for {patch.path}")


def apply_patches(ledger: Ledger, patches: list[Patch], revision: int,
                  threshold: float) -> tuple[Ledger, list[AuditRecord]]:
    current = ledger
    records: list[AuditRecord] = []
    for p in patches:
        check_patch(current, p, threshold)
        current = set_field(current, p.path, p.new_value)
        records.append(AuditRecord(revision=revision, field=p.path, old_value=p.old_value,
                                   new_value=p.new_value, reason=p.reason, source_page=p.source_page,
                                   source_table=p.source_table, source_row=p.source_row,
                                   confidence=p.confidence))
    return current, records
```
- [ ] **Step 4:** `python -m pytest tests/unit/test_reconciliation.py -v` → PASS. **Step 5:** checkpoint — tick Task 9; end of Wave 2a.

---

### Task 10: LangGraph assembly

**Files:**
- Create: `src/ledger_agent/graph.py`
- Test: `tests/integration/test_graph_smoke.py`

**Interfaces:**
- Consumes: all prior modules.
- Produces: `Deps` dataclass (`embedder`, `proposer`, `config=Config()`, `llm=None`, `ocr=None`, `table_extractor=PyMuPDFTableExtractor()`, `ledger_builder=build_ledger`, `validator=validate`); `build_graph(deps) -> CompiledStateGraph`; `ReconciliationResult(invoice_id, status, iterations, ledger, original_ledger, corrections, evidence, error)`; `run_invoice(pdf_path, deps, invoice_id=None) -> ReconciliationResult`. Nodes: `ingest, extract, build_index, build_ledger, validate, audit, verify_evidence, reconcile, finalize, failed`. Every node returns `route`; any exception inside a node routes to `failed` with `status=FAILED` and `error`. `finalize` and `failed` dispose the index.

- [ ] **Step 1: Smoke test** — `tests/integration/test_graph_smoke.py`:
```python
from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps, run_invoice
from ledger_agent.state import Status
from ledger_agent.testing.invoices import default_spec, render_invoice

def test_clean_invoice_reconciles_without_revisions(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer()))
    assert res.status == Status.RECONCILED and res.iterations == 0 and res.corrections == []
    assert res.invoice_id == "INV-001" and res.ledger.total > 0
```
- [ ] **Step 2:** FAIL. **Step 3:** `graph.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from ledger_agent.agents.audit import EvidenceProposer, retrieve_and_propose, verify_candidates
from ledger_agent.agents.guards import decide_after_validate, signatures
from ledger_agent.agents.reconciliation import PatchRejected, apply_patches, propose_patches
from ledger_agent.config import Config
from ledger_agent.extraction.canonical import build_document
from ledger_agent.extraction.ledger import build_ledger, resolve_column_overrides
from ledger_agent.ingestion.pdf import ingest_pdf
from ledger_agent.ingestion.tables import PyMuPDFTableExtractor
from ledger_agent.models import AuditRecord, Document, Evidence, Ledger
from ledger_agent.protocols import Embedder, LLMClient, OcrBackend, TableExtractor
from ledger_agent.retrieval.hybrid import build_index
from ledger_agent.state import LedgerState, Status
from ledger_agent.validation.arithmetic import validate


@dataclass
class Deps:
    embedder: Embedder
    proposer: EvidenceProposer
    config: Config = field(default_factory=Config)
    llm: LLMClient | None = None
    ocr: OcrBackend | None = None
    table_extractor: TableExtractor = field(default_factory=PyMuPDFTableExtractor)
    ledger_builder: Callable[[Document], Ledger] = build_ledger
    validator: Callable = validate


class ReconciliationResult(BaseModel):
    invoice_id: str
    status: Status
    iterations: int
    ledger: Ledger | None
    original_ledger: Ledger | None
    corrections: list[AuditRecord]
    evidence: list[Evidence]
    error: str | None = None


def _guarded(name: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(state):
            try:
                return fn(state)
            except Exception as exc:  # any node failure ends the run cleanly
                return {"status": Status.FAILED, "error": f"{name}: {exc}", "route": "failed"}
        return wrapper
    return deco


def build_graph(deps: Deps):
    cfg = deps.config

    @_guarded("ingest")
    def ingest(state):
        pages = ingest_pdf(state["pdf_path"], min_chars=cfg.ocr_min_chars, ocr=deps.ocr)
        missing = [p.page_number for p in pages if p.needs_ocr]
        if missing:
            return {"status": Status.FAILED, "route": "failed",
                    "error": f"ingest: pages {missing} need OCR but no OCR backend is configured"}
        return {"pages": pages, "status": Status.INGESTED, "route": "extract"}

    @_guarded("extract")
    def extract(state):
        doc_id = state.get("invoice_id") or Path(state["pdf_path"]).stem
        tables = deps.table_extractor.extract(state["pdf_path"])
        doc = build_document(doc_id, state["pages"], tables)
        doc.column_overrides = resolve_column_overrides(doc, deps.llm)
        return {"invoice_id": doc_id, "document": doc, "status": Status.EXTRACTED, "route": "build_index"}

    @_guarded("build_index")
    def build_index_node(state):
        return {"retrieval_index": build_index(state["document"], deps.embedder),
                "status": Status.INDEXED, "route": "build_ledger"}

    @_guarded("build_ledger")
    def build_ledger_node(state):
        ledger = deps.ledger_builder(state["document"])
        return {"ledger": ledger, "original_ledger": ledger, "revision": 0,
                "last_signatures": None, "status": Status.VALIDATING, "route": "validate"}

    @_guarded("validate")
    def validate_node(state):
        ds = deps.validator(state["ledger"], cfg.validation)
        outcome = decide_after_validate(ds, state.get("last_signatures"),
                                        state["revision"], state["max_revisions"])
        update: dict[str, Any] = {"discrepancies": ds, "last_signatures": signatures(ds)}
        if outcome == "finalize":
            update |= {"route": "finalize"}
        elif outcome == "audit":
            update |= {"route": "audit", "status": Status.AUDITING}
        else:
            status = Status.NO_PROGRESS if outcome == "no_progress" else Status.MAX_REVISIONS_EXCEEDED
            update |= {"route": "failed", "status": status}
        return update

    @_guarded("audit")
    def audit(state):
        cands = [retrieve_and_propose(d, state["ledger"], state["retrieval_index"],
                                      deps.proposer, cfg.top_k) for d in state["discrepancies"]]
        return {"audit_candidates": cands, "route": "verify_evidence"}

    @_guarded("verify_evidence")
    def verify_evidence_node(state):
        verified: list[Evidence] = []
        events = list(state.get("retrieval_events", []))
        for cand in state["audit_candidates"]:
            ok, rejected = verify_candidates(cand, state["invoice_id"], cfg.confidence_threshold)
            verified += ok
            events.append({
                "revision": state["revision"], "field": cand.discrepancy.field, "query": cand.query,
                "retrieved": [(s.chunk.chunk_id, round(s.score, 6)) for s in cand.retrieved],
                "rejected": [(e.field, why) for e, why in rejected],
            })
        update = {"audit_evidence": verified, "retrieval_events": events}
        if not verified:
            return update | {"status": Status.INSUFFICIENT_EVIDENCE, "route": "failed"}
        return update | {"route": "reconcile"}

    @_guarded("reconcile")
    def reconcile(state):
        patches = propose_patches(state["ledger"], state["audit_evidence"])
        if not patches:
            return {"status": Status.UNRESOLVED, "route": "failed",
                    "error": "evidence agrees with the extracted values; nothing to correct"}
        try:
            ledger, records = apply_patches(state["ledger"], patches, state["revision"] + 1,
                                            cfg.confidence_threshold)
        except PatchRejected as exc:
            return {"status": Status.UNRESOLVED, "route": "failed", "error": f"patch rejected: {exc}"}
        return {"ledger": ledger, "revision": state["revision"] + 1, "proposed_corrections": patches,
                "audit_trail": list(state.get("audit_trail", [])) + records,
                "status": Status.RECONCILING, "route": "validate"}

    def _dispose(state):
        idx = state.get("retrieval_index")
        if idx is not None:
            idx.dispose()
        return {"retrieval_index": None}

    def finalize(state):
        return _dispose(state) | {"status": Status.RECONCILED}

    def failed(state):
        return _dispose(state)

    g = StateGraph(LedgerState)
    for name, fn in [("ingest", ingest), ("extract", extract), ("build_index", build_index_node),
                     ("build_ledger", build_ledger_node), ("validate", validate_node),
                     ("audit", audit), ("verify_evidence", verify_evidence_node),
                     ("reconcile", reconcile), ("finalize", finalize), ("failed", failed)]:
        g.add_node(name, fn)
    g.add_edge(START, "ingest")

    def route(src: str, targets: list[str]):
        g.add_conditional_edges(src, lambda s: s["route"], {t: t for t in targets})

    route("ingest", ["extract", "failed"])
    route("extract", ["build_index", "failed"])
    route("build_index", ["build_ledger", "failed"])
    route("build_ledger", ["validate", "failed"])
    route("validate", ["audit", "finalize", "failed"])
    route("audit", ["verify_evidence", "failed"])
    route("verify_evidence", ["reconcile", "failed"])
    route("reconcile", ["validate", "failed"])
    g.add_edge("finalize", END)
    g.add_edge("failed", END)
    return g.compile()


def run_invoice(pdf_path: str, deps: Deps, invoice_id: str | None = None) -> ReconciliationResult:
    initial: LedgerState = {"pdf_path": str(pdf_path), "max_revisions": deps.config.max_revisions,
                            "audit_trail": [], "audit_evidence": [], "retrieval_events": [],
                            "revision": 0}
    if invoice_id:
        initial["invoice_id"] = invoice_id
    final = build_graph(deps).invoke(initial, {"recursion_limit": 100})
    return ReconciliationResult(
        invoice_id=final.get("invoice_id", Path(pdf_path).stem), status=final["status"],
        iterations=final.get("revision", 0), ledger=final.get("ledger"),
        original_ledger=final.get("original_ledger"), corrections=final.get("audit_trail", []),
        evidence=final.get("audit_evidence", []), error=final.get("error"))
```
Notes: the audit-trail event list `retrieval_events` is part of the final state; expose it from `run_invoice` in cycle 2 (persistence). If LangGraph rejects `route` or `retrieval_index` keys, confirm they are declared in `LedgerState` (they are).
- [ ] **Step 4:** `python -m pytest tests/integration/test_graph_smoke.py -v` → PASS.
- [ ] **Step 5: Checkpoint** — tick Task 10.

---

### Task 11: End-to-end scenarios and terminal states

**Files:**
- Create: `src/ledger_agent/testing/corrupt.py`
- Test: `tests/integration/test_graph.py`

**Interfaces:**
- Produces: `corrupting_builder(path: str, value: Decimal) -> Callable[[Document], Ledger]` (builds the real ledger then overwrites one field — simulates an extraction/OCR error); `scripted_validator(script: list[list[Discrepancy]])` returns a validator that yields successive lists (last list repeats).

- [ ] **Step 1: Write the tests** — `tests/integration/test_graph.py`:
```python
from decimal import Decimal as D
import pymupdf
from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.config import Config
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps, run_invoice
from ledger_agent.models import Discrepancy
from ledger_agent.state import Status
from ledger_agent.testing.corrupt import corrupting_builder, scripted_validator
from ledger_agent.testing.invoices import InvoiceSpec, ItemSpec, default_spec, render_invoice

def deps(**kw):
    return Deps(embedder=HashingEmbedder(), proposer=kw.pop("proposer", ChunkValueProposer()), **kw)

def test_line_amount_extraction_error_is_corrected_with_provenance(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps(ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00"))))
    assert res.status == Status.RECONCILED and res.iterations == 1
    [rec] = res.corrections
    assert (rec.revision, rec.field, rec.old_value, rec.new_value) == (1, "items[line_01].amount", D("1040.00"), D("1014.00"))
    assert (rec.source_page, rec.source_table, rec.source_row) == (1, "table_01", 1)
    assert rec.confidence >= 0.9
    assert res.ledger.items[0].amount == D("1014.00")
    assert res.original_ledger.items[0].amount == D("1040.00")      # original preserved

def test_wrong_total_extraction_error_is_corrected(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps(ledger_builder=corrupting_builder("total", D("1200.00"))))
    assert res.status == Status.RECONCILED and res.ledger.total == D("1148.40")

def test_duplicate_lines_patch_the_right_row(tmp_path):                # Review Focus 2
    spec = InvoiceSpec("INV-DUP", [ItemSpec("Gasket", D("3"), D("10.00"))] * 3)
    pdf = render_invoice(spec, tmp_path / "INV-DUP.pdf")
    res = run_invoice(str(pdf), deps(ledger_builder=corrupting_builder("items[line_02].amount", D("99.00"))))
    assert res.status == Status.RECONCILED
    assert [(r.field, r.source_row) for r in res.corrections] == [("items[line_02].amount", 2)]

def test_invoice_that_is_itself_wrong_is_unresolved_not_guessed(tmp_path):  # Review Focus 5
    spec = default_spec()
    spec.items[0].printed_amount = D("1040.00")
    pdf = render_invoice(spec, tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps())
    assert res.status == Status.UNRESOLVED and res.iterations == 0 and res.corrections == []

class LowConfidence(ChunkValueProposer):
    def propose(self, discrepancy, chunks):
        return [e.model_copy(update={"confidence": 0.5}) for e in super().propose(discrepancy, chunks)]

def test_weak_evidence_is_insufficient(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps(proposer=LowConfidence(),
                                     ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00"))))
    assert res.status == Status.INSUFFICIENT_EVIDENCE and res.iterations == 0

def disc(field, exp, obs, related):
    return Discrepancy(field=field, expected=D(exp), observed=D(obs),
                       difference=D(obs) - D(exp), rule="line_amount", related_fields=related)

L1 = disc("items[line_01].amount", "1014.00", "1040.00",
          ["items[line_01].amount", "items[line_01].quantity", "items[line_01].unit_price"])
L2 = disc("items[line_02].amount", "30.00", "99.00",
          ["items[line_02].amount", "items[line_02].quantity", "items[line_02].unit_price"])

def test_no_progress_terminates(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps(ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00")),
                                     validator=scripted_validator([[L1]])))  # same discrepancy forever
    assert res.status == Status.NO_PROGRESS and res.iterations == 1

def test_max_revisions_terminates(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    builder = corrupting_builder("items[line_01].amount", D("1040.00"), also=("items[line_02].amount", D("99.00")))
    res = run_invoice(str(pdf), deps(config=Config(max_revisions=1), ledger_builder=builder,
                                     validator=scripted_validator([[L1], [L2]])))
    assert res.status == Status.MAX_REVISIONS_EXCEEDED and res.iterations == 1

def test_zero_revisions_allowed_blocks_correction(tmp_path):
    pdf = render_invoice(default_spec(), tmp_path / "INV-001.pdf")
    res = run_invoice(str(pdf), deps(config=Config(max_revisions=0),
                                     ledger_builder=corrupting_builder("items[line_01].amount", D("1040.00"))))
    assert res.status == Status.MAX_REVISIONS_EXCEEDED and res.corrections == []

def test_scanned_pdf_without_ocr_fails_cleanly(tmp_path):             # Review Focus 3
    p = tmp_path / "scan.pdf"
    d = pymupdf.open(); d.new_page(); d.save(p); d.close()
    res = run_invoice(str(p), deps())
    assert res.status == Status.FAILED and "OCR" in res.error and res.ledger is None

def test_pdf_without_line_item_table_fails_cleanly(tmp_path):          # Review Focus 4
    p = tmp_path / "notable.pdf"
    d = pymupdf.open(); page = d.new_page()
    page.insert_text((72, 72), "Invoice #X  Total: $5.00  this page has no tables at all, just prose")
    d.save(p); d.close()
    res = run_invoice(str(p), deps())
    assert res.status == Status.FAILED and "line-item" in res.error
```
- [ ] **Step 2:** FAIL (`ledger_agent.testing.corrupt` missing).
- [ ] **Step 3: Implement** `testing/corrupt.py`:
```python
from decimal import Decimal
from typing import Callable

from ledger_agent.extraction.ledger import build_ledger
from ledger_agent.models import Discrepancy, Document, Ledger
from ledger_agent.paths import set_field


def corrupting_builder(path: str, value: Decimal, also: tuple[str, Decimal] | None = None
                       ) -> Callable[[Document], Ledger]:
    def build(doc: Document) -> Ledger:
        led = set_field(build_ledger(doc), path, value)
        return set_field(led, also[0], also[1]) if also else led
    return build


def scripted_validator(script: list[list[Discrepancy]]):
    calls = {"n": 0}

    def validator(ledger, rules):
        out = script[min(calls["n"], len(script) - 1)]
        calls["n"] += 1
        return out
    return validator
```
- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -v`
Expected: all PASS. If `test_max_revisions_terminates` ends `UNRESOLVED`, check that pass 1 patched `line_01` and pass 2's discrepancy `L2` has retrievable evidence differing from the corrupted `99.00` (it must, since line_02's printed amount is 30.00).
- [ ] **Step 5: Checkpoint** — tick Task 11; end of Wave 2.

---

### Task 12: Close-out

**Files:** Modify `memory-bank/progress.md`; create `README.md`.

- [ ] **Step 1: Verification before completion** (superpowers:verification-before-completion): run `python -m pytest -v` fresh and read the output; confirm count and zero failures/skips you can't explain.
- [ ] **Step 2: Definition-of-Done audit** — copy §22 of `memory-bank/implementation-plan.md` into `progress.md`; for each cycle-1 item write the test that proves it (e.g. "Infinite loops are impossible → `test_no_progress_terminates`, `test_max_revisions_terminates`"); mark persistence/observability/baseline items as cycle 2.
- [ ] **Step 3: Code review** — invoke superpowers:requesting-code-review over `src/` and `tests/`; fix Critical/Important findings and re-run the suite.
- [ ] **Step 4: README** — quick start (`pip install -e ".[dev]"`, `pytest`, a 10-line `run_invoice` example using `HashingEmbedder` + `ChunkValueProposer`), architecture diagram from `memory-bank/architecture.md` §1, and the cycle-2 list.
- [ ] **Step 5: Final progress update** — set every cycle-1 box, record decisions/known limits (tax model: each rate applies to `subtotal − discount`; OCR/Docling are interfaces only; no real-LLM adapter yet), and note that claude-mem captures session observations automatically (its `observation_add` tool needs server mode).

---

## Self-Review (done)

- **Spec coverage:** contracts T1; extraction/ingestion/provenance T4+T6; validation T3 (all §8 cases incl. multi-tax, rounding, custom formula); retrieval + isolation + dispose T5; audit/evidence verification T8; reconcile safety checks + revisions T9; guards T7; graph and all five terminal states plus FAILED T10–T11; fixtures T2; scanned-page hook (`needs_ocr`, `OcrBackend`) T4; LLM column-mapping fallback T6; LLM proposer T8. Persistence/observability/eval/API are explicitly cycle 2.
- **Placeholder scan:** no TBD/TODO/"similar to Task N" steps; every code step contains the code.
- **Type consistency:** `item_id` (`line_NN`/`tax_NN`), `related_fields` paths, `Chunk.values` keys, `retrieval_index` state key, `InvoiceIndex.search(invoice_id, query, k, mode, chunk_types)`, `decide_after_validate(...)->str`, `apply_patches(ledger, patches, revision, threshold)` are used identically across tasks.
