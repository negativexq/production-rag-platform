"""Concrete demonstration for Sprint 7's DoD: same question, same context,
answered with prompt v1 vs v2, against real Ollama — showing a real,
measured behavior difference, not a constructed claim.

Run with native Ollama running:
    PYTHONPATH=. .venv/bin/python scripts/demo_prompt_versions.py
"""

import asyncio

from app.llm.generate import stream_answer
from app.llm.grounding import check_grounding
from app.llm.ollama_client import OllamaClient
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import settings

QUESTION = "What is the return policy for a defective product?"
CONTEXT_CHUNKS = [
    SearchResult(
        score=0.9,
        payload={
            "page_number": 2,
            "paragraph_index": 0,
            "text": "Defective products can be returned within 30 days for a full refund.",
        },
    )
]


async def run_version(ollama: OllamaClient, version: str) -> None:
    answer_parts = []
    metadata = None
    grounding = None

    async for event in stream_answer(
        QUESTION, CONTEXT_CHUNKS, ollama, model=settings.ollama_model, prompt_version=version
    ):
        if event["type"] == "metadata":
            metadata = event
        elif event["type"] == "token":
            answer_parts.append(event["content"])
        else:
            grounding = event

    answer = "".join(answer_parts)
    print(f"--- prompt_version={version} ---")
    print(f"metadata event: {metadata}")
    print(f"answer: {answer!r}")
    print(f"grounding (from stream): {grounding}")
    print(f"grounding (re-checked standalone): {check_grounding(answer, CONTEXT_CHUNKS)}")
    print()


async def main() -> None:
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    try:
        await run_version(ollama, "v1")
        await run_version(ollama, "v2")
    finally:
        await ollama.aclose()


if __name__ == "__main__":
    asyncio.run(main())
