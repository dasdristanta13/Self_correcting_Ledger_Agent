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
    def __init__(self, invoice_id: str, chunks: list[Chunk], embedder: Embedder,
                 vector_factory=None, default_mode: str = "hybrid"):
        stray = [c.chunk_id for c in chunks if c.invoice_id != invoice_id]
        if stray:
            raise InvoiceScopeError(f"chunks from another invoice: {stray}")
        self.invoice_id = invoice_id
        self.default_mode = default_mode
        self._chunks: list[Chunk] | None = chunks
        self._bm25: BM25Index | None = BM25Index(chunks)
        factory = vector_factory or (lambda inv, ch, emb: VectorIndex(ch, emb))
        self._vec = factory(invoice_id, chunks, embedder)

    def search(self, invoice_id: str, query: str, k: int = 5, mode: str | None = None,
               chunk_types: list[str] | None = None) -> list[ScoredChunk]:
        mode = mode or self.default_mode
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
        vec, self._chunks, self._bm25, self._vec = self._vec, None, None, None
        if vec is not None:
            try:
                vec.dispose()
            except Exception:  # backend cleanup failure must not hide the run's result
                pass


def build_index(doc: Document, embedder: Embedder, vector_factory=None,
                mode: str = "hybrid") -> InvoiceIndex:
    return InvoiceIndex(doc.document_id, build_chunks(doc), embedder,
                        vector_factory=vector_factory, default_mode=mode)
