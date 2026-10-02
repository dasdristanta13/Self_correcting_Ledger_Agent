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
