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
