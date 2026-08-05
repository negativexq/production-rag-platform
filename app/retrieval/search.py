from typing import Protocol

from qdrant_client import QdrantClient

from app.retrieval.hybrid_search import DEFAULT_TOP_K, SearchResult, hybrid_search
from app.retrieval.sparse import SparseVector

# Query-side counterpart to app/ingestion/ingest.py's SEARCH_DOCUMENT_PREFIX —
# nomic-embed-text requires this prefix on the *query* text for retrieval to
# work well (see docs/PLANNING.md Sprint 2 closing note).
SEARCH_QUERY_PREFIX = "search_query: "


class OllamaEmbedProtocol(Protocol):
    async def embed(self, text: str, model: str, prefix: str = "") -> list[float]: ...


class SparseEncoderProtocol(Protocol):
    def embed_query(self, text: str) -> SparseVector: ...


async def search(
    query: str,
    ollama: OllamaEmbedProtocol,
    sparse_encoder: SparseEncoderProtocol,
    qdrant_client: QdrantClient,
    collection_name: str,
    embed_model: str,
    top_k: int = DEFAULT_TOP_K,
) -> list[SearchResult]:
    dense_vector = await ollama.embed(query, model=embed_model, prefix=SEARCH_QUERY_PREFIX)
    sparse_vector = sparse_encoder.embed_query(query)
    return hybrid_search(qdrant_client, collection_name, dense_vector, sparse_vector, top_k=top_k)
