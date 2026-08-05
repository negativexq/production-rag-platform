"""End-to-end trace verification against a REAL Jaeger instance (the
docker-compose service) and real Ollama/Qdrant — this is the DoD's
concrete proof that a single query's full pipeline is traceable as one
waterfall, not a unit-test assumption.

Skipped automatically if Ollama/Qdrant/Jaeger aren't reachable.
"""

import asyncio
import shutil
import socket

import httpx
import pytest
from opentelemetry import trace
from qdrant_client import QdrantClient

from app.ingestion.ingest import ingest_path
from app.ingestion.qdrant_store import QdrantStore
from app.llm.generate import stream_answer
from app.llm.ollama_client import OllamaClient
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings
from app.shared.tracing import get_tracer, setup_tracing

COLLECTION = "test_tracing_e2e"
JAEGER_API = "http://localhost:16686"


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


_services_up = (
    _port_open("localhost", 11434)
    and _port_open("localhost", 6333)
    and _port_open("localhost", 16686)
)


def _fetch_trace(trace_id: str) -> dict | None:
    response = httpx.get(f"{JAEGER_API}/api/traces/{trace_id}")
    response.raise_for_status()
    data = response.json()["data"]
    return data[0] if data else None


@pytest.mark.skipif(
    not _services_up, reason="requires native Ollama, Qdrant, and Jaeger all running"
)
@pytest.mark.asyncio
async def test_full_query_pipeline_is_one_traceable_waterfall(sample_pdf, tmp_path):
    setup_tracing(service_name="test-tracing-e2e")
    tracer = get_tracer(__name__)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "sample.pdf")

    qdrant_client = QdrantClient(url=settings.qdrant_url)
    store = QdrantStore(client=qdrant_client, collection_name=COLLECTION)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse_encoder = SparseEncoder()
    reranker = CrossEncoderReranker()

    async def embed_fn(text: str) -> list[float]:
        from app.ingestion.ingest import SEARCH_DOCUMENT_PREFIX

        return await ollama.embed(
            text, model=settings.ollama_embed_model, prefix=SEARCH_DOCUMENT_PREFIX
        )

    try:
        await ingest_path(str(docs_dir), store, embed_fn, sparse_encoder)

        trace_id_hex = None
        with tracer.start_as_current_span("test_chat_request") as root_span:
            trace_id_hex = format(root_span.get_span_context().trace_id, "032x")

            chunks = await search(
                "PAGE1-PARA0",
                ollama=ollama,
                sparse_encoder=sparse_encoder,
                qdrant_client=qdrant_client,
                collection_name=COLLECTION,
                embed_model=settings.ollama_embed_model,
                reranker=reranker,
                tracer=tracer,
            )
            async for _ in stream_answer(
                "What is mentioned on PAGE1-PARA0?",
                chunks,
                ollama,
                model=settings.ollama_model,
                prompt_version="v1",
                tracer=tracer,
            ):
                pass

        # BatchSpanProcessor batches on a timer (default 5s) — force an
        # immediate export instead of guessing how long to sleep.
        trace.get_tracer_provider().force_flush()
        await asyncio.sleep(1)

        fetched_trace = _fetch_trace(trace_id_hex)
        assert fetched_trace is not None, f"trace {trace_id_hex} not found in Jaeger"

        span_names = {span["operationName"] for span in fetched_trace["spans"]}
        assert {
            "test_chat_request",
            "embed_query",
            "retrieve_hybrid",
            "rerank",
            "generate",
        } <= span_names

        root = next(s for s in fetched_trace["spans"] if s["operationName"] == "test_chat_request")
        for span in fetched_trace["spans"]:
            if span["spanID"] == root["spanID"]:
                continue
            parent_ids = [ref["spanID"] for ref in span["references"]]
            assert root["spanID"] in parent_ids, f"{span['operationName']} isn't a child of root"

        for span in fetched_trace["spans"]:
            for tag in span["tags"]:
                assert "PAGE1-PARA0" not in str(tag["value"]), (
                    f"high-cardinality chunk text leaked into span tag: {tag}"
                )
    finally:
        qdrant_client.delete_collection(COLLECTION)
        await ollama.aclose()
