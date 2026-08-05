from collections.abc import AsyncIterator
from typing import Protocol

from app.llm.grounding import check_grounding
from app.llm.prompt import build_messages
from app.retrieval.hybrid_search import SearchResult


class StreamingOllamaProtocol(Protocol):
    def stream_chat(self, messages: list[dict], model: str) -> AsyncIterator[str]: ...


async def stream_answer(
    query: str,
    chunks: list[SearchResult],
    ollama: StreamingOllamaProtocol,
    model: str,
) -> AsyncIterator[dict]:
    """Stream a grounded answer as a sequence of events:
    {"type": "token", "content": str} for each generated token, followed by
    exactly one {"type": "grounding", "grounded": bool, "citations_found":
    [...], "ungrounded_citations": [...]} once generation completes.

    The grounding check is post-hoc by design — it can only run after the
    full answer (with its citations) exists, by which point the tokens have
    already been streamed. See docs/PLANNING.md Sprint 6 closing note for
    why a failed check warns instead of blocking.
    """
    messages = build_messages(query, chunks)
    answer_parts = []

    async for token in ollama.stream_chat(messages, model=model):
        answer_parts.append(token)
        yield {"type": "token", "content": token}

    grounding = check_grounding("".join(answer_parts), chunks)
    yield {
        "type": "grounding",
        "grounded": grounding.grounded,
        "citations_found": grounding.citations_found,
        "ungrounded_citations": grounding.ungrounded_citations,
    }
