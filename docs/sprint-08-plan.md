# Sprint 8 — OpenTelemetry Tracing Planı

## Amaç
Pipeline'ın her adımını uçtan uca izlenebilir kılmak.

## Doğrulanan Gerçekler (varsayılmadı)

- **OTLP endpoint**: `.env`'deki `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`
  zaten Jaeger'ın OTLP gRPC portuna (docker-compose'da `4317:4317`) işaret
  ediyor — değişiklik gerekmedi.
- **Gerçek export testi**: `OTLPSpanExporter` ile deneme bir span gönderildi,
  Jaeger API'sinden (`/api/traces?service=probe-service`) gerçekten geri
  okunabildiği doğrulandı. `opentelemetry-sdk`/`api`/`exporter-otlp-proto-grpc`
  `1.29.0` kullanıldı (mevcut `qdrant-client`'ın grpc-tools bağımlılığıyla
  protobuf sürüm uyarısı veriyor ama gerçek çalışmayı bozmuyor — test suite'i
  ve manuel OTel/Qdrant kullanımı sorunsuz, `pip`'in dependency-resolver
  uyarısı zararsız).
- **Qdrant fusion sonuçlarında dense/sparse alt-skorları YOK**: `ScoredPoint`
  nesnesinin alanları (`id, score, payload, vector, version, ...`) incelendi
  — `FusionQuery(fusion=RRF)` ile gelen sonuçta sadece **tek bir birleşik
  `score`** var, ayrı dense/sparse component skorları Qdrant tarafından
  döndürülmüyor. Bunları almak isteseydik, dense-only + sparse-only + fused
  olmak üzere **3 ayrı sorgu** atmamız gerekirdi — bu da her kullanıcı
  sorgusunun retrieval gecikmesini gözlemlenebilirlik uğruna 3 katına çıkarır.
  **Karar**: sadece fused RRF skorunu (ve top_k/prefetch_limit parametrelerini)
  span'e yazıyoruz; ayrı dense/sparse skor talebi bu sprint'in kapsamı dışında
  bırakılıyor, gerekçesiyle birlikte not düşülüyor.

## Kapsam Netleştirmesi — "Parse" Adımı Sorgu Zamanında Yok

Plandaki "Parse → embed → retrieve → rerank → generate" sıralaması mimari
diyagramdan (ingestion + query akışlarının birleşimi) geliyor. Ama DoD açıkça
**"tek bir sorgunun"** (query-time) tüm pipeline'ını istiyor — PDF parse
etme ingestion zamanında (offline, `make ingest`) olur, sorgu anında hiç
çalışmaz. Bu yüzden:

- **Query-time span'leri** (DoD'nin somut kanıtının odağı): `embed_query` →
  `retrieve_hybrid` → `rerank` → `generate`, hepsi tek bir `chat_request`
  kök span'i altında.
- **Ingestion-time span'leri** (ek, DoD'nin kapsamı dışında ama "pipeline'ın
  her adımı" ruhuna uygun düşsün diye eklendi): `parse_and_chunk` → `embed_batch`
  → `upsert_batch`, `ingest_document` kök span'i altında.

## Modül

```
app/shared/tracing.py    # setup_tracing(), get_tracer() — TracerProvider + OTLP exporter
app/retrieval/search.py   # + embed_query, retrieve_hybrid, rerank span'leri
app/llm/generate.py       # + generate span'i (stream_answer'ın tamamını sarıyor)
app/api/chat.py            # + chat_request kök span'i
app/ingestion/ingest.py     # + parse_and_chunk, embed_batch, upsert_batch span'leri
app/main.py                  # setup_tracing() çağrısı (app başlangıcında)
```

## Kararlar

- **Span attribute'ları (yüksek kardinaliteli veri YOK)**:
  - `embed_query`: `embed.model`
  - `retrieve_hybrid`: `retrieve.candidate_count`, `retrieve.top_k`,
    `retrieve.top_score` (sadece en yüksek skor, referans için — tüm skor
    listesini yazmak yüksek kardinalite sayılmasa da gereksiz, tek sayı yeterli)
  - `rerank`: `rerank.top_n`, `rerank.top_score`
  - `generate`: `generate.model`, `generate.prompt_version`,
    `generate.context_chunk_count`, `generate.token_count` (üretilen token
    sayısı — tam cevap metni DEĞİL), `generate.grounded`,
    `generate.citation_count`
  - Hiçbir span'e tam chunk text'i, tam prompt içeriği veya tam cevap metni
    yazılmıyor — sadece sayılar/referanslar (plandaki açık soru böyle
    netleşti).
