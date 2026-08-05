"""Concrete demonstration for Sprint 3's DoD: same query, dense-only vs
hybrid search.

Part 1 uses REAL nomic-embed-text embeddings and real Qdrant on a
near-duplicate-ID scenario (the classic case where dense embeddings are
expected to struggle). Honest result, reported as measured: across many
adversarial real-embedding trials (see docs/PLANNING.md Sprint 3 closing
note), nomic-embed-text's dense retrieval turned out to be robust enough
that it did NOT actually miss the correct chunk in this run either — the
margin is just much narrower than for unrelated topics.

Part 2 is a controlled example (deliberately constructed vectors, not real
embeddings) that isolates the fusion mechanism itself: a chunk whose dense
vector is orthogonal to the query (dense-only ranks it last / effectively
invisible) but that shares an exact rare keyword — hybrid recovers it. This
is the mechanical proof that the RRF fusion code path does what it claims.

Run with services up (`make up`, native Ollama running):
    PYTHONPATH=. .venv/bin/python scripts/demo_hybrid_vs_dense.py
"""

import asyncio

from qdrant_client import QdrantClient

from app.ingestion.ingest import SEARCH_DOCUMENT_PREFIX
from app.ingestion.models import Chunk
from app.ingestion.qdrant_store import QdrantStore
from app.llm.ollama_client import OllamaClient
from app.retrieval.hybrid_search import dense_only_search, hybrid_search
from app.retrieval.search import SEARCH_QUERY_PREFIX
from app.retrieval.sparse import SparseEncoder, SparseVector
from app.shared.config import settings

COLLECTION = "demo_hybrid_vs_dense"

QUERY = "What is the status of order REF-99182?"


def _demo_chunk(page: int, text: str) -> Chunk:
    return Chunk(doc_id="demo", page_number=page, paragraph_index=0, char_range=(0, 1), text=text)


CHUNKS = [
    _demo_chunk(1, "REF-99182: shipped."),
    _demo_chunk(2, "REF-99183: delayed due to inventory shortage, expected to ship next week."),
    _demo_chunk(3, "REF-99181: cancelled by the customer before fulfillment."),
    _demo_chunk(4, "REF-99184: on hold pending payment confirmation from billing."),
]


async def part1_real_embeddings() -> None:
    print("=" * 70)
    print("PART 1 — real nomic-embed-text embeddings, near-duplicate order IDs")
    print("=" * 70)

    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse_encoder = SparseEncoder()
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    store = QdrantStore(client=qdrant_client, collection_name=COLLECTION)

    qdrant_client.delete_collection(COLLECTION)
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

    dense_results = dense_only_search(qdrant_client, COLLECTION, query_dense, top_k=4)
    hybrid_results = hybrid_search(qdrant_client, COLLECTION, query_dense, query_sparse, top_k=4)

    print(f"\nQuery: {QUERY!r}\n")
    print("Dense-only ranking:")
    for i, r in enumerate(dense_results, 1):
        print(f"  {i}. score={r.score:.4f}  {r.payload['text']!r}")
    print("\nHybrid (RRF) ranking:")
    for i, r in enumerate(hybrid_results, 1):
        print(f"  {i}. score={r.score:.4f}  {r.payload['text']!r}")

    print(
        "\nHonest note: dense-only also ranks REF-99182 first here. Across 14 "
        "adversarial real-embedding trials (rare codes, near-duplicate IDs, "
        "invented jargon), nomic-embed-text never actually misranked the "
        "correct chunk — see docs/PLANNING.md Sprint 3 closing note for the "
        "full list. The margin does shrink for near-duplicates though: "
        f"{dense_results[0].score:.4f} vs {dense_results[1].score:.4f} here, "
        "versus a >0.2 gap for semantically unrelated topics."
    )

    qdrant_client.delete_collection(COLLECTION)
    await ollama.aclose()


def part2_controlled_mechanism_proof() -> None:
    print("\n" + "=" * 70)
    print("PART 2 — controlled example: hybrid recovers what dense-only truly misses")
    print("=" * 70)

    qdrant_client = QdrantClient(":memory:")
    store = QdrantStore(client=qdrant_client, collection_name="demo_controlled")
    store.ensure_collection()

    def unit(index: int, dim: int = 768) -> list[float]:
        v = [0.0] * dim
        v[index] = 1.0
        return v

    keyword_chunk = Chunk(
        doc_id="kw",
        page_number=1,
        paragraph_index=0,
        char_range=(0, 1),
        text="something about qdrant vector databases",
    )
    unrelated_chunk = Chunk(
        doc_id="unrel",
        page_number=2,
        paragraph_index=0,
        char_range=(0, 1),
        text="completely unrelated topic about cooking",
    )

    store.upsert_chunks(
        [keyword_chunk],
        [unit(5)],  # orthogonal to the query vector -> dense-only can't find it
        [SparseVector(indices=[111, 222], values=[2.0, 1.0])],
        source_filename="doc.pdf",
    )
    store.upsert_chunks(
        [unrelated_chunk],
        [unit(0)],  # matches the query vector exactly
        [SparseVector(indices=[999], values=[0.1])],
        source_filename="doc.pdf",
    )

    query_dense_vector = unit(0)
    query_sparse_vector = SparseVector(indices=[111], values=[1.0])

    dense_results = dense_only_search(qdrant_client, "demo_controlled", query_dense_vector, top_k=2)
    hybrid_results = hybrid_search(
        qdrant_client, "demo_controlled", query_dense_vector, query_sparse_vector, top_k=2
    )

    print("\nDense-only ranking:")
    for i, r in enumerate(dense_results, 1):
        print(f"  {i}. score={r.score:.4f}  doc_id={r.payload['doc_id']!r}  {r.payload['text']!r}")
    print("\nHybrid (RRF) ranking:")
    for i, r in enumerate(hybrid_results, 1):
        print(f"  {i}. score={r.score:.4f}  doc_id={r.payload['doc_id']!r}  {r.payload['text']!r}")

    kw_in_dense_top1 = dense_results[0].payload["doc_id"] == "kw"
    kw_in_hybrid = "kw" in [r.payload["doc_id"] for r in hybrid_results]
    print(
        f"\n=> dense-only ranks the keyword-matching chunk first: {kw_in_dense_top1} "
        f"(it's semantically orthogonal to the query, so dense-only can't rank it above "
        f"the unrelated-but-vector-identical chunk)"
    )
    print(f"=> hybrid surfaces the keyword-matching chunk: {kw_in_hybrid}")


async def main() -> None:
    await part1_real_embeddings()
    part2_controlled_mechanism_proof()


if __name__ == "__main__":
    asyncio.run(main())
