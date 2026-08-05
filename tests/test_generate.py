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


async def _collect(query, chunks, ollama, model="qwen", prompt_version="v1"):
    return [
        event
        async for event in stream_answer(
            query, chunks, ollama, model=model, prompt_version=prompt_version
        )
    ]


@pytest.mark.asyncio
async def test_stream_answer_first_event_is_metadata_with_prompt_version():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["ok"])

    events = await _collect("How long?", chunks, ollama, prompt_version="v2")

    assert events[0] == {"type": "metadata", "prompt_version": "v2"}


@pytest.mark.asyncio
async def test_stream_answer_yields_token_events_in_order():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds ", "take ", "30 days ", "[s.2/0]."])

    events = await _collect("How long?", chunks, ollama)

    token_events = [e for e in events if e["type"] == "token"]
    assert [e["content"] for e in token_events] == ["Refunds ", "take ", "30 days ", "[s.2/0]."]


@pytest.mark.asyncio
async def test_stream_answer_emits_grounding_event_last():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.2/0]."])

    events = await _collect("How long?", chunks, ollama)

    assert events[-1]["type"] == "grounding"
    assert events[-1]["grounded"] is True
    assert events[-1]["citations_found"] == [(2, 0)]


@pytest.mark.asyncio
async def test_stream_answer_grounding_event_flags_fabricated_citation():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.99/0]."])  # 99 was never in context

    events = await _collect("How long?", chunks, ollama)

    grounding_event = events[-1]
    assert grounding_event["grounded"] is False
    assert grounding_event["ungrounded_citations"] == [(99, 0)]


@pytest.mark.asyncio
async def test_stream_answer_passes_built_messages_to_ollama():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["ok"])

    await _collect("How long?", chunks, ollama, model="qwen")

    roles = [m["role"] for m in ollama.received_messages]
    assert roles == ["system", "user"]
    assert "How long?" in ollama.received_messages[1]["content"]
    assert ollama.received_model == "qwen"


@pytest.mark.asyncio
async def test_stream_answer_uses_requested_prompt_version_content():
    from app.llm.prompt import load_system_prompt

    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["ok"])

    await _collect("How long?", chunks, ollama, prompt_version="v2")

    assert ollama.received_messages[0]["content"] == load_system_prompt("v2")
