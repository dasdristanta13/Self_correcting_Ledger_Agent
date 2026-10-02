from decimal import Decimal as D

import chromadb
import pytest

from ledger_agent.fakes import HashingEmbedder
from ledger_agent.retrieval.chroma_vector import (
    ChromaVectorIndex, chroma_vector_factory, list_index_collections, sweep_orphan_indexes)
from ledger_agent.retrieval.hybrid import InvoiceScopeError, build_index
from ledger_agent.testing.ledgers import make_document

EMB = HashingEmbedder()
TEN = tuple((f"Part {i:02d}", D("2"), D("5.00")) for i in range(1, 11))


@pytest.fixture()
def client():
    c = chromadb.EphemeralClient()
    sweep_orphan_indexes(c)
    yield c
    sweep_orphan_indexes(c)


def top_ids(idx, query, mode="hybrid", k=3):
    return [r.chunk.chunk_id for r in idx.search("INV-001", query, k=k, mode=mode,
                                                 chunk_types=["line_item"])]


@pytest.mark.parametrize("query", ["line_07 Part 07 quantity unit price amount",
                                   "line_02 Part 02", "Part 10 amount"])
@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_rankings_match_the_numpy_backend(client, query, mode):
    doc = make_document(items=TEN)
    numpy_idx = build_index(doc, EMB)
    chroma_idx = build_index(doc, EMB, vector_factory=chroma_vector_factory(client))
    assert top_ids(chroma_idx, query, mode) == top_ids(numpy_idx, query, mode)
    chroma_idx.dispose()


def test_scores_are_aligned_to_chunk_order(client):
    doc = make_document(items=TEN)
    from ledger_agent.retrieval.chunks import build_chunks
    from ledger_agent.retrieval.vector import VectorIndex

    chunks = build_chunks(doc)
    ref = VectorIndex(chunks, EMB).scores("line_03 Part 03 amount")
    got = ChromaVectorIndex(client, "INV-001", chunks, EMB).scores("line_03 Part 03 amount")
    assert len(got) == len(ref)
    assert all(abs(a - b) < 1e-4 for a, b in zip(got, ref))


def test_dispose_deletes_the_collection_and_is_idempotent(client):
    idx = build_index(make_document(), EMB, vector_factory=chroma_vector_factory(client))
    assert len(list_index_collections(client)) == 1
    idx.dispose()
    idx.dispose()
    assert list_index_collections(client) == []


def test_two_invoices_use_separate_collections_and_never_leak(client):
    factory = chroma_vector_factory(client)
    a = build_index(make_document(invoice_id="INV-A"), EMB, vector_factory=factory)
    b = build_index(make_document(invoice_id="INV-B"), EMB, vector_factory=factory)
    assert len(list_index_collections(client)) == 2
    with pytest.raises(InvoiceScopeError):
        a.search("INV-B", "total")
    assert all(r.chunk.invoice_id == "INV-A" for r in a.search("INV-A", "total", k=10))
    a.dispose()
    assert len(list_index_collections(client)) == 1
    assert b.search("INV-B", "total", k=3)
    b.dispose()


def test_sweep_removes_orphans_but_not_other_collections(client):
    client.get_or_create_collection("jobs", embedding_function=None)
    ChromaVectorIndex(client, "INV-X", [], EMB)          # empty -> creates nothing
    orphan = build_index(make_document(), EMB, vector_factory=chroma_vector_factory(client))
    assert sweep_orphan_indexes(client) == 1
    assert list_index_collections(client) == []
    names = [getattr(c, "name", c) for c in client.list_collections()]
    assert "jobs" in names
    del orphan


def test_empty_corpus_and_zero_query_vector(client):
    assert ChromaVectorIndex(client, "INV-X", [], EMB).scores("anything") == []
    idx = build_index(make_document(), EMB, vector_factory=chroma_vector_factory(client))
    assert idx.search("INV-001", "", k=2, mode="vector") is not None   # empty query -> zero vector
    idx.dispose()
