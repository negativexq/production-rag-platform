"""Runs the golden Q&A set end-to-end against real Ollama + real Qdrant and
prints/saves a retrieval + generation quality report. Usable as a
pre-deploy regression check, and as the comparison harness for Sprint 1's
chunk size, Sprint 5's k/n, and Sprint 7's prompt version decisions.

Ingests a fresh copy of the golden source PDF into a throwaway collection
for each run (so chunk-size sweeps are actually comparable), then tears it
down.

Examples:
    # Retrieval-only (fast, no judge LLM — good for chunk-size/k-n sweeps)
    PYTHONPATH=. .venv/bin/python scripts/run_evaluation.py --skip-generation-metrics

    # Full run (retrieval + generation metrics via the 7B judge, ~10+ min)
    PYTHONPATH=. .venv/bin/python scripts/run_evaluation.py --output report.json

    # Compare prompt v2 instead of v1
    PYTHONPATH=. .venv/bin/python scripts/run_evaluation.py \
        --prompt-version v2 --skip-generation-metrics
"""

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path

from qdrant_client import QdrantClient

from app.evaluation.generation_metrics import build_default_metrics, compute_generation_metrics
from app.evaluation.harness import build_report, load_golden_set, run_evaluation
from app.ingestion.ingest import SEARCH_DOCUMENT_PREFIX, ingest_path
from app.ingestion.qdrant_store import QdrantStore
from app.llm.generate import stream_answer
from app.llm.ollama_client import OllamaClient
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.search import RERANK_CANDIDATE_K, RERANK_TOP_N, search
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings
from tests.fixtures.golden_source import build_golden_source_pdf

GOLDEN_QA_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "golden_qa.json"


async def main(args: argparse.Namespace) -> None:
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    store = QdrantStore(client=qdrant_client, collection_name=args.collection)
    sparse_encoder = SparseEncoder()
    reranker = None if args.no_reranker else CrossEncoderReranker()

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text, model=settings.ollama_embed_model, prefix=SEARCH_DOCUMENT_PREFIX
        )

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "golden_source.pdf"
            build_golden_source_pdf(str(pdf_path))
            await ingest_path(
                tmp_dir,
                store,
                embed_fn,
                sparse_encoder,
                chunk_size_tokens=args.chunk_size,
                overlap_tokens=args.overlap,
            )

        questions = load_golden_set(args.golden_set or str(GOLDEN_QA_PATH))
        if args.limit:
            questions = questions[: args.limit]

        async def search_fn(question: str):
            return await search(
                question,
                ollama=ollama,
                sparse_encoder=sparse_encoder,
                qdrant_client=qdrant_client,
                collection_name=args.collection,
                embed_model=settings.ollama_embed_model,
                reranker=reranker,
                top_k=args.top_k,
                top_n=args.top_n,
            )

        async def generate_fn(question: str, chunks) -> str:
            parts = []
            async for event in stream_answer(
                question,
                chunks,
                ollama,
                model=settings.ollama_model,
                prompt_version=args.prompt_version,
            ):
                if event["type"] == "token":
                    parts.append(event["content"])
            return "".join(parts)

        generation_metrics_fn = None
        if not args.skip_generation_metrics:
            metrics = build_default_metrics(base_url=settings.ollama_base_url)

            def generation_metrics_fn(question, answer, contexts):
                return compute_generation_metrics(question, answer, contexts, metrics)

        def progress_callback(phase: str, index: int, total: int, question_id: str) -> None:
            label = "generation (3B)" if phase == "generate" else "judge (7B)"
            print(f"[{index}/{total}] {label} done: {question_id}", flush=True)

        t0 = time.time()
        results = await run_evaluation(
            questions, search_fn, generate_fn, generation_metrics_fn, progress_callback
        )
        elapsed = time.time() - t0

        report = build_report(results)
        report["config"] = {
            "chunk_size_tokens": args.chunk_size,
            "overlap_tokens": args.overlap,
            "top_k": args.top_k,
            "top_n": args.top_n,
            "prompt_version": args.prompt_version,
            "reranker_enabled": reranker is not None,
            "generation_metrics_enabled": not args.skip_generation_metrics,
        }
        report["elapsed_seconds"] = round(elapsed, 1)

        print(json.dumps(report, indent=2))
        if args.output:
            Path(args.output).write_text(json.dumps(report, indent=2))
            print(f"\nSaved report to {args.output}")
    finally:
        qdrant_client.delete_collection(args.collection)
        await ollama.aclose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the golden Q&A evaluation harness")
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--overlap", type=int, default=50)
    parser.add_argument("--top-k", type=int, default=RERANK_CANDIDATE_K)
    parser.add_argument("--top-n", type=int, default=RERANK_TOP_N)
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument("--no-reranker", action="store_true")
    parser.add_argument("--skip-generation-metrics", action="store_true")
    parser.add_argument("--collection", default="eval_golden_set")
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--limit", type=int, default=None, help="Only evaluate the first N golden questions"
    )
    parser.add_argument("--golden-set", default=None, help="Override path to golden Q&A JSON")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
