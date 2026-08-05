# Production RAG Platform — Planlama Dokümanı

Ortam: M2 MacBook, 16GB RAM
Generation: Ollama (native, host'ta — Docker'da GPU/Metal passthrough olmadığı için)
Altyapı: Qdrant + Jaeger (Docker Compose), backend `host.docker.internal` ile Ollama'ya bağlanır

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

Her sprint: plan → test-first implementasyon → doğrulama → README güncelleme → kapanış notu.

## Sprint 0 — Foundation

Amaç: Boş bir iskeletten, tüm servislerin birbirine ulaştığı doğrulanmış bir temel çıkarmak.

Scope:

- Repo yapısı (`app/`, `docs/`, `docker-compose.yml`, `Makefile`)
- `docker-compose.yml`: Qdrant + Jaeger servisleri
- FastAPI iskeleti + `/health` endpoint
- Ollama native kurulum doğrulama (`ollama pull <model>`, `ollama pull nomic-embed-text`)
- Backend'in `host.docker.internal:11434` üzerinden Ollama'ya erişebildiğini doğrulayan basit bir smoke-test endpoint'i

Açık sorular (implementasyon sırasında karara bağlanacak):

- Hangi Ollama modeli generation için (3B mi 7B mi — ilk gerçek latency ölçümüne göre karar verilecek)
- Python paket yönetimi: uv mu pip+venv mi (ModelOps projesinde pip+venv kullanıldı, tutarlılık için aynısı düşünülebilir)

Definition of Done: `docker compose up` ile Qdrant+Jaeger ayağa kalkıyor, `/health` 200 dönüyor, backend'den Ollama'ya native bağlantı testi geçiyor.

### Kapanış Notu (2026-08-06)

Sprint 0 tamamlandı, DoD karşılandı:

