import httpx


class OllamaUnreachableError(Exception):
    """Raised when the native Ollama instance cannot be reached."""


class OllamaClient:
    def __init__(self, base_url: str | None = None, http_client: httpx.AsyncClient | None = None):
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

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

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
