# Production RAG Platform

A PDF Q&A system with page/paragraph-level citations, hybrid search (dense + sparse),
cross-encoder reranking, and OpenTelemetry tracing — an enterprise-style production
architecture.

Not a simple vector DB demo — an end-to-end pipeline covering retrieval, reranking,
grounded generation, and observability.

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

**Why is Ollama native (not in Docker)?** Docker Desktop on macOS doesn't support
Metal GPU passthrough. Putting Ollama in a container would drop it to CPU and lose
GPU speed. So Ollama runs natively on the host; services that don't need a GPU, like
Qdrant and Jaeger, stay in Docker Compose. The backend connects to native Ollama from
inside the container via `host.docker.internal` (if you run the backend in a container
yourself); for local development, if the backend also runs on the host,
`http://localhost:11434` works too.

See [docs/PLANNING.md](docs/PLANNING.md) for sprint plans and progress notes.

## Prerequisites

- Python 3.12+
- Docker Desktop
- [Ollama](https://ollama.com) installed natively (on the host, not in Docker)

## Setup

### 1. Pull the Ollama models

```bash
ollama pull qwen2.5:3b-instruct
ollama pull nomic-embed-text
```

Verify Ollama is running:

```bash
ollama list
```

### 2. Python environment

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
```

### 3. Bring up Qdrant + Jaeger

```bash
make up
```

- Qdrant: http://localhost:6333/dashboard
- Jaeger UI: http://localhost:16686

### 4. Run the backend

```bash
make dev
```

## Verification

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/ollama
```

`/health/ollama` should connect to native Ollama and return the same model list as
`ollama list`. If Ollama isn't running, it returns 503 and `{"status": "unreachable", ...}`.

## Development

```bash
make test   # pytest
make lint   # ruff
make down   # stop Qdrant + Jaeger
```

## Project Structure

```
app/
├── main.py          # FastAPI app, /health, /health/ollama
├── api/             # HTTP layer (will grow in later sprints)
├── ingestion/        # PDF parsing + chunking
├── retrieval/         # Hybrid search
├── reranker/          # Cross-encoder reranking
├── llm/               # Ollama client, generation
└── shared/            # Config, shared helpers
```
