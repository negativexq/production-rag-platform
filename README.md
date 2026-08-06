# Production RAG Platform

A PDF Q&A system with page/paragraph-level citations, hybrid search (dense +
sparse), cross-encoder reranking, and OpenTelemetry tracing — an
enterprise-style production architecture.

Not a simple vector DB demo — an end-to-end pipeline covering retrieval,
reranking, grounded generation, and observability.

## Architecture

```
PDF/Docs → Parser (PyMuPDF) → Chunking
        → Embedding (Ollama, native)
        → Qdrant (dense + sparse, Docker)
        → Hybrid Search (Qdrant native fusion)
        → Metadata Filtering (Qdrant payload filters)
        → Cross-Encoder Reranker
        → LLM (Ollama, native, streaming)
        → Answer + Citation (+ OpenTelemetry trace)
```

```
┌─────────────────────────────────────────────┐   Docker Compose
│  backend (FastAPI, :8000)                    │
│    ├─ Qdrant  (:6333) ─────────────┐         │
│    └─ Jaeger  (:16686/OTLP :4317)  │         │
└──────────────┼──────────────────────┼────────┘
               │ host.docker.internal │
               ▼                      │
        Ollama (native, :11434) ◄─────┘
```

**Why is Ollama native (not in Docker)?** Docker Desktop on macOS doesn't
support Metal GPU passthrough. Putting Ollama in a container would drop it
to CPU and lose GPU speed. So Ollama keeps running **natively on the host**
— the one hard prerequisite for this project.

**Is the backend containerized or native?** As of Sprint 10, the backend
(`app.main:app`) runs **in a container** — the `backend` service in
`docker-compose.yml` reaches native Ollama via `host.docker.internal:11434`.
This assumption had been sitting in `.env.example` since Sprint 0; Sprint 10
actually verified that the container can reach native Ollama
(`docker compose exec backend curl http://host.docker.internal:11434/api/tags`).
The ingestion CLI (`make ingest`) still runs on the host/venv — it's a batch
job reading local PDF files and wasn't moved into the container (see the
[docs/PLANNING.md](docs/PLANNING.md) Sprint 10 closing note). If you'd rather
run the backend on the host instead of in a container for local development
(`make dev`), use `OLLAMA_BASE_URL=http://localhost:11434`.

See [docs/PLANNING.md](docs/PLANNING.md) for sprint plans and progress notes.

## What's Here (Sprint 0-10)

Every sprint went test-first, was verified against real data, and was closed
out with a note in `docs/PLANNING.md` — measured findings instead of
assumptions (e.g. SPLADE being unacceptably slow on an M2, RAGAS being
unusable due to a dependency conflict, `OllamaClient`'s 10s timeout turning
out to be a real production bug) were recorded at the end of each sprint.

| Sprint | Topic |
|---|---|
| 0 | Foundation — FastAPI skeleton, Qdrant+Jaeger (Docker), native Ollama |
| 1 | PDF ingestion — page/paragraph-preserving chunking with PyMuPDF |
| 2 | Embedding + idempotent Qdrant ingestion (`nomic-embed-text`) |
| 3 | Hybrid search — dense + sparse (BM25), Qdrant native RRF fusion |
| 4 | Metadata filtering — payload-based (`doc_id`, `source_filename`, `page_number`) |
| 5 | Cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`) |
| 6 | Grounded streaming generation — page/paragraph citations + post-hoc grounding check |
| 7 | File-based prompt versioning (`prompts/answer_v1.txt`, `v2.txt`) |
| 8 | OpenTelemetry tracing — the whole pipeline traceable as one waterfall in Jaeger |
| 9 | Golden-set evaluation (DeepEval + 7B judge) — chunk size/k-n/prompt decisions settled with real data |
| 10 | Docker Compose polish — backend containerized, Ollama stays native |

## Prerequisites

- Docker Desktop
- [Ollama](https://ollama.com) installed natively (on the host, **not in
  Docker** — see the "why native" section above)
- Python 3.12+ (only needed for host-side commands like `make dev`/
  `make ingest`/`make test`; the backend itself runs in a container, so
  `docker compose up` alone doesn't require Python)

## Setup (From Scratch)

### 1. Install Ollama and pull the models

```bash
ollama pull qwen2.5:3b-instruct
ollama pull nomic-embed-text
```

Verify Ollama is running:

```bash
ollama list
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

The values in `.env.example` are the correct defaults for running natively
on the host (`make dev`); the `backend` service in `docker compose` already
gets its own correct values (`host.docker.internal`, the `qdrant`/`jaeger`
service names) from `docker-compose.yml` and doesn't need `.env`.

### 3. Bring up the whole system with one command

```bash
docker compose up -d
```

This brings up Qdrant + Jaeger + the backend (containerized). On first run
the backend image gets built (the cross-encoder/sparse-encoder models are
downloaded from HuggingFace on first use — cached in an `hf_cache` volume so
they aren't re-downloaded on subsequent `up`s).

- Qdrant: http://localhost:6333/dashboard
- Jaeger UI: http://localhost:16686
- Backend: http://localhost:8000

### 4. Verify

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/ollama
```

`/health/ollama` should connect to native Ollama from inside the container
and return the same model list as `ollama list`. If Ollama isn't running,
it returns 503 with `{"status": "unreachable", ...}`.

### 5. Ingest a PDF and ask a question

Ingestion runs from the host/venv (it reads local files):

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
make ingest PATH_ARG=./docs
```

Then ask the containerized backend a real question:

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"..."}'
```

You should get a streaming answer with page/paragraph references
(`[s.page/paragraph]`) and a `grounding` event (verifying whether the
citations actually exist in the retrieved context).

## PDF Ingestion

Parses, chunks, embeds (with `nomic-embed-text`), and writes every `.pdf` in
a folder to Qdrant:

```bash
make ingest PATH_ARG=./docs
```

- Re-ingesting the same file doesn't create duplicate points (idempotent via
  a content hash + deterministic point ID).
- Qdrant collection: `rag_chunks` (dense, 768 dimensions, cosine distance).
- Scanned/image-only (no text layer) PDFs aren't supported — see
  [docs/PLANNING.md](docs/PLANNING.md) Sprint 1.

## Development

```bash
make dev    # run the backend on the host (venv) instead of in a container
make test   # pytest
make lint   # ruff
make up     # docker compose up -d (Qdrant + Jaeger + backend, containerized)
make down   # docker compose down
```

To rebuild the container after changing backend code:
`docker compose build backend && docker compose up -d backend`.

## Evaluation

Reports retrieval + generation quality metrics over a golden Q&A set (usable
as a pre-deploy regression check):

```bash
PYTHONPATH=. .venv/bin/python scripts/run_evaluation.py --skip-generation-metrics
```

See [docs/PLANNING.md](docs/PLANNING.md) Sprint 9 for the judge model
decision, real comparison results, and options like `--limit`/`--golden-set`.

## Project Structure

```
app/
├── main.py          # FastAPI app, /health, /health/ollama, /chat
├── api/              # HTTP layer
├── ingestion/          # PDF parsing + chunking + Qdrant upsert
├── retrieval/           # Hybrid search + filtering
├── reranker/             # Cross-encoder reranking
├── llm/                   # Ollama client, grounded generation
├── evaluation/              # Golden-set evaluation harness
└── shared/                   # Config, tracing, shared helpers
Dockerfile              # backend image (python:3.12-slim)
docker-compose.yml        # qdrant + jaeger + backend
```

## License

[MIT](LICENSE)
