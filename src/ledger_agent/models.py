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
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
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
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


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
