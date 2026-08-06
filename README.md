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

## Technologies Used

Layer by layer, what's actually running (not aspirational — each line was
verified in a sprint closing note in [docs/PLANNING.md](docs/PLANNING.md)):

| Layer | Technology | Notes |
|---|---|---|
| Parsing | PyMuPDF (`fitz`) | Page/paragraph-preserving text extraction (Sprint 1) |
| Chunking | Whitespace token counter, 500/50 (size/overlap) | Provisional default; Sprint 9 found the right size is corpus-dependent, kept as-is (see Known Limitations) |
| Embedding | Ollama (native, Metal), `nomic-embed-text` | 768-dim, cosine distance; requires `search_document:`/`search_query:` task prefixes for quality (Sprint 2/3) |
| Generation | Ollama (native, Metal), `qwen2.5:7b-instruct` | Switched from `qwen2.5:3b-instruct` after a real side-by-side comparison found the 3B model hallucinated a factual detail (wrong company name) with no citation to catch it; 7B was correct and grammatically clean. The initial ~6x latency penalty (22s vs 3.7s) turned out to be mostly a cold-start cost — Ollama unloads an idle model after 5 minutes by default; `OllamaClient` now sends `keep_alive=30m` on every call, so a warm 7B request is ~2.9s. See [docs/PLANNING.md](docs/PLANNING.md) Sprint 12 post-release notes |
| Vector DB | Qdrant | Dense + sparse (BM25 via FastEmbed `Qdrant/bm25`), native RRF fusion (Sprint 2/3). SPLADE was tried and rejected — ~1000x slower than BM25 on an M2 CPU |
| Metadata filtering | Qdrant payload filters | `doc_id`, `source_filename`, `page_number` (Sprint 4) |
| Reranking | `sentence-transformers` CrossEncoder, `ms-marco-MiniLM-L-6-v2` | Runs on CPU, ~2.8ms/pair measured (Sprint 5) |
| Backend | FastAPI | Containerized since Sprint 10; SSE streaming for `/chat` (Sprint 6) |
| Prompt versioning | File-based (`prompts/answer_v1.txt`, `v2.txt`) | Active version is a config value; v1 kept as default after real evaluation (Sprint 7/9) |
| Observability | OpenTelemetry + Jaeger | 6 spans/request: `chat_request`, `load_models`, `embed_query`, `retrieve_hybrid`, `rerank`, `generate` (Sprint 8) |
| Evaluation | DeepEval + `qwen2.5:7b-instruct` (judge) | RAGAS was tried first and rejected — an unresolvable dependency conflict (`langchain_community.chat_models.vertexai` import failure), not a design choice (Sprint 9) |
| UI | Streamlit | Separate venv (`.venv-ui`) + `requirements-ui.txt` — avoids a real `starlette` version conflict with FastAPI's pin (Sprint 11) |
| Orchestration | Docker Compose | Qdrant + Jaeger + backend; Ollama stays native — Docker Desktop on macOS has no Metal GPU passthrough (Sprint 0/10) |

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
ollama pull qwen2.5:7b-instruct
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

## Known Limitations

Real, documented gaps — not a hedge. Each one is traceable to a sprint
closing note in [docs/PLANNING.md](docs/PLANNING.md).

- **Citation page/paragraph numbers can be wrong even for the correct
  document.** The judge/generation model occasionally cites a real
  document but a fabricated page/paragraph within it. The post-hoc
  grounding check catches and flags this (⚠️ in the UI) but doesn't block
  the streamed answer — see the Sprint 11 post-release bug fix note.
- **The same citation tag can be repeated after every word or list item**
  instead of once per sentence/list. A prompt instruction reduced this but
  didn't eliminate it — confirmed probabilistic (2 clean out of 3 repeat
  trials), not a guarantee. See the Sprint 11 follow-up note.
- **Metadata filtering is limited to `doc_id`, `source_filename`, and
  `page_number`** — there's no date or tag field. Adding one requires an
  ingestion-side design decision (file date? PDF metadata? manual
  tagging?) that was deliberately deferred (Sprint 4).
- **Chunk size (500/50 tokens) and rerank k/n (20/5) were only validated
  against one small, single-source golden set** (a 6-page fictional PDF)
  — not revalidated at scale or against a diverse corpus. Sprint 9 found
  smaller chunks (paragraph-level) roughly doubled precision on that
  golden set, but the defaults were deliberately left unchanged pending
  broader validation.
- **Scanned/image-only PDFs (no text layer) aren't supported** — pages
  without extractable text are silently skipped during ingestion
  (Sprint 1).
- **No query rewriting or HyDE** — questions are embedded and searched
  exactly as typed.
- **`qdrant-client`'s `:memory:` test mode diverges from a real server**
  in two confirmed cases: querying an empty collection with the sparse
  IDF modifier throws `KeyError` locally but returns an empty result on a
  real server (Sprint 3), and `query_filter` is silently ignored during
  prefetch+fusion queries locally but is correctly applied on a real
  server (Sprint 4). Tests that depend on this behavior require a real
  Qdrant instance and are skipped when one isn't available.
- **Single-user, single-session** — no auth, no multi-tenancy, no
  persisted conversation history. `st.session_state` holds chat history
  only for the current browser session; a page refresh clears it. A
  deliberate scope decision, not an oversight (Sprint 11).

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
