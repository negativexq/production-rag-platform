import pytest
from qdrant_client import QdrantClient

from app.ingestion.models import Chunk
from app.ingestion.qdrant_store import QdrantStore
from app.retrieval.search import SEARCH_QUERY_PREFIX, search
from app.retrieval.sparse import SparseVector

COLLECTION = "test_search"


class _FakeOllama:
    def __init__(self):
        self.calls = []

    async def embed(self, text: str, model: str, prefix: str = "") -> list[float]:
        self.calls.append({"text": text, "model": model, "prefix": prefix})
        vector = [0.0] * 768
        vector[0] = 1.0
        return vector


class _FakeSparseEncoder:
    def embed_query(self, text: str) -> SparseVector:
        return SparseVector(indices=[42], values=[1.0])

    def embed_document(self, text: str) -> SparseVector:
        return SparseVector(indices=[42], values=[2.0])


def _chunk(text: str) -> Chunk:
    return Chunk(
        doc_id="doc", page_number=1, paragraph_index=0, char_range=(0, len(text)), text=text
    )


@pytest.mark.asyncio
async def test_search_applies_search_query_prefix_to_dense_embedding():
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION)
    store.ensure_collection()
    # qdrant-client's local (":memory:") mode raises a KeyError when
    # querying a sparse vector with an IDF modifier against a completely
    # empty collection (confirmed this doesn't happen on a real Qdrant
    # server — see docs/PLANNING.md Sprint 3 closing note). Upsert one
    # point first so the local IDF store is initialized.
    store.upsert_chunks(
        [_chunk("placeholder")],
        [[0.0] * 768],
        [SparseVector(indices=[1], values=[1.0])],
        source_filename="doc.pdf",
    )
    ollama = _FakeOllama()

    await search(
        "what is hybrid search",
        ollama=ollama,
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION,
        embed_model="nomic-embed-text",
    )

    assert ollama.calls[0]["prefix"] == SEARCH_QUERY_PREFIX
    assert ollama.calls[0]["text"] == "what is hybrid search"


@pytest.mark.asyncio
async def test_search_returns_hybrid_results():
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION + "2")
    store.ensure_collection()
    dense_vector = [0.0] * 768
    dense_vector[0] = 1.0
    store.upsert_chunks(
        [_chunk("hello world")],
        [dense_vector],
        [SparseVector(indices=[42], values=[2.0])],
        source_filename="doc.pdf",
    )

    results = await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION + "2",
        embed_model="nomic-embed-text",
    )

    assert len(results) == 1
    assert results[0].payload["text"] == "hello world"
