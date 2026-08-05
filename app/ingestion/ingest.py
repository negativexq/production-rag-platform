from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.ingestion.chunker import DEFAULT_CHUNK_SIZE_TOKENS, DEFAULT_OVERLAP_TOKENS, chunk_document
from app.ingestion.qdrant_store import QdrantStore
from app.retrieval.sparse import SparseVector

# nomic-embed-text requires a task instruction prefix on the embedded text;
# "search_document: " is the indexing-side prefix (query side uses
# "search_query: ", applied at retrieval time in app/retrieval).
SEARCH_DOCUMENT_PREFIX = "search_document: "

EmbedFn = Callable[[str], Awaitable[list[float]]]


class SparseEncoderProtocol(Protocol):
    def embed_document(self, text: str) -> SparseVector: ...


@dataclass
class IngestStats:
    files_processed: int
    chunks_upserted: int


async def ingest_path(
    path: str,
    store: QdrantStore,
    embed_fn: EmbedFn,
    sparse_encoder: SparseEncoderProtocol,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    batch_size: int = 64,
) -> IngestStats:
    store.ensure_collection()

    files_processed = 0
    chunks_upserted = 0

    for pdf_path in sorted(Path(path).glob("*.pdf")):
        chunks = chunk_document(str(pdf_path), chunk_size_tokens, overlap_tokens)

        for batch_start in range(0, len(chunks), batch_size):
            batch = chunks[batch_start : batch_start + batch_size]
            dense_vectors = [await embed_fn(chunk.text) for chunk in batch]
            sparse_vectors = [sparse_encoder.embed_document(chunk.text) for chunk in batch]
            store.upsert_chunks(batch, dense_vectors, sparse_vectors, source_filename=pdf_path.name)
            chunks_upserted += len(batch)

        files_processed += 1

    return IngestStats(files_processed=files_processed, chunks_upserted=chunks_upserted)
