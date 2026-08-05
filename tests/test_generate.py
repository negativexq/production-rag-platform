import pytest

from app.llm.generate import stream_answer
from app.retrieval.hybrid_search import SearchResult


def _chunk(page: int, paragraph: int, text: str) -> SearchResult:
    return SearchResult(
        score=0.9, payload={"page_number": page, "paragraph_index": paragraph, "text": text}
    )


class _FakeOllama:
    def __init__(self, tokens: list[str]):
        self._tokens = tokens
        self.received_messages = None
        self.received_model = None

    async def stream_chat(self, messages, model):
        self.received_messages = messages
        self.received_model = model
        for token in self._tokens:
            yield token


@pytest.mark.asyncio
async def test_stream_answer_yields_token_events_in_order():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds ", "take ", "30 days ", "[s.2/0]."])

    events = [event async for event in stream_answer("How long?", chunks, ollama, model="qwen")]

    token_events = [e for e in events if e["type"] == "token"]
    assert [e["content"] for e in token_events] == ["Refunds ", "take ", "30 days ", "[s.2/0]."]


@pytest.mark.asyncio
async def test_stream_answer_emits_grounding_event_last():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.2/0]."])

    events = [event async for event in stream_answer("How long?", chunks, ollama, model="qwen")]

    assert events[-1]["type"] == "grounding"
    assert events[-1]["grounded"] is True
    assert events[-1]["citations_found"] == [(2, 0)]


@pytest.mark.asyncio
async def test_stream_answer_grounding_event_flags_fabricated_citation():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.99/0]."])  # 99 was never in context

    events = [event async for event in stream_answer("How long?", chunks, ollama, model="qwen")]

    grounding_event = events[-1]
    assert grounding_event["grounded"] is False
    assert grounding_event["ungrounded_citations"] == [(99, 0)]


@pytest.mark.asyncio
async def test_stream_answer_passes_built_messages_to_ollama():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["ok"])

    async for _ in stream_answer("How long?", chunks, ollama, model="qwen"):
        pass

    roles = [m["role"] for m in ollama.received_messages]
    assert roles == ["system", "user"]
    assert "How long?" in ollama.received_messages[1]["content"]
    assert ollama.received_model == "qwen"