- **Streaming span'in ömrü**: `generate` span'i, `stream_answer`'ın **tüm**
  async generator gövdesini sarıyor (`with tracer.start_as_current_span(...)`
  bloğu içinde `yield` ifadeleri var) — Python'da bir context manager, generator
  suspend/resume (yield) sırasında kapanmıyor, sadece generator tükenince veya
  `close()` çağrılınca kapanıyor. **Bu varsayılmadı** — gerçek bir `/chat`
  isteğiyle test edilip `generate` span süresinin, tüm streaming'in bittiği
  ana kadar (ilk byte değil) uzandığı Jaeger'dan çekilen gerçek trace
  verisiyle doğrulanacak (bkz. Test-First Plan #4).
- **Tracer kurulumu**: `setup_tracing()` idempotent (birden fazla çağrılırsa
  tekrar provider kurmuyor), `app/main.py` başlangıcında ve
  `app/ingestion/cli.py`'de çağrılıyor.

## Test-First Plan

1. `tests/test_tracing.py` — OTel SDK'nın `InMemorySpanExporter`'ı ile
   (gerçek ağ yok, gerçek SDK davranışı): `setup_tracing()`'in bir
   `TracerProvider` kurduğunu, `get_tracer()`'ın span üretebildiğini doğrula.
2. `tests/test_search.py`'a ekle — `search()`'in `embed_query`,
   `retrieve_hybrid`, (varsa) `rerank` span'lerini doğru attribute'larla
   ürettiğini `InMemorySpanExporter` ile doğrula.
3. `tests/test_generate.py`'a ekle — `stream_answer`'ın `generate` span'ini
   doğru attribute'larla (model, prompt_version, token_count, grounded)
   ürettiğini doğrula.
4. **Gerçek Jaeger'a karşı e2e** (`tests/test_tracing_e2e.py`, servis
   kapalıyken atlanıyor): gerçek bir `/chat` isteği at, birkaç saniye bekle,
   Jaeger API'sinden (`/api/traces?service=...`) trace'i çek, doğrula:
   - Tek bir `traceID` altında `chat_request`, `embed_query`,
     `retrieve_hybrid`, `rerank`, `generate` span'lerinin hepsi var
   - `generate` span süresi, `chat_request` toplam süresine yakın (streaming
     bitene kadar açık kaldığının kanıtı — sadece ilk token'a kadar değil)
   - Yüksek kardinaliteli hiçbir attribute (tam chunk text'i vb.) yok

## Somut Kanıt Planı

Gerçek bir `/chat` isteği sonrası Jaeger API'sinden çekilen trace JSON'u
(`docs/`e ya da script çıktısına dahil edilecek) — waterfall'daki span'lerin
adları, süreleri ve parent-child ilişkisi raporlanacak.

## Adımlar

1. `requirements.txt`'e OTel paketlerini ekle
2. Kırmızı testleri yaz (1-3, in-memory exporter ile)
3. `app/shared/tracing.py` implementasyonu
4. `search.py`, `generate.py`'a span'leri ekle
5. `chat.py`'a kök span'i ekle, `main.py`'da `setup_tracing()` çağır
6. Testleri yeşile çevir, `ruff check` temiz
7. Gerçek `/chat` isteği + Jaeger API doğrulaması (e2e test + manuel kanıt)
8. İsteğe bağlı: `ingest.py`'a da span'ler ekle
9. Tracing'in eklediği overhead'i ölç (span oluşturma + export maliyeti)
10. `docs/PLANNING.md` kapanış notu

## Definition of Done

- Jaeger'da (veya API'sinden) tek bir sorgunun tüm pipeline'ı adım adım
  latency'siyle waterfall görünümünde izlenebiliyor
- Testler ve lint temiz
