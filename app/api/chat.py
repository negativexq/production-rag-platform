import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient

from app.llm.generate import stream_answer
from app.llm.ollama_client import OllamaClient
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings

router = APIRouter()


class ChatRequest(BaseModel):
    question: str


# Model loading is expensive (~9s for the cross-encoder, similar for the
# sparse encoder) — instantiated once per process, not per request.
_sparse_encoder: SparseEncoder | None = None
_reranker: CrossEncoderReranker | None = None
_qdrant_client: QdrantClient | None = None


def _get_sparse_encoder() -> SparseEncoder:
    global _sparse_encoder
    if _sparse_encoder is None:
        _sparse_encoder = SparseEncoder()
    return _sparse_encoder


def _get_reranker() -> CrossEncoderReranker:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker()
    return _reranker


def _get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=settings.qdrant_url)
    return _qdrant_client


async def _sse_event_stream(question: str):
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    try:
        chunks = await search(
            question,
            ollama=ollama,
            sparse_encoder=_get_sparse_encoder(),
            qdrant_client=_get_qdrant_client(),
            collection_name=settings.qdrant_collection_name,
            embed_model=settings.ollama_embed_model,
            reranker=_get_reranker(),
        )
        async for event in stream_answer(question, chunks, ollama, model=settings.ollama_model):
            if event["type"] == "token":
                yield f"data: {json.dumps({'token': event['content']})}\n\n"
            else:
                grounding_payload = {k: v for k, v in event.items() if k != "type"}
                yield f"event: grounding\ndata: {json.dumps(grounding_payload)}\n\n"
    finally:
        await ollama.aclose()


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_sse_event_stream(request.question), media_type="text/event-stream")
