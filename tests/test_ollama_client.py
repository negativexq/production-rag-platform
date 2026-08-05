import json

import httpx
import pytest

from app.llm.ollama_client import OllamaClient, OllamaUnreachableError


def _mock_client(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url="http://host.docker.internal:11434")


@pytest.mark.asyncio
async def test_list_models_parses_tags_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "qwen2.5:3b-instruct"}, {"name": "nomic-embed-text"}]},
        )

    client = OllamaClient(http_client=_mock_client(handler))
    models = await client.list_models()

    assert models == ["qwen2.5:3b-instruct", "nomic-embed-text"]


@pytest.mark.asyncio
async def test_list_models_raises_when_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = OllamaClient(http_client=_mock_client(handler))

    with pytest.raises(OllamaUnreachableError):
        await client.list_models()


@pytest.mark.asyncio
async def test_embed_sends_prefixed_prompt_and_parses_embedding():
    captured_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embeddings"
        captured_body.update(json.loads(request.content))
        return httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})

    client = OllamaClient(http_client=_mock_client(handler))
    embedding = await client.embed(
        "hello world", model="nomic-embed-text", prefix="search_document: "
    )

    assert embedding == [0.1, 0.2, 0.3]
    assert captured_body["prompt"] == "search_document: hello world"
    assert captured_body["model"] == "nomic-embed-text"


@pytest.mark.asyncio
async def test_embed_raises_when_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = OllamaClient(http_client=_mock_client(handler))

    with pytest.raises(OllamaUnreachableError):
        await client.embed("hello world", model="nomic-embed-text", prefix="search_document: ")
