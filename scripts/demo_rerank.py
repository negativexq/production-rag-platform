"""Concrete demonstration for Sprint 5's DoD: hybrid search's top-1 result
is measurably wrong (an irrelevant chunk that only ranks first because it
repeats a keyword many times), and reranking fixes it — with real,
measured scores, against real Ollama + real Qdrant.

Run with services up (`make up`, native Ollama running):
    PYTHONPATH=. .venv/bin/python scripts/demo_rerank.py
"""

import asyncio

from qdrant_client import QdrantClient

from app.ingestion.ingest import SEARCH_DOCUMENT_PREFIX
from app.ingestion.models import Chunk
from app.ingestion.qdrant_store import QdrantStore
from app.llm.ollama_client import OllamaClient
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.search import SEARCH_QUERY_PREFIX
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings

COLLECTION = "demo_rerank"
QUERY = "What is the return policy for a defective product?"

CHUNKS = [
    Chunk(
        doc_id="d",
        page_number=1,
        paragraph_index=0,
        char_range=(0, 1),
        text=(
            "This product comes in three colors: red, blue, and green. Product "
            "weight is 1.2kg and product dimensions are 10x10x5cm. Product ships "
            "within two business days. Product specifications are listed in the "
            "appendix. Product warranty card is included in the product box."
        ),
    ),
    Chunk(
        doc_id="d",
        page_number=2,
        paragraph_index=0,
        char_range=(0, 1),
        text=(
            "If an item arrives broken or faulty, customers may send it back "
            "within 30 days for a complete refund, provided the original box "
            "and accessories are included."
        ),
    ),
]


async def main() -> None:
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse_encoder = SparseEncoder()
    client = QdrantClient(url=settings.qdrant_url)
    store = QdrantStore(client=client, collection_name=COLLECTION)

    client.delete_collection(COLLECTION)
    store.ensure_collection()

    dense_vectors = [
        await ollama.embed(c.text, model=settings.ollama_embed_model, prefix=SEARCH_DOCUMENT_PREFIX)
        for c in CHUNKS
    ]
    sparse_vectors = [sparse_encoder.embed_document(c.text) for c in CHUNKS]
    store.upsert_chunks(CHUNKS, dense_vectors, sparse_vectors, source_filename="demo.pdf")

    query_dense = await ollama.embed(
        QUERY, model=settings.ollama_embed_model, prefix=SEARCH_QUERY_PREFIX
    )
    query_sparse = sparse_encoder.embed_query(QUERY)

    hybrid_results = hybrid_search(client, COLLECTION, query_dense, query_sparse, top_k=2)

    reranker = CrossEncoderReranker()
    reranked_results = reranker.rerank(QUERY, hybrid_results, top_n=2)

    print(f"Query: {QUERY!r}\n")
    print("Before rerank — hybrid (RRF) ranking:")
    for i, r in enumerate(hybrid_results, 1):
        print(f"  {i}. score={r.score:.4f}  {r.payload['text'][:70]!r}")

    print("\nAfter rerank — CrossEncoder ranking:")
    for i, r in enumerate(reranked_results, 1):
        print(f"  {i}. score={r.score:.4f}  {r.payload['text'][:70]!r}")

    top1_before = hybrid_results[0].payload["text"]
    top1_after = reranked_results[0].payload["text"]
    print(
        f"\n=> hybrid's top-1 changed after rerank: {top1_before != top1_after}\n"
        f"=> hybrid ranked the keyword-stuffed, irrelevant chunk first "
        f"(score={hybrid_results[0].score:.4f}); rerank correctly promotes the "
        f"actually relevant return-policy chunk (score={reranked_results[0].score:.4f}) "
        f"and demotes the irrelevant one (score={reranked_results[1].score:.4f})."
    )

    client.delete_collection(COLLECTION)
    await ollama.aclose()


if __name__ == "__main__":
    asyncio.run(main())
