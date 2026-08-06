import json
from collections.abc import AsyncIterator

import httpx

# A 10s default was measured to be too short for local generation: a 7B
# model used as an LLM judge (Sprint 9) hit httpx.ReadTimeout mid-request
# because it hadn't produced a first token within 10s under load. Local
# models on CPU/limited-RAM hardware can legitimately take well over a
# minute for a single call — see docs/PLANNING.md Sprint 9 closing note.
DEFAULT_TIMEOUT_SECONDS = 120.0


class OllamaUnreachableError(Exception):
    """Raised when the native Ollama instance cannot be reached."""


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def list_models(self) -> list[str]:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnreachableError(f"Could not reach Ollama: {exc}") from exc

        data = response.json()
        return [model["name"] for model in data.get("models", [])]

    async def embed(self, text: str, model: str, prefix: str = "") -> list[float]:
        try:
            response = await self._client.post(
                "/api/embeddings",
                json={"model": model, "prompt": f"{prefix}{text}"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnreachableError(f"Could not reach Ollama: {exc}") from exc

        return response.json()["embedding"]

    async def stream_chat(self, messages: list[dict], model: str) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST",
                "/api/chat",
                json={"model": model, "messages": messages, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
        except httpx.HTTPError as exc:
            raise OllamaUnreachableError(f"Could not reach Ollama: {exc}") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
