from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.llm.ollama_client import OllamaClient, OllamaUnreachableError
from app.shared.config import settings

app = FastAPI(title="Production RAG Platform")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/ollama")
async def health_ollama():
    client = OllamaClient(base_url=settings.ollama_base_url)
    try:
        models = await client.list_models()
    except OllamaUnreachableError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unreachable",
                "base_url": settings.ollama_base_url,
                "detail": str(exc),
            },
        )
    finally:
        await client.aclose()

    return {"status": "ok", "base_url": settings.ollama_base_url, "models": models}
