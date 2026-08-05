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
    prompt_version: str,
) -> AsyncIterator[dict]:
    """Stream a grounded answer as a sequence of events:
    {"type": "metadata", "prompt_version": str} first (so the caller knows
    which prompt answered before a single token arrives — see
    docs/PLANNING.md Sprint 7 closing note for why this goes first rather
    than at the end), then {"type": "token", "content": str} for each
    generated token, then exactly one {"type": "grounding", "grounded":
    bool, "citations_found": [...], "ungrounded_citations": [...]} once
    generation completes.

    The grounding check is post-hoc by design — it can only run after the
    full answer (with its citations) exists, by which point the tokens have
    already been streamed. See docs/PLANNING.md Sprint 6 closing note for
    why a failed check warns instead of blocking.
    """
    yield {"type": "metadata", "prompt_version": prompt_version}

    messages = build_messages(query, chunks, version=prompt_version)
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
