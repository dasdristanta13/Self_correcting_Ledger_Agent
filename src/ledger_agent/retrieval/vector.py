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
