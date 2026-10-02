from __future__ import annotations

import uuid

import numpy as np

from ledger_agent.models import Chunk
from ledger_agent.protocols import Embedder

_PREFIX = "idx-"


def _names(client) -> list[str]:
    return [getattr(c, "name", c) for c in client.list_collections()]


def list_index_collections(client) -> list[str]:
    return [n for n in _names(client) if n.startswith(_PREFIX)]


def sweep_orphan_indexes(client) -> int:
    orphans = list_index_collections(client)
    for name in orphans:
        client.delete_collection(name)
    return len(orphans)


def _normalise(vectors: list[list[float]]) -> np.ndarray:
    m = np.array(vectors, dtype=float)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


class ChromaVectorIndex:
    """Per-invoice vector index in its own Chroma collection (inner product on unit vectors)."""

    def __init__(self, client, invoice_id: str, chunks: list[Chunk], embedder: Embedder):
        self._client = client
        self._embedder = embedder
        self._n = len(chunks)
        self._name: str | None = None
        self._col = None
        if not chunks:
            return
        self._name = f"{_PREFIX}{uuid.uuid4().hex[:16]}"
        self._col = self._create_collection(client, self._name, invoice_id)
        vectors = _normalise(embedder.embed([c.text for c in chunks]))
        self._col.add(ids=[str(i) for i in range(len(chunks))], embeddings=vectors.tolist(),
                      metadatas=[{"invoice_id": invoice_id, "chunk_id": c.chunk_id} for c in chunks])

    @staticmethod
    def _create_collection(client, name, invoice_id):
        try:
            return client.create_collection(name, embedding_function=None,
                                            configuration={"hnsw": {"space": "ip"}},
                                            metadata={"invoice_id": invoice_id})
        except TypeError:
            return client.create_collection(name, embedding_function=None,
                                            metadata={"hnsw:space": "ip", "invoice_id": invoice_id})

    def scores(self, query: str) -> list[float]:
        if self._col is None:
            return []
        q = _normalise([self._embedder.embed([query])[0]])[0]
        res = self._col.query(query_embeddings=[q.tolist()], n_results=self._n, include=["distances"])
        out = [0.0] * self._n
        for id_, dist in zip(res["ids"][0], res["distances"][0]):
            out[int(id_)] = 1.0 - float(dist)      # ip distance = 1 - dot(unit, unit)
        return out

    def dispose(self) -> None:
        if self._name is None:
            return
        name, self._name, self._col = self._name, None, None
        try:
            self._client.delete_collection(name)
        except Exception:
            pass                                    # already gone


def chroma_vector_factory(client):
    def factory(invoice_id: str, chunks: list[Chunk], embedder: Embedder) -> ChromaVectorIndex:
        return ChromaVectorIndex(client, invoice_id, chunks, embedder)
    return factory
