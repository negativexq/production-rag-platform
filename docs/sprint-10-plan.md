# Sprint 10 — Docker Compose Polish Planı

## Amaç
Tüm sistemin tek komutla ayağa kalkmasını sağlamak.

## Karar — Backend Container'a Giriyor (Ollama Hâlâ Native)

Planın orijinal scope satırı zaten şunu söylüyor: *"`docker compose up`:
Qdrant + Jaeger + backend"* — yani backend'in container'a girmesi başından
beri öngörülmüştü. Bu sprint'te bunu netleştirip gerçekten uyguluyoruz:

- **Backend (FastAPI/`app.main:app`) container'a giriyor.** Sprint 0'dan
  beri `.env.example`'da bekleyen `OLLAMA_BASE_URL=http://host.docker.internal:11434`
  varsayımı bu sprint'te **gerçekten** test edilecek — container içinden
  native Ollama'ya erişimin çalıştığı varsayılmayacak, doğrulanacak.
- **Ollama hâlâ native kalıyor** — Sprint 0'daki gerekçe değişmedi (Docker
  Desktop macOS'ta Metal GPU passthrough yok).
- **`make ingest` (CLI) container'a GİRMİYOR, host/venv'de kalıyor.**
  Gerekçe: ingestion bir batch/CLI işi, host'taki PDF dosyalarını okuyor;
  bunu container'a taşımak dosya mount'u gibi ek karmaşıklık gerektirir ve
  bu sprint'in "tek komutla ayağa kalksın" hedefiyle doğrudan ilgili değil.
  Asıl kanıtlanması gereken şey, **serving** path'inin (gerçek bir `/chat`
  isteği) container'dan native Ollama'ya gerçekten ulaşabildiği — ingestion
  zaten Sprint 2-9 boyunca host/venv'den çalışıp doğrulandı, değişmiyor.
- **Model cache (sentence-transformers, fastembed) için named volume**:
  backend container'ı ilk açılışta CrossEncoder + sparse encoder
  modellerini HuggingFace'ten indiriyor (~9s+ gecikme, Sprint 5/8'de
  ölçülmüştü). Bunu her `docker compose up`'ta tekrar indirmemek için
  `~/.cache/huggingface` container içi yolu bir named volume'a bağlanacak.

## Modül

```
Dockerfile                  # backend image: python:3.12-slim + requirements.txt + app/
docker-compose.yml            # + backend servisi, + hf_cache volume'ü
.env.example                   # backend servisi env'i docker-compose.yml'de ayrıca set ediliyor
                                # (host.docker.internal/qdrant/jaeger servis adları) — .env.example
                                # host'ta native çalıştırma (make dev) için doğru kalmaya devam ediyor
```

## Kararlar

- **Backend servisinin env'i `.env` dosyasından DEĞİL, `docker-compose.yml`
  içindeki `environment:` bloğundan geliyor** — çünkü container içi doğru
  değerler (`QDRANT_URL=http://qdrant:6333`, `OTEL_EXPORTER_OTLP_ENDPOINT=
  http://jaeger:4317`, `OLLAMA_BASE_URL=http://host.docker.internal:11434`)
  host'ta native çalıştırırken (`make dev`) kullanılan değerlerden (`localhost`)
  farklı. İki ayrı `.env` dosyası yerine, tek `.env.example`'ın host/native
  senaryo için doğru kalması + compose'un kendi servis adlarını açıkça
  set etmesi tercih edildi — daha az "hangi ortamdayım" karışıklığı.
- **Dockerfile taban imaj**: `python:3.12-slim` (Sprint 0'da venv için
  seçilen 3.12 ile tutarlı).
- **Healthcheck**: backend servisine `/health` üzerinden bir Docker
  healthcheck eklenecek, `depends_on` ile qdrant/jaeger'ın `service_started`
  durumuna bağlı olacak (Ollama native olduğu için compose bunu bekleyemez
  — README'de net bir ön koşul olarak belirtilecek).

## Test-First / Doğrulama Planı

Bu sprint büyük ölçüde altyapı/entegrasyon işi — "test-first" burada gerçek
bir e2e doğrulama olarak uygulanacak (birim test edilecek yeni bir iş
mantığı yok):

1. `docker compose build` gerçekten başarılı image üretiyor mu
2. `docker compose up -d` sonrası backend container'ı `/health` üzerinden
   200 dönüyor mu
3. **Varsayılmayacak, gerçekten test edilecek**: backend container'ından
   `curl http://host.docker.internal:11434/api/tags` (container `exec` ile)
   gerçekten native Ollama'ya ulaşıyor mu
4. `docker compose down -v` (temiz durum) + yeniden `docker compose up -d`
   sonrası sistem yine çalışıyor mu (DoD'nin "sıfırdan" şartı)
5. Host'tan `make ingest` ile örnek bir PDF ingest edilip, container'daki
   backend'e gerçek bir `/chat` isteği atılıp uçtan uca (embed → retrieve →
   rerank → generate → citation) çalıştığı gösterilecek

## Adımlar

1. `Dockerfile` yaz
2. `docker-compose.yml`'e `backend` servisi + `hf_cache` volume ekle
3. `docker compose build` ile gerçekten imajı derle, hataları çöz
4. `docker compose up -d` ile ayağa kaldır, `/health` doğrula
5. Container'dan native Ollama'ya erişimi `docker compose exec` ile doğrula
6. `docker compose down -v` + yeniden `up -d` ile temiz kurulum senaryosunu
   doğrula
7. Host'tan `make ingest` + container'daki backend'e gerçek `/chat` isteği
8. README'yi güncelle: mimari diyagramı, Ollama'nın native ön koşul olduğu,
   `docker compose up` + `make ingest` + örnek sorgu akışı
9. `docs/PLANNING.md` kapanış notu

## Definition of Done

- Dokümante edilen kurulum adımları izlenerek (Ollama kurulu + model pull
  edilmiş olmak kaydıyla) sistem uçtan uca çalışıyor
- Bu, gerçekten sıfırdan (`docker compose down -v` + yeniden `up`) denenerek
  doğrulanmış
