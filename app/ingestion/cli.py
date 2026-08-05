import argparse
import asyncio

from qdrant_client import QdrantClient

from app.ingestion.ingest import SEARCH_DOCUMENT_PREFIX, ingest_path
from app.ingestion.qdrant_store import QdrantStore
from app.llm.ollama_client import OllamaClient
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings
from app.shared.tracing import setup_tracing


async def _run(path: str) -> None:
    setup_tracing()
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    store = QdrantStore(client=qdrant_client, collection_name=settings.qdrant_collection_name)
    sparse_encoder = SparseEncoder()

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text, model=settings.ollama_embed_model, prefix=SEARCH_DOCUMENT_PREFIX
        )

    try:
        stats = await ingest_path(path, store, embed_fn, sparse_encoder)
    finally:
        await ollama.aclose()

    print(f"Processed {stats.files_processed} file(s), upserted {stats.chunks_upserted} chunk(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PDFs into Qdrant")
    parser.add_argument("--path", required=True, help="Folder containing PDF files")
    args = parser.parse_args()

    asyncio.run(_run(args.path))


if __name__ == "__main__":
    main()
