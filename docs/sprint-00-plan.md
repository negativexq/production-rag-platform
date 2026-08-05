# Sprint 0 — Foundation Planı

## Amaç
Boş repodan, tüm servislerin birbirine ulaştığı doğrulanmış bir temel çıkarmak.

## Repo İskeleti

```
production-rag-platform/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, /health ve /health/ollama
│   ├── api/
│   │   └── __init__.py
│   ├── ingestion/
│   │   └── __init__.py
│   ├── retrieval/
│   │   └── __init__.py
│   ├── reranker/
│   │   └── __init__.py
│   ├── llm/
│   │   ├── __init__.py
│   │   └── ollama_client.py # httpx tabanlı Ollama client (native, host.docker.internal)
│   └── shared/
│       ├── __init__.py
│       └── config.py        # pydantic-settings ile env config
├── tests/
│   ├── __init__.py
│   ├── test_health.py
│   └── test_ollama_client.py
├── docs/
│   ├── PLANNING.md
│   └── sprint-00-plan.md
├── docker-compose.yml        # Qdrant + Jaeger (Ollama YOK)
├── Makefile                  # dev, test, lint, up, down
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
└── README.md
```

## Kararlar

- **Paket yönetimi**: pip + venv (ModelOps projesiyle tutarlılık için).
- **Generation modeli**: `qwen2.5:3b-instruct` (kullanıcı tarafından netleştirildi, latency ölçümüne göre 7B'ye geçiş ileride değerlendirilebilir).
- **Embedding modeli**: `nomic-embed-text`.
- **HTTP client**: `httpx` (async, FastAPI ile uyumlu, Ollama native API'sine `http://host.docker.internal:11434` üzerinden bağlanacak).
- **Config**: `pydantic-settings` ile `.env` üzerinden `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_EMBED_MODEL` gibi değerler.
- Ollama container'a KONMUYOR — native/host'ta, Docker Desktop macOS Metal GPU passthrough desteklemediği için.

## Test-First Plan

1. `tests/test_health.py`
   - `GET /health` → 200, `{"status": "ok"}`
2. `tests/test_ollama_client.py`
   - `OllamaClient` sınıfı httpx mock ile: base url doğru kuruluyor mu, `/api/tags` çağrısı doğru parse ediliyor mu
   - Gerçek Ollama'ya bağlantı testi ayrı bir smoke-test olarak (`GET /health/ollama`), CI'da mock'lanabilir ama local'de gerçek native Ollama'ya vuracak

## Adımlar

1. `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `.gitignore`, `.env.example` oluştur
2. venv kur, bağımlılıkları yükle (fastapi, uvicorn, httpx, pydantic-settings, pytest, pytest-asyncio, ruff)
3. `app/shared/config.py` — Settings sınıfı
4. `app/llm/ollama_client.py` — OllamaClient (list models, health check)
5. `app/main.py` — FastAPI app, `/health`, `/health/ollama`
6. Testleri yaz (önce kırmızı), sonra implementasyonla yeşile çevir
7. `docker-compose.yml` — Qdrant (6333/6334) + Jaeger (16686 UI, 4317/4318 OTLP)
8. `Makefile` — `make dev`, `make test`, `make lint`, `make up`, `make down`
9. README.md — kurulum adımları (Ollama native pull komutları dahil), mimari özeti
10. Doğrulama: `docker compose up -d`, `/health` 200, `/health/ollama` gerçek Ollama'ya bağlanıp model listesi dönüyor mu
11. `docs/PLANNING.md` Sprint 0 bölümüne kapanış notu ekle
12. Git init + ilk commit (AI co-author satırı YOK)

## Definition of Done

- `docker compose up` ile Qdrant + Jaeger ayağa kalkıyor
- `/health` 200 dönüyor
- `/health/ollama` native Ollama'ya bağlanıp gerçek model listesini dönüyor
- Testler yeşil (`make test`)
- README güncel