- Repo iskeleti (`app/{api,ingestion,retrieval,reranker,llm,shared}`, `tests/`, `docs/`) oluşturuldu.
- Python: pip + venv, Python 3.12 (sistemdeki varsayılan `python3` 3.9.6 olduğu için Homebrew'daki
  `python3.12` kullanıldı — `pyproject.toml`'daki `requires-python = ">=3.11"` şartı için gerekli).
- Test-first: `tests/test_health.py` ve `tests/test_ollama_client.py` önce kırmızıya düşürüldü
  (import hatası ile), sonra `app/shared/config.py`, `app/llm/ollama_client.py`, `app/main.py`
  implementasyonuyla yeşile çevrildi. `OllamaClient` httpx `MockTransport` ile test ediliyor,
  gerçek ağ çağrısı yapmıyor.
- `docker-compose.yml`: sadece Qdrant (`v1.12.4`) + Jaeger (`1.63.0`, OTLP gRPC/HTTP + UI) —
  Ollama container'a konmadı, plana uygun şekilde native kaldı.
- Doğrulama: `make up` ile Qdrant+Jaeger ayağa kalktı, `curl /health` → 200, `curl /health/ollama`
  → gerçek native Ollama'ya bağlanıp `ollama list` ile birebir aynı model listesini döndü
  (`qwen2.5:3b-instruct`, `nomic-embed-text`, ortamda önceden yüklü `gemma2:2b`).

**Önemli bulgu — `host.docker.internal` local'de çözümlenmiyor:** Backend şu an Docker'da değil,
doğrudan host'ta (`make dev` ile) çalışıyor. `host.docker.internal` DNS adı sadece bir container
*içinden* çözümlenir; host'un kendisinden çözümlenmez. Bu yüzden local geliştirme için `.env`
içinde `OLLAMA_BASE_URL=http://localhost:11434` kullanıldı (gitignore'da, local'e özel).
`.env.example` ise ileride backend container'a alındığında (bkz. Sprint 10) doğru varsayılan olan
`host.docker.internal:11434`'ü koruyor. Backend container'a taşındığında bu iki değer arasında
gidip gelmemek için `OLLAMA_BASE_URL`'in ortam bazlı ayarlandığından emin olunmalı.

Açık sorular netleşti: generation modeli `qwen2.5:3b-instruct` olarak sabitlendi (kullanıcı
tarafından belirtildi), paket yönetimi pip+venv olarak teyit edildi.

Sıradaki: Sprint 1 — PDF Ingestion + Chunking.

## Sprint 1 — PDF Ingestion + Chunking

Amaç: PDF'lerden sayfa/paragraf metadata'sı korunarak temiz text chunk'ları çıkarmak.

Scope:

- PyMuPDF ile text + sayfa numarası extraction
- Paragraf sınırlarının korunması (citation'ın "sayfa/paragraf" seviyesinde olabilmesi için)
- Chunking stratejisi: sabit token boyutu + overlap (örn. 500 token / %10 overlap) — chunk sınırının bir cümleyi ortadan bölmemesine dikkat
- Her chunk için metadata: `{doc_id, page_number, paragraph_index, char_range, text}`

Açık sorular:

- Chunk boyutu nihai değil — Sprint 5 (reranking) ve Sprint 9 (evaluation) sonuçlarına göre revize edilebilir
- Taranmış (scanned/image-only) PDF desteği kapsam dışı mı tutulacak, yoksa OCR fallback eklenecek mi (v1'de kapsam dışı öneriliyor, ileri sprint'e bırakılabilir)

Definition of Done: Örnek bir PDF setinde her chunk doğru sayfa numarasına eşleniyor, birim testlerle doğrulanmış.

## Sprint 2 — Embedding + Qdrant Ingestion

Amaç: Chunk'ları embed edip Qdrant'a production-usulü bir şemayla yazmak.

Scope:

- Ollama `nomic-embed-text` ile embedding
- Qdrant collection şeması: dense vector (embedding boyutuna göre), payload (`doc_id`, `page_number`, `paragraph_index`, `text`, `source_filename`)
- Batch upsert ile ingestion CLI (`ingest --path ./docs`)
- Idempotency: aynı dosya tekrar ingest edilirse duplicate oluşmaması (örn. content-hash tabanlı point ID)

Açık sorular:

- Embedding boyutu ve mesafe metriği (cosine vs dot) — model dokümantasyonuna göre netleştirilecek
- Re-ingestion / güncelleme stratejisi (dosya değişirse eski chunk'lar nasıl temizlenecek)

Definition of Done: Bir klasördeki tüm PDF'ler tek komutla Qdrant'a yükleniyor, aynı dosyanın iki kez ingest edilmesi duplicate yaratmıyor.

## Sprint 3 — Hybrid Search (Native Qdrant)

Amaç: Dense + sparse vektörleri Qdrant içinde birleştirip tek bir hybrid retrieval sağlamak.

Scope:

- Sparse vector üretimi (FastEmbed SPLADE veya benzeri) ve collection'a ikinci bir named vector olarak eklenmesi
- Qdrant Query API ile dense+sparse fusion (RRF)
- Retrieval fonksiyonu: sorgu → top-k hybrid sonuç

Açık sorular:

- Sparse model seçimi gerçek chunk'larda test edilecek (SPLADE ağırsa, TF-IDF tabanlı basit bir alternatif de değerlendirilebilir)
- Fusion ağırlıkları (dense/sparse oranı) ilk gerçek sorgularla kalibre edilecek

Definition of Done: Aynı sorgu için hybrid sonuçların, sadece-dense sonuçlardan gözle görülür şekilde farklı/daha iyi olduğu somut örneklerle gösterilmiş.

## Sprint 4 — Metadata Filtering

Amaç: Hybrid search'e payload bazlı filtreleme eklemek (enterprise senaryosu: "sadece 2024 sonrası dokümanlarda ara" gibi).

Scope:

- Qdrant payload filtreleri: `doc_id`, `source_filename`, (varsa) tarih/tag alanları
- API katmanında filtre parametreleri (`filters: {doc_ids: [...], tags: [...]}`)
- Filtrelerin hybrid search sorgusuna doğru şekilde geçtiğinin testi

Açık sorular:

- Chunk metadata'sına tarih/tag gibi ek alanlar Sprint 1'de mi eklenmeliydi yoksa burada mı genişletilecek (muhtemelen burada, ingestion'a geriye dönük eklenecek)

Definition of Done: Filtreli ve filtresiz aynı sorgu farklı, doğru sonuç setleri döndürüyor.

## Sprint 5 — Cross-Encoder Reranking

Amaç: Hybrid search'ten gelen top-k adayları gerçek alaka düzeyine göre yeniden sıralamak.

Scope:

- `sentence-transformers` CrossEncoder (`ms-marco-MiniLM-L-6-v2`, CPU'da çalışır)
- Top-k (örn. 20) → rerank → top-n (örn. 5) daraltma
- Rerank öncesi/sonrası karşılaştırma: birkaç gerçek soru üzerinde manuel değerlendirme

Açık sorular:

- k ve n değerleri Sprint 9 (evaluation) sonuçlarına göre kesinleştirilecek

Definition of Done: Rerank sonrası top-n sonuçların, rerank öncesine göre daha alakalı olduğu somut örneklerle gösterilmiş.

## Sprint 6 — Grounded Generation + Streaming + Citations

Amaç: Reranked context'i kullanarak, sayfa/paragraf referanslı, streaming bir cevap üretmek.

Scope:

- Prompt: context chunk'ları + sayfa/paragraf bilgisiyle birlikte modele veriliyor, cevabın kaynak göstermesi isteniyor
- Ollama streaming API + FastAPI `StreamingResponse` (SSE)
- Grounding check: cevaptaki sayfa/paragraf referanslarının gerçekten context'te var olup olmadığının doğrulanması (basit bir post-hoc kontrol)
- Context'te cevap yoksa "dokümanda bulunamadı" davranışı

Açık sorular:

- Grounding check başarısız olursa (model olmayan bir sayfa uydurursa) kullanıcıya nasıl gösterilecek — cevabı reddetmek mi, uyarı eklemek mi

Definition of Done: Streaming cevap gerçek zamanlı akıyor, her cevap doğrulanmış sayfa/paragraf referansı içeriyor, context dışı sorularda uydurma yapmıyor.

## Sprint 7 — Prompt Versioning

Amaç: Prompt'ları kod değişikliği gerektirmeden versiyonlayıp, hangi versiyonun kullanıldığını izlenebilir kılmak.

Scope:

- `prompts/` klasörü altında versiyonlu template dosyaları (`answer_v1.txt`, `answer_v2.txt`)
- Aktif versiyon config/env üzerinden seçilebiliyor
- Her response'ta kullanılan prompt versiyonu loglanıyor / trace metadata'sına yazılıyor

Açık sorular:

- Versiyonlar arası A/B karşılaştırma Sprint 9'un (evaluation) bir parçası mı olacak, yoksa ayrı mı tutulacak (öneri: evaluation harness'ı versiyon parametreli çalıştırıp karşılaştırmak)

Definition of Done: Aktif prompt versiyonu tek bir config değişikliğiyle değiştirilebiliyor, her response'ta kullanılan versiyon net şekilde görülebiliyor.

## Sprint 8 — OpenTelemetry Tracing

Amaç: Pipeline'ın her adımını uçtan uca izlenebilir kılmak.

Scope:

- Parse → embed → retrieve → rerank → generate adımlarının her biri ayrı bir span
- Span attribute'ları: chunk sayısı, retrieval skorları, kullanılan prompt versiyonu, model adı, latency
- Jaeger'a export (docker-compose'daki Jaeger servisi)

Açık sorular:

- Yüksek kardinaliteli attribute'lar (örn. tam chunk text'i) span'e mi yazılacak yoksa sadece referans mı tutulacak (öneri: sadece referans/özet, tam text loglamak trace boyutunu şişirir)

Definition of Done: Jaeger UI'da tek bir sorgunun tüm pipeline'ı, adım adım latency'siyle birlikte waterfall görünümünde izlenebiliyor.

## Sprint 9 — Evaluation (RAGAS/DeepEval)

Amaç: Sistemin retrieval ve generation kalitesini nesnel metriklerle ölçmek.

Scope:

- Golden Q&A seti (soru + beklenen sayfa/paragraf + varsa referans cevap)
- RAGAS veya DeepEval ile: context precision/recall (retrieval tarafı), faithfulness/answer relevance (generation tarafı)
- Farklı k/n (Sprint 5) ve prompt versiyonu (Sprint 7) kombinasyonlarını karşılaştırma imkanı

Açık sorular:

- RAGAS mı DeepEval mi — ikisi de Ollama ile "judge model" olarak yerel model kullanılmasını destekliyor mu, yoksa judge için bir bulut modeli mi gerekecek (bu, gerçek kütüphane davranışı test edilerek netleştirilecek)

Definition of Done: Golden set üzerinde çalıştırılan bir komut, retrieval + generation metriklerini raporluyor; bu rapor deploy öncesi bir regression check olarak da kullanılabiliyor.

## Sprint 10 — Docker Compose Polish

Amaç: Tüm sistemin tek komutla ayağa kalkmasını sağlamak.

Scope:

- `docker compose up`: Qdrant + Jaeger + backend
- Ollama'nın native prerequisite olduğu README'de net şekilde belirtiliyor (kurulum adımlarıyla)
- Mimari diyagramı ve hızlı başlangıç rehberi README'ye ekleniyor

Definition of Done: Sıfırdan bir makinede (Ollama kurulu olmak kaydıyla) `docker compose up` + `make ingest` + bir örnek sorgu ile sistem uçtan uca çalışıyor.

## Sprint 11 — UI (stretch)

Amaç: Streaming cevap ve citation'ları gösteren basit bir arayüz.

Scope:

- Streamlit (ya da minimal bir Next.js sayfası) ile chat arayüzü
- Streaming token'ların gerçek zamanlı gösterimi
- Citation'lara tıklanınca ilgili sayfa/paragrafın vurgulanması

Definition of Done: PDF yükle → soru sor → streaming cevabı citation'larla birlikte gör, uçtan uca tarayıcıda doğrulanmış.
