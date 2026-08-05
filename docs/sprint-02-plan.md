# Sprint 2 — Embedding + Qdrant Ingestion Planı

## Amaç
Chunk'ları embed edip Qdrant'a production-usulü bir şemayla yazmak.

## Doğrulanan Gerçekler (varsayılmadı, kontrol edildi)

- **`.env` içinde `OLLAMA_BASE_URL`**: hâlâ `http://localhost:11434` (Sprint 0'da
  belgelenen host.docker.internal/localhost ayrımı geçerliliğini koruyor —
  backend henüz container'a alınmadı).
- **Embedding boyutu**: `curl http://localhost:11434/api/embeddings -d
  '{"model":"nomic-embed-text","prompt":"hello world"}'` ile gerçek bir çağrı
  yapıldı → **768 boyut**. Ayrıca `ollama list`/`/api/tags` çıktısındaki
  `embedding_length: 768` alanıyla da teyit edildi.
- **Mesafe metriği**: Nomic'in HuggingFace model kartı (`nomic-ai/nomic-embed-text-v1.5`)
  embedding'lerin `F.normalize(..., p=2, dim=1)` ile L2-normalize edildiğini ve
  karşılaştırmada **cosine similarity** kullanılmasını belirtiyor → Qdrant
  collection'ında `Distance.COSINE`.
- **Task prefix gereksinimi (planda yoktu, araştırma sırasında ortaya çıktı)**:
  Nomic'in model kartı, embed edilecek metnin **mutlaka** bir görev prefix'i
  içermesini şart koşuyor: dokümanlar için `"search_document: "`, sorgular için
  `"search_query: "`. Prefix'siz embedding kalitesi düşük olur. Bu sprint'te
  ingestion tarafı `"search_document: "` prefix'ini kullanacak; sorgu tarafı
  (`"search_query: "`) Sprint 3'te (hybrid search) uygulanacak.

## Modül

```
app/llm/ollama_client.py   # + embed(text, prefix) metodu eklenecek
app/ingestion/
├── qdrant_store.py         # Collection yönetimi, deterministic point ID, batch upsert
└── cli.py                  # `python -m app.ingestion.cli --path ./docs`
app/shared/config.py        # + qdrant_collection_name ayarı
```

## Kararlar

- **Collection şeması**: named dense vector `"dense"`, size=768, distance=Cosine.
  Payload: `{doc_id, page_number, paragraph_index, char_range, text,
  source_filename}`. `char_range` Qdrant payload'da JSON-uyumlu olması için
  `[start, end]` listesi olarak saklanır (tuple değil).
- **Point ID (idempotency)**: Qdrant point ID'leri unsigned int ya da UUID
  olmalı. Deterministic UUID üretimi: `uuid.uuid5(NAMESPACE, f"{doc_id}:
  {page_number}:{paragraph_index}:{char_range[0]}:{char_range[1]}")`. Aynı
  dosya (aynı `doc_id`, çünkü içerik hash'i) tekrar ingest edilirse, parser
  deterministic olduğu için aynı chunk'lar aynı ID'leri üretir → Qdrant upsert
  aynı point'in üzerine yazar, duplicate oluşmaz.
- **Batch upsert**: chunk'lar sabit boyutlu batch'ler halinde (örn. 64)
  gönderilecek, tek tek point upsert edilmeyecek.
- **CLI**: `python -m app.ingestion.cli --path <klasör>` — klasördeki tüm
  `*.pdf` dosyalarını gezer, her biri için chunk + embed + upsert yapar, özet
  rapor basar (dosya sayısı, toplam chunk/point sayısı).

## Test-First Plan

1. `tests/test_ollama_client.py`'a ekle:
   - `embed()` doğru endpoint'e (`/api/embeddings`) doğru payload ile
     (prefix eklenmiş prompt) istek atıyor mu, response'u doğru parse ediyor mu
     (mock'lanmış httpx transport ile — gerçek ağ çağrısı yok)
   - Unreachable durumunda `OllamaUnreachableError` fırlatıyor mu
2. `tests/test_qdrant_store.py` — qdrant-client'ın `:memory:` modu (gerçek
   client davranışı, network yok, hızlı) ile:
   - Collection doğru boyut (768) ve mesafe metriğiyle (Cosine) oluşturuluyor mu
   - Aynı chunk iki kez upsert edilirse point sayısı artmıyor mu (idempotency)
   - Payload alanları (`doc_id`, `page_number`, ... `source_filename`) doğru
     yazılıyor mu
3. `tests/test_ingest_cli.py` — sahte (deterministic, gerçek ağa çıkmayan) bir
   embedding fonksiyonu enjekte edilerek, `:memory:` Qdrant ile CLI'ın orkestrasyon
   mantığı (`ingest_path`) test edilir: point sayısı == chunk sayısı, ikinci
   çalıştırmada duplicate yok.
4. `tests/test_ingest_e2e.py` — **gerçek** native Ollama + **gerçek**
   docker-compose Qdrant'a karşı, sample PDF ile uçtan uca: ingest et, point
   sayısı chunk sayısına eşit mi, aynı dosyayı tekrar ingest et, point sayısı
   değişmiyor mu. Bu servisler ayakta değilse test `pytest.mark.skipif` ile
   atlanır (CI/offline ortamda kırılmasın diye), ama local'de gerçek servislerle
   çalıştırılıp doğrulanacak.

## Adımlar

1. `requirements.txt`'e `qdrant-client` ekle, kur
2. Kırmızı testleri yaz (yukarıdaki 1-4)
3. `OllamaClient.embed()` implementasyonu
4. `app/ingestion/qdrant_store.py` implementasyonu
5. `app/ingestion/cli.py` implementasyonu
6. Testleri yeşile çevir
7. `ruff check` temiz
8. Gerçek bir örnek PDF klasörüyle CLI'ı manuel çalıştır: ingest et, Qdrant
   dashboard/API'den point sayısını kontrol et, tekrar ingest et, sayının
   değişmediğini doğrula
9. `docs/PLANNING.md` Sprint 2 kapanış notu — embedding boyutu (768), mesafe
   metriği (cosine), idempotency stratejisi (deterministic UUID) kesin karar
   olarak not düşülecek; task prefix gereksinimi de belgelenecek
10. Commit (AI co-author satırı yok)

## Definition of Done

- Bir klasördeki tüm PDF'ler tek komutla Qdrant'a yükleniyor
- Aynı dosyanın iki kez ingest edilmesi duplicate yaratmıyor
- Testler ve lint temiz
