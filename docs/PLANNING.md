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

### Kapanış Notu (2026-08-06)

Sprint 1 tamamlandı, DoD karşılandı:

- `app/ingestion/{models,parser,chunker}.py` eklendi. `parser.py` PyMuPDF (`fitz`)
  ile sayfa başına metin bloklarını (`page.get_text("blocks")`) paragraf sınırı
  olarak kabul edip sırayla `Paragraph(page_number, paragraph_index, text)`
  üretiyor. Text-layer'ı olmayan (taranmış/image-only) sayfalar hiç paragraf
  üretmeden sessizce atlanıyor — bilinçli kapsam dışı bırakma, testle
  (`test_page_with_no_text_layer_is_skipped`) doğrulandı.
- `chunker.py`: sayfa metnini paragraflardan birleştirip whitespace tabanlı bir
  "token" (kelime) sayacıyla chunk'lıyor, chunk sınırını en yakın cümle sonuna
  (`.`, `!`, `?`) kadar ileri itiyor ki cümle ortadan bölünmesin. Her chunk
  `{doc_id, page_number, paragraph_index, char_range, text}` şemasına uyuyor.
  `doc_id` = PDF dosya baytlarının SHA-256'sı (Sprint 2'deki idempotent
  ingestion'la tutarlı olacak).
- Test fixture'ı (`tests/conftest.py`) gerçek bir PDF'i PyMuPDF'in kendisiyle
  programatik üretiyor: 3 sayfa metinli (bazıları çok paragraflı, biri chunk
  bölünmesini tetikleyecek kadar uzun), 1 sayfa hiç text layer'ı olmayan
  (sadece çizilmiş bir dikdörtgen) — taranmış PDF senaryosunu simüle ediyor.
  Harici bir örnek PDF dosyası depoya commit'lenmedi; fixture testte anlık
  üretiliyor, böylece hem deterministik hem de repo boyutu şişmiyor.
- 16 test yeşil (13'ü bu sprint'te eklendi: `test_parser.py`, `test_chunker.py`),
  `ruff check` temiz. `test_chunk_document_maps_each_chunk_to_correct_page`
  testi, sayfa 1/2/3'teki her chunk'ın metninde o sayfaya özgü işaretleyicinin
  (`PAGE{n}-`) bulunduğunu doğrulayarak sayfa-chunk eşleşmesini garanti ediyor.

**Chunk boyutu kararı KESİN DEĞİL:** `DEFAULT_CHUNK_SIZE_TOKENS = 500` ve
`DEFAULT_OVERLAP_TOKENS = 50` (`app/ingestion/chunker.py`), plandaki gibi bir
başlangıç varsayımı olarak işaretlendi (kod içinde yorumla belirtildi). Ayrıca
"token" sayımı gerçek bir LLM tokenizer'ı değil, kaba bir whitespace-split
kelime sayacı — bu da geçici bir basitleştirme. Bu iki karar da **Sprint 5
(cross-encoder reranking sonuçları)** ve **Sprint 9 (RAGAS/DeepEval evaluation
metrikleri)** sonrasında gerçek verilerle revize edilecek; o zamana kadar
kesinleşmiş kabul edilmemeli.

Taranmış/image-only PDF desteği (OCR fallback) bu sprint'te olduğu gibi kapsam
dışı kalmaya devam ediyor; ileride ayrı bir sprint/görev olarak ele alınabilir.

Sıradaki: Sprint 2 — Embedding + Qdrant Ingestion.

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

### Kapanış Notu (2026-08-06)

Sprint 2 tamamlandı, DoD karşılandı. Açık sorular **kesin karara bağlandı**:

- **Embedding boyutu: 768** — varsayılmadı, gerçek bir `curl
  /api/embeddings` çağrısıyla ölçüldü ve `/api/tags`'daki
  `embedding_length: 768` alanıyla teyit edildi
  (`app/ingestion/qdrant_store.py:EMBEDDING_DIM`).
- **Mesafe metriği: Cosine** — Nomic'in HuggingFace model kartı embedding'lerin
  L2-normalize edilip cosine similarity ile karşılaştırılmasını öngörüyor;
  Qdrant collection'ı `Distance.COSINE` ile oluşturuluyor.
- **Beklenmeyen bulgu — task prefix zorunluluğu**: Planda yoktu, araştırma
  sırasında ortaya çıktı. `nomic-embed-text`, embed edilecek metnin bir görev
  prefix'i (`"search_document: "` ingestion için, `"search_query: "` sorgu
  için) içermesini *şart koşuyor* — yoksa embedding kalitesi düşük kalıyor.
  Bu sprint'te `"search_document: "` prefix'i uygulandı
  (`app/ingestion/ingest.py:SEARCH_DOCUMENT_PREFIX`); sorgu tarafı Sprint 3'te
  hybrid search implementasyonuna eklenecek — **Sprint 3 başlarken bu
  hatırlanmalı**, aksi halde dense tarafın retrieval kalitesi düşük çıkar.
- **Idempotency stratejisi**: content-hash tabanlı `doc_id` (SHA-256, Sprint
  1'den) + chunk alanlarından (`doc_id, page_number, paragraph_index,
  char_range`) türetilen deterministic `uuid5` point ID
  (`QdrantStore.point_id_for`). Aynı dosya tekrar ingest edildiğinde parser
  deterministic olduğu için aynı point ID'ler üretilir, Qdrant upsert
  üzerine yazar — duplicate oluşmaz. **Bilinen sınırlama**: içerik birebir
  aynı olan iki farklı dosya adı aynı `doc_id`'yi (ve dolayısıyla aynı point
  ID'leri) üretir; ikinci dosyanın `source_filename` payload'ı öncekinin
  üzerine yazılır. Bu, içerik-adresli bir dedup olarak kabul edildi, hata
  değil — ama ileride birden fazla dosya adının aynı içeriğe işaret ettiği
  senaryo netleştirilmek istenirse burası revize edilmeli.

Doğrulama: gerçek native Ollama + gerçek docker-compose Qdrant'a karşı hem
otomatik bir testle (`tests/test_ingest_e2e.py`, servisler kapalıyken
otomatik atlanıyor) hem de `make ingest PATH_ARG=...` ile manuel olarak — bir
örnek PDF ingest edildi, Qdrant'taki point sayısı chunk sayısıyla birebir
eşleşti, aynı klasör tekrar ingest edildiğinde point sayısı değişmedi. Payload
şeması (`doc_id, page_number, paragraph_index, char_range, text,
source_filename`) `curl` ile manuel doğrulandı.

28 test yeşil (bu sprint'te 12 yeni test eklendi:
`test_ollama_client.py::test_embed_*`, `test_qdrant_store.py`,
`test_ingest.py`, `test_ingest_e2e.py`), `ruff check` temiz.

Sıradaki: Sprint 3 — Hybrid Search (Native Qdrant). Sorgu tarafında
`"search_query: "` prefix'ini uygulamayı unutma.

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

### Kapanış Notu (2026-08-06)

Sprint 3 tamamlandı, DoD karşılandı. Açık sorular karara bağlandı:

- **Sparse model seçimi: `Qdrant/bm25` (FastEmbed), SPLADE değil.** M2 CPU'da
  gerçek chunk boyutunda ölçüldü: SPLADE++ (`prithivida/Splade_PP_en_v1`)
  ~134ms/chunk, `Qdrant/bm25` ~0.1ms/chunk — 1000x'ten fazla fark, 1000
  chunk'lık bir ingestion'da SPLADE +2 dakikadan fazla ekliyor. Bu "gözle
  görülür ve kabul edilemez" eşiğini net şekilde aşıyor, planın öngördüğü
  gibi TF-IDF/BM25 tabanlı alternatife geçildi. `Qdrant/bm25` ayrıca Qdrant'ın
  native `modifier="idf"` sparse index özelliğiyle özel tasarlanmış — IDF
  hesaplaması Qdrant tarafında, corpus'u client'ta fit etmeye gerek yok
  (`fastembed/sparse/bm25.py` kaynağı incelenerek doğrulandı).
- **Fusion**: Qdrant Query API'nin native `FusionQuery(fusion=Fusion.RRF)`'i,
  dense ve sparse'tan `prefetch_limit=20` ile ayrı top-20 aday çekip RRF ile
  birleştiriyor. Ayrı bir ağırlıklandırma (dense/sparse oranı) parametresi
  **eklenmedi** — RRF zaten skor ölçeğinden bağımsız, rank-tabanlı bir
  yöntem; ileride gerçek kullanıcı sorgularıyla kalibrasyon gerekirse
  Qdrant'ın `Prefetch` limitleri veya `Fusion.DBSF` gibi alternatifler
  değerlendirilebilir.
- **Query prefix**: Sprint 2'nin bıraktığı uyarı uygulandı —
  `app/retrieval/search.py:SEARCH_QUERY_PREFIX = "search_query: "` artık
  dense query embedding'ine ekleniyor; ingestion tarafı (`"search_document:
  "`) değişmedi.
- **Migration**: Qdrant var olan bir collection'a sonradan named vector
  ekleyemiyor. `QdrantStore.ensure_collection()` bu yüzden sparse vector'ü
  eksik bir collection'ı **drop edip yeniden oluşturuyor** — dev ortamı için
  kabul edilebilir (koleksiyon boştu), ama gerçek veri olan bir prod
  ortamında bu aynı şekilde uygulanmamalı; orada scroll+reindex+alias-swap
  gerekir. Bu, kod içinde yorumla da belirtildi.

**Beklenmeyen bulgu 1 — `qdrant-client`'ın `:memory:` modunda bug**: Sparse
vector + `modifier=IDF` olan tamamen boş bir collection'a karşı
`query_points` çağrısı local (in-memory) modda `KeyError: 'sparse'`
fırlatıyor (`local_collection.py:_rescore_idf`). Gerçek Qdrant sunucusuna
karşı aynı senaryo sorunsuz boş sonuç döndürüyor — doğrulandı. Bu sadece
local test modunun bir kısıtlaması; testler en az bir point upsert edildikten
sonra sorgu yaparak bu bug'ı bypass ediyor (`tests/test_search.py`'de
yorumla belgelendi).

**Beklenmeyen bulgu 2 — nomic-embed-text, exact-match sorgularında beklenenden
çok daha sağlam**: DoD'nin istediği "hybrid'in bulduğu ama dense'in kaçırdığı
somut bir örnek"i gerçek embeddinglerle üretmeye çalışırken, 14 farklı
adversarial senaryo denendi (nadir kodlar, birbirine çok yakın ID'ler —
REF-99182 vs REF-99183 gibi —, kısa/bağlamsız sorgular, uydurma teknik
jargon, gerçekçi PDF gürültüsü eklenmiş chunk'lar). **Hiçbirinde dense-only
yanlış chunk'ı üste çıkarmadı** — `nomic-embed-text` alt-kelime (subword)
tokenizasyonu sayesinde nadir/tam eşleşen terimleri bekleneden çok daha
sağlam yakalıyor. Yakın-ID senaryosunda skor farkı daralıyor (0.7395 vs
0.6942) ama sıralama bozulmuyor. Bu, "dense embedding'ler exact-match'te
zayıftır" genel varsayımının bu model için doğrulanmadığı, ileride fusion
ağırlıklarını ayarlarken hatırlanması gereken değerli bir bulgu.
Somut kanıt: `scripts/demo_hybrid_vs_dense.py` — Part 1 gerçek embeddinglerle
bu dürüst sonucu raporluyor; Part 2 (ve `tests/test_hybrid_search.py`)
kontrollü/deterministic vektörlerle fusion mekanizmasının kendisini
kanıtlıyor: sorguya ortogonal dense vektörü olan ama nadir bir anahtar
kelimeyi paylaşan bir chunk, dense-only'de son sırada (`score=0.0`) kalırken,
hybrid'de ilk sıraya çıkıyor (`score=0.83`) — DoD'nin istediği somut örnek.

40 test yeşil (12 yeni: `test_sparse.py`, `test_hybrid_search.py`,
`test_search.py`, `test_qdrant_store.py`/`test_ingest.py`'a sparse
eklentileri), `ruff check` temiz.

Sıradaki: Sprint 4 — Metadata Filtering.

## Sprint 4 — Metadata Filtering

Amaç: Hybrid search'e payload bazlı filtreleme eklemek (enterprise senaryosu: "sadece 2024 sonrası dokümanlarda ara" gibi).

Scope:

- Qdrant payload filtreleri: `doc_id`, `source_filename`, (varsa) tarih/tag alanları
- API katmanında filtre parametreleri (`filters: {doc_ids: [...], tags: [...]}`)
- Filtrelerin hybrid search sorgusuna doğru şekilde geçtiğinin testi

Açık sorular:

- Chunk metadata'sına tarih/tag gibi ek alanlar Sprint 1'de mi eklenmeliydi yoksa burada mı genişletilecek (muhtemelen burada, ingestion'a geriye dönük eklenecek)

Definition of Done: Filtreli ve filtresiz aynı sorgu farklı, doğru sonuç setleri döndürüyor.

### Kapanış Notu (2026-08-06)

Sprint 4 tamamlandı, DoD karşılandı. Açık soru karara bağlandı:

- **Filtrelenebilir alanlar: `doc_id`, `source_filename`, `page_number`** —
  hepsi Sprint 1-3'ten beri payload'da zaten var, **yeni bir ingestion alanı
  eklenmedi**. `app/retrieval/filters.py:build_filter()` bu üç alanı kabul
  ediyor (her biri opsiyonel liste, AND ile birleşiyor, alan içi değerler
  OR/`MatchAny`).
- **Tarih/tag alanları bilinçli olarak kapsam dışı bırakıldı** — bugün
  ingestion'da böyle bir alan yok ve otomatik çıkarımı (dosya sistemi tarihi
  mi, PDF metadata'sı mı, manuel etiketleme mi) ayrı bir tasarım kararı
  gerektiriyor. **İleride ayrı bir mini-sprint olarak ele alınmalı**: ingestion'a
  geriye dönük tarih/tag alanı + payload index'i + filtre desteği eklemek.

**Beklenmeyen bulgu — filtre+fusion etkileşimi gerçek sunucuda doğru, ama
`:memory:` local test modunda YANLIŞ**: Planın istediği gibi varsayılmadı,
gerçek Qdrant'a karşı test edildi. Bulgular:

1. **Gerçek sunucuda top-level `query_filter`, `prefetch` aşamasına da
   uygulanıyor** (fusion'dan önce, aday havuzu daraltılırken) — extreme bir
   stres testinde (`prefetch_limit=1`, filtrelenen dokümanın 50 kat daha
   yüksek skorlu rakibi varken) bile doğru sonucu buluyor. Bu yüzden filtreyi
   her `Prefetch`'e ayrı ayrı geçirmeye gerek yok, tek bir top-level
   `query_filter` yeterli (`app/retrieval/hybrid_search.py`).
2. **`qdrant-client`'ın `:memory:` (local) modu bu davranışı DOĞRU
   YANSITMIYOR** — aynı senaryo `:memory:`'de çalıştırıldığında, `query_filter`
   fusion sorgularında (prefetch+`FusionQuery`) tamamen görmezden geliniyor;
   filtrelenmiş olması gereken point yine sonuçlarda çıkıyor. Düz (fusion'suz)
   filtreli bir sorguda `:memory:` doğru çalışıyor — sorun özellikle
   prefetch+fusion kombinasyonunda. **Sonuç**: filtre+fusion davranışını
   doğrulayan hiçbir test `:memory:` ile yazılamaz, gerçek bir Qdrant sunucusu
   şart (`tests/test_filters_e2e.py`, servis kapalıyken atlanıyor). Bu, Sprint
   3'te bulunan `:memory:` modundaki boş-collection/sparse-IDF `KeyError`
   bug'ından sonra bu projede tespit edilen **ikinci** local-mode/gerçek-sunucu
   davranış farkı — `:memory:`'nin hız için kullanışlı ama fusion+filter gibi
   daha yeni/karmaşık Query API özelliklerinde güvenilir bir sunucu vekili
   olmadığı netleşti.

Somut kanıt (`tests/test_filters_e2e.py`, gerçek Qdrant'a karşı): `doc_id`
filtresi olmadan hybrid search, sparse eşleşmesi sayesinde `target-doc`'u
buluyor; `doc_ids=["other-doc"]` filtresiyle aynı sorgu **sadece** `other-doc`
sonuçlarını döndürüyor — `target-doc` filtre nedeniyle tamamen dışlanıyor.
İki sonuç kümesi farklı ve doğru.

46 test yeşil (5 yeni: `test_filters.py`, `test_filters_e2e.py`, ve
`test_search.py`'a filtre wiring testi), `ruff check` temiz.

Sıradaki: Sprint 5 — Cross-Encoder Reranking.

## Sprint 5 — Cross-Encoder Reranking

Amaç: Hybrid search'ten gelen top-k adayları gerçek alaka düzeyine göre yeniden sıralamak.

Scope:

- `sentence-transformers` CrossEncoder (`ms-marco-MiniLM-L-6-v2`, CPU'da çalışır)
- Top-k (örn. 20) → rerank → top-n (örn. 5) daraltma
- Rerank öncesi/sonrası karşılaştırma: birkaç gerçek soru üzerinde manuel değerlendirme

Açık sorular:

- k ve n değerleri Sprint 9 (evaluation) sonuçlarına göre kesinleştirilecek

Definition of Done: Rerank sonrası top-n sonuçların, rerank öncesine göre daha alakalı olduğu somut örneklerle gösterilmiş.

### Kapanış Notu (2026-08-06)

Sprint 5 tamamlandı, DoD karşılandı.

- **Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2` — planda önerilen model
  aynen kullanıldı, alternatif aramaya gerek kalmadı.
- **Gerçek latency ölçümü (varsayılmadı)**: M2 CPU'da, gerçek chunk boyutunda
  top-20 aday skorlandı. Model yükleme ~9s (process başına bir kerelik,
  cache'den), skorlama ısındıktan sonra top-20 için **~60ms** (2.8ms/çift).
  Sprint 3'teki SPLADE deneyiminin (~134ms/chunk, kabul edilemez) aksine, bu
  sefer eklenen gecikme kullanıcı sorgusu başına kabul edilebilir düzeyde —
  alternatif bir modele geçmeye gerek yok.
- **k=20, n=5 — HÂLÂ GEÇİCİ**: `app/retrieval/search.py:RERANK_CANDIDATE_K=20`,
  `RERANK_TOP_N=5`. Sprint 1'in chunk boyutu kararı gibi, bunlar da Sprint
  9'un (RAGAS/DeepEval evaluation) gerçek metriklerine göre kesinleşecek bir
  başlangıç varsayımı — kod içinde bu şekilde işaretlendi.
- **search.py entegrasyonu**: `reranker` parametresi opsiyonel — verilirse
  hybrid'in top-k'sı rerank edilip top-n'e daraltılıyor; verilmezse hybrid'in
  RRF sıralaması ilk `top_n` ile kesiliyor. Bu, Sprint 9'da rerank'li/rerank'siz
  A/B karşılaştırmasını kolaylaştırmak için bilinçli bir tasarım.

**Somut kanıt (`scripts/demo_rerank.py`, gerçek Ollama + gerçek Qdrant + gerçek
CrossEncoder)**: Sorgu "What is the return policy for a defective product?".
Bir chunk yalnızca ürün özelliklerini "product" kelimesini 6 kez tekrarlayarak
listeliyor (alakasız); diğeri gerçek iade politikasını anlatıyor (alakalı,
ama "product" kelimesini hiç geçmiyor). Hybrid (RRF) fusion, BM25'in kelime
tekrarına aşırı ağırlık vermesi yüzünden **alakasız chunk'ı top-1 yapıyor**
(`score=0.8333`, alakalı chunk `score=0.5000` ile 2.). CrossEncoder rerank
bunu tersine çeviriyor: alakalı chunk `score=0.4055` (pozitif, alakalı) ile
1., alakasız chunk `score=-11.0160` (çok negatif, alakasız) ile 2. sıraya
düşüyor. Bu, iddia değil, gerçek ölçülmüş bir skor farkı — ve ayrıca RRF
fusion'ın kelime-tekrarı gibi basit bir saldırıya (keyword stuffing) karşı
savunmasız olduğunu, rerank adımının bunun için tam olarak gerekli olduğunu
somut olarak gösteriyor.

52 test yeşil (6 yeni: `test_reranker.py`, `test_search.py`'a rerank
entegrasyon testleri), `ruff check` temiz.

Sıradaki: Sprint 6 — Grounded Generation + Streaming + Citations.

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

### Kapanış Notu (2026-08-06)

Sprint 6 tamamlandı, DoD karşılandı. Açık soru karara bağlandı:

- **Grounding check başarısız olursa — KARAR: cevap reddedilmiyor, uyarı
  olarak işaretleniyor.** Gerekçe: kontrol post-hoc (planın kendisinde de
  böyle tanımlı) — citation'lar cevabın *içinde*, dolayısıyla generation
  tamamlanmadan kontrol edilemez; o noktada token'lar zaten kullanıcıya
  stream edilmiş oluyor. "Reddetmek" ancak yeniden üretim (regenerate)
  gerektirir, bu sprint'in kapsamında yok. Bunun yerine stream'in sonunda
  ayrı bir SSE event'i (`event: grounding`) ile `{grounded, citations_found,
  ungrounded_citations}` gönderiliyor — istemci bunu bir uyarı olarak
  gösterebilir. Regenerate-on-failure ileride ayrı bir mini-sprint olarak
  değerlendirilebilir.
- **Prompt versiyonu**: tek bir sabit `SYSTEM_PROMPT_V1`
  (`app/llm/prompt.py`) — Sprint 7'de dosya-tabanlı versiyonlamaya taşınacak.

**Beklenmeyen bulgu — ilk prompt taslağı citation formatını takip ettirmedi**:
İlk yazılan prompt ("every claim must be followed by [s.page/paragraph]")
gerçek `qwen2.5:3b-instruct` ile test edildiğinde model context etiketini
(`[Kaynak: Sayfa 2, Paragraf 0]`) olduğu gibi (hatta yanlış yazarak,
"Kayfan") kopyaladı — istenen kısa `[s.2/0]` formatını hiç kullanmadı,
`check_grounding` da citation bulamadı (`citations_found=[]`). Gerçek model
çıktısıyla test edilmeseydi bu sessizce geçerdi (grounding "boş citation =
grounded" kuralı yüzünden yanlışlıkla "başarılı" görünürdü). Prompt, açık
bir örnek (`"[Kaynak: Sayfa 3, Paragraf 0]" için [s.3/0] yaz`) ve "Kaynak/
Sayfa/Paragraf kelimelerini kullanma" talimatıyla güçlendirildi — 3 farklı
gerçek senaryoda (tek chunk, çoklu chunk, context-dışı soru) tutarlı şekilde
doğru format ve doğru "bulunamadı" davranışı üretti. Bu, 3B gibi küçük bir
modelin format talimatlarını gerçek veriyle doğrulamadan güvenilir
sayılamayacağının somut bir kanıtı.

**Somut kanıt**:
- Streaming: `tests/test_generation_e2e.py` gerçek Ollama'ya karşı, token
  varış zamanlarını ölçüp aralarında >50ms fark olduğunu doğruluyor —
  tamamı aynı anda gelen "sahte stream" değil, gerçek token-token akış.
  `curl -N /chat` ile manuel doğrulandı, SSE `data:` satırları tek tek geldi.
- Grounding: context'te sadece (sayfa 2, paragraf 0) varken cevapta
  kasıtlı olarak `[s.99/0]` (uydurma) geçirilen test, `grounded=False` ve
  `ungrounded_citations=[(99,0)]` ile başarısız olarak yakalandı
  (`tests/test_grounding.py`).
- Context dışı soru ("What is the capital of France?", context iade
  politikasıyla ilgili): model gerçek Ollama ile tam olarak
  `"I could not find this in the document."` cevabını verdi — uydurma
  yapmadı, hem otomatik testte hem `curl` ile manuel doğrulandı.

69 test yeşil (14 yeni: `test_prompt.py`, `test_grounding.py`,
`test_ollama_client.py`'a stream_chat testleri, `test_generate.py`,
`test_generation_e2e.py`), `ruff check` temiz.

Sıradaki: Sprint 7 — Prompt Versioning.

## Sprint 7 — Prompt Versioning

Amaç: Prompt'ları kod değişikliği gerektirmeden versiyonlayıp, hangi versiyonun kullanıldığını izlenebilir kılmak.

Scope:

- `prompts/` klasörü altında versiyonlu template dosyaları (`answer_v1.txt`, `answer_v2.txt`)
- Aktif versiyon config/env üzerinden seçilebiliyor
- Her response'ta kullanılan prompt versiyonu loglanıyor / trace metadata'sına yazılıyor

Açık sorular:

- Versiyonlar arası A/B karşılaştırma Sprint 9'un (evaluation) bir parçası mı olacak, yoksa ayrı mı tutulacak (öneri: evaluation harness'ı versiyon parametreli çalıştırıp karşılaştırmak)

Definition of Done: Aktif prompt versiyonu tek bir config değişikliğiyle değiştirilebiliyor, her response'ta kullanılan versiyon net şekilde görülebiliyor.

### Kapanış Notu (2026-08-06)

Sprint 7 tamamlandı, DoD karşılandı. Açık soru karara bağlandı:

- **Sprint 9 A/B karşılaştırması bunu nasıl kullanacak**: `search()`/
  `stream_answer()` versiyonu **parametre olarak** aldığı için (config'i
  kendi içinde okumuyor), Sprint 9'un evaluation harness'ı aynı golden
  soru setini `prompt_version="v1"` ve `prompt_version="v2"` ile art arda
  çalıştırıp RAGAS/DeepEval metriklerini yan yana karşılaştırabilecek —
  kod değişikliği ya da ayrı bir "A/B modu" gerekmiyor, sadece parametreyi
  değiştirmek yeterli. Ayrı bir A/B altyapısı kurulmadı, çünkü mevcut
  tasarım zaten bunu destekliyor.
- **Versiyon seçimi nerede**: `app/shared/config.py:active_prompt_version`
  (env: `ACTIVE_PROMPT_VERSION`) — sadece `app/api/chat.py`'de okunuyor,
  `build_messages`/`stream_answer` saf fonksiyonlar olarak kalıyor (config'e
  gizli bağımlılıkları yok, test edilmesi kolay).
- **Versiyonun görünürlüğü**: stream'in **ilk** event'i olarak
  `{"type": "metadata", "prompt_version": "..."}` gönderiliyor (token'lardan
  önce) — grounding event'inin sonuna eklemek yerine bu tercih edildi çünkü
  istemci hangi versiyonun cevap verdiğini stream bitmeden bilebiliyor, ve
  generation ortada hata verip kesilse bile versiyon bilgisi zaten gönderilmiş
  oluyor.

**Taşıma doğrulandı**: Sprint 6'da gerçek modelle sabitlenmiş prompt
(`CITATION RULE`, açık örnek, "Kaynak/Sayfa/Paragraf kelimelerini kullanma"
talimatı) `prompts/answer_v1.txt`'e birebir taşındı —
`test_load_system_prompt_v1_preserves_sprint6_fixes` bunu garanti ediyor.
Sprint 6'nın tüm testleri (`test_generation_e2e.py` dahil, gerçek Ollama'ya
karşı) refactor sonrası hiç değişiklik yapılmadan (sadece `prompt_version`
parametresi eklenerek) geçmeye devam etti — regresyon yok.

**Somut kanıt (`scripts/demo_prompt_versions.py` ve ek bir prob script'i,
gerçek Ollama'ya karşı)**: Aynı soru + aynı context'e v1 ve v2 ile ayrı ayrı
cevap üretildi. Tek-chunk'lı basit soruda ikisi de doğru `[s.PAGE/PARAGRAPH]`
formatını kullandı ama **farklı davrandı**: v1 citation'ı cümleden önce
koydu, context'i neredeyse birebir yansıttı; v2 citation'ı cümleden sonra
koydu, kendi cümleleriyle parafraz etti — metadata event'i de doğru şekilde
`prompt_version` farkını yansıttı. Daha zorlu, çok chunk'lı bir soruda
(printer troubleshooting, 2 chunk) **beklenmedik ama dürüst bir bulgu**: v1
iki denemeden birinde tutarsız bir çıktı üretti — soruya cevap context'te
açıkça varken "I could not find this in the document. [s.4/2]" dedi (hem
yanlış "bulunamadı" hem de gereksiz bir citation, kendi kuralıyla çelişen bir
çıktı), v2 ise iki denemede de tutarlı ve doğru, tam grounded cevaplar verdi.
Bu, "v1 daha detaylı olduğu için her zaman daha güvenilir" varsayımının
genellenemeyeceğini gösteren gerçek, ölçülmüş bir fark — versiyonlar arası
davranış gerçekten farklı, iddia değil.

77 test yeşil (13 yeni/değişen: `test_config.py`, `test_prompt.py`'a
versiyon testleri, `test_generate.py`'a metadata event testi), `ruff check`
temiz.

Sıradaki: Sprint 8 — OpenTelemetry Tracing.

## Sprint 8 — OpenTelemetry Tracing

Amaç: Pipeline'ın her adımını uçtan uca izlenebilir kılmak.

Scope:

- Parse → embed → retrieve → rerank → generate adımlarının her biri ayrı bir span
- Span attribute'ları: chunk sayısı, retrieval skorları, kullanılan prompt versiyonu, model adı, latency
- Jaeger'a export (docker-compose'daki Jaeger servisi)

Açık sorular:

- Yüksek kardinaliteli attribute'lar (örn. tam chunk text'i) span'e mi yazılacak yoksa sadece referans mı tutulacak (öneri: sadece referans/özet, tam text loglamak trace boyutunu şişirir)

Definition of Done: Jaeger UI'da tek bir sorgunun tüm pipeline'ı, adım adım latency'siyle birlikte waterfall görünümünde izlenebiliyor.

### Kapanış Notu (2026-08-06)

Sprint 8 tamamlandı, DoD karşılandı. Açık soru karara bağlandı:

- **Yüksek kardinaliteli attribute'lar span'e YAZILMIYOR** — hiçbir span'e
  tam chunk text'i, tam prompt içeriği veya tam cevap metni yazılmadı;
  sadece sayılar/referanslar (`chunk_count`, `token_count`,
  `citation_count`, `top_score`, `source_filename` gibi dosya adı referansı).
  Bunu iddia olarak bırakmadık: `test_stream_answer_generate_span_does_not_contain_full_answer_text`
  ve `test_ingest_path_spans_do_not_contain_chunk_text` testleri, gerçek
  chunk metninin (`"PAGE1-PARA0"` gibi) hiçbir span attribute'unda
  görünmediğini otomatik doğruluyor.

**Span'e konan attribute'lar**:
- `embed_query`: `embed.model`
- `retrieve_hybrid`: `retrieve.candidate_count`, `retrieve.top_k`,
  `retrieve.top_score` — **sadece fused RRF skoru**. Qdrant'ın gerçek
  `ScoredPoint` yanıtı incelendi (`dir()` ile alan listesi çıkarıldı):
  ayrı dense/sparse alt-skorları döndürülmüyor, sadece birleşik `score` var.
  Bunları almak isteseydik dense-only + sparse-only + fused olmak üzere 3
  ayrı sorgu gerekirdi — retrieval gecikmesini gözlemlenebilirlik uğruna 3
  katına çıkarmak yerine, sadece fused skoru kaydetmeye karar verildi.
- `rerank`: `rerank.top_n`, `rerank.top_score`
- `generate`: `generate.model`, `generate.prompt_version`,
  `generate.context_chunk_count`, `generate.token_count`, `generate.grounded`,
  `generate.citation_count`
- `chat_request` (kök span): `chat.question_char_count`
- `load_models`, `ingest_document`, `parse_and_chunk`, `embed_batch`,
  `upsert_batch`: chunk/dosya sayıları ve dosya adı referansı

**Streaming span'in ömrü — varsayılmadı, gerçek istekle doğrulandı**:
`generate` (ve kök `chat_request`) span'i, ilgili async generator'ın **tüm**
gövdesini (her `yield` dahil) sarıyor. Python'da bir context manager,
generator suspend/resume (yield) sırasında kapanmıyor — sadece generator
tükenince kapanıyor. Bunu gerçek bir `/chat` isteğiyle test ettik: Jaeger'dan
çekilen gerçek trace'te, warm (modeller zaten yüklü) bir istekte
`chat_request` kök span süresi (**1833.2ms**) ile çocuk span'lerin toplamı
(`embed_query 72.7 + retrieve_hybrid 7.2 + rerank 262.5 + generate 1489.8 =
1832.2ms`) neredeyse birebir eşleşti (fark: 1ms) — yani `generate` span'i
gerçekten stream'in tamamı bitene kadar açık kaldı, sadece ilk token'a kadar
değil. Eğer span erken kapansaydı, kapanıştan stream'in gerçek bitişine kadar
açıklanamayan bir boşluk olurdu.

**Beklenmeyen bulgu — ilk istekte ~9.6s'lik açıklanamayan boşluk**: İlk gerçek
`/chat` isteğinde kök span 11454.4ms sürdü ama çocuk span'lerin toplamı
sadece ~1824ms'ydi — aradaki ~9.6s, `CrossEncoderReranker`/`SparseEncoder`'ın
process başına bir kerelik lazy model yüklemesiydi (Sprint 5/6'da bilinen
~9s'lik maliyet), ama hiçbir span'e sarılmamıştı, yani waterfall'da
açıklanamayan bir boşluk olarak görünüyordu. Bu, sadece not düşülüp
geçilmedi — `app/api/chat.py`'e ayrı bir `load_models` span'i eklenerek
düzeltildi. Düzeltme sonrası aynı senaryoda kök span ile çocuk span'lerin
toplamı arasındaki fark **6.8ms**'ye indi (tamamen ihmal edilebilir,
span açma/kapama overhead'i kadar).

**Tracing overhead'i ölçüldü (varsayılmadı)**: İzole bir benchmark'ta
(5000 span oluştur/kapat döngüsü), OTel'in no-op tracer'ı ~0.68μs/span
sürerken, gerçek `BatchSpanProcessor` + OTLP exporter'lı tracer ~12.24μs/span
sürdü — span başına **~11.5μs** ek yük. Bir sorgu tipik olarak 5-6 span
üretiyor (`chat_request, load_models, embed_query, retrieve_hybrid, rerank,
generate`), yani toplam ek yük **~70 mikrosaniye** — saniyeler süren LLM
generation'ına kıyasla (%0.004) tamamen ihmal edilebilir. `BatchSpanProcessor`
export'u arka planda ayrı bir thread'de yaptığı için ana istek yolunu
bloklamıyor.

**Somut kanıt**: Gerçek bir `/chat` isteği sonrası Jaeger API'sinden
(`/api/traces/{trace_id}`) çekilen trace, tek bir `traceID` altında
`chat_request` → `load_models`, `embed_query`, `retrieve_hybrid`, `rerank`,
`generate` span'lerinin hepsini, doğru parent-child ilişkisiyle ve
latency'leriyle içeriyordu (bkz. yukarıdaki ölçümler).
`tests/test_tracing_e2e.py` bunu otomatik olarak da doğruluyor (gerçek
Ollama+Qdrant+Jaeger'a karşı, servisler kapalıyken atlanıyor): tek trace,
beklenen 5 span adı, hepsi kökün çocuğu, hiçbir span'de chunk text'i sızıntısı yok.

88 test yeşil (12 yeni: `test_tracing.py`, `search.py`/`generate.py`/
`ingest.py`'a span testleri, `test_tracing_e2e.py`), `ruff check` temiz.

Sıradaki: Sprint 9 — Evaluation (RAGAS/DeepEval).

## Sprint 9 — Evaluation (RAGAS/DeepEval)

Amaç: Sistemin retrieval ve generation kalitesini nesnel metriklerle ölçmek.

Scope:

- Golden Q&A seti (soru + beklenen sayfa/paragraf + varsa referans cevap)
- RAGAS veya DeepEval ile: context precision/recall (retrieval tarafı), faithfulness/answer relevance (generation tarafı)
- Farklı k/n (Sprint 5) ve prompt versiyonu (Sprint 7) kombinasyonlarını karşılaştırma imkanı

Açık sorular:

- RAGAS mı DeepEval mi — ikisi de Ollama ile "judge model" olarak yerel model kullanılmasını destekliyor mu, yoksa judge için bir bulut modeli mi gerekecek (bu, gerçek kütüphane davranışı test edilerek netleştirilecek)

Definition of Done: Golden set üzerinde çalıştırılan bir komut, retrieval + generation metriklerini raporluyor; bu rapor deploy öncesi bir regression check olarak da kullanılabiliyor.

### Kapanış Notu (2026-08-06)

Sprint 9 tamamlandı, DoD karşılandı. Açık soru çözüldü:

- **RAGAS: kullanılamaz durumda, koddan/tasarımdan değil bağımlılık
  çakışmasından.** Hem güncel (`0.4.3`) hem eski (`0.2.15`) sürüm denendi,
  ikisi de `ragas`'ın koşulsuz import ettiği
  `langchain_community.chat_models.vertexai`'ın güncel `langchain-community`
  (`0.4.2`)'de artık var olmamasından ötürü import aşamasında patladı.
  `langchain-google-vertexai` kurmak, `langchain-community`'yi eski sürüme
  çekmek gibi çözümler denendi; hepsi ya aynı hatayı verdi ya da
  `langchain-core`/`langgraph`/`langchain-openai` zincirinde çözülemeyen
  yeni çakışmalar açtı (`ContextOverflowError` import hatası). **Karar:
  RAGAS bu ortamda hiç kullanılmıyor.**
- **DeepEval: çalışıyor ama 3B judge güvenilmez, 7B judge güvenilir —
  gerçekten ölçüldü.** `qwen2.5:3b-instruct` judge olarak
  `FaithfulnessMetric`'i **0.0** skorladı ama sentezlenen gerekçe "hiç
  çelişki yok" diyordu — `verbose_mode` ile bakıldığında model claim için
  `verdict: "no"` üretmiş ama `reason: null` bırakmıştı (kendi şemasını
  tutarlı dolduramamış). Aynı test case, sadece judge modeli
  `qwen2.5:7b-instruct` (4.7GB, RAM/disk kontrol edilip indirildi) olarak
  değiştirilince **1.0** ve tutarlı bir gerekçe verdi. **Karar: DeepEval +
  `qwen2.5:7b-instruct` (sadece judge — RAG'ın kendi generation modeli
  3B'de kalıyor, hız için).**
- **Retrieval metrikleri judge gerektirmiyor**: golden set'teki kesin
  `(page, paragraph)` referanslarıyla precision/recall deterministik
  hesaplanıyor (`app/evaluation/retrieval_metrics.py`) — LLM'in kendi hata
  payı devreye girmiyor.

**Golden set**: `tests/fixtures/golden_source.py` gerçek bir kaynak PDF
üretiyor (kurgusal ama iç tutarlı "Nimbus Cloud Storage" destek kılavuzu,
6 sayfa × 2 paragraf), gerçek parser ile test edilip sayfa/paragraf
eşleşmesi doğrulandı. `tests/fixtures/golden_qa.json`: 20 soru (16 tek-chunk,
2 çok-chunk sentez, 2 context-dışı).

**Gerçek karşılaştırmalar (Sprint 1/5/7'nin geçici kararları):**

1. **Prompt v1 vs v2 (Sprint 7) — KESİNLEŞTİ.** 7 soruluk temsili bir alt
   kümede (`golden_qa_smoke.json`: tek-chunk + çok-chunk + context-dışı
   karışımı), gerçek 7B judge ile: v1 `faithfulness=0.70, answer_relevancy=
   0.80, not_found_accuracy=1.0`; v2 `faithfulness=0.75, answer_relevancy=
   0.70, not_found_accuracy=0.5`. Faithfulness'ta ikisi de yakın (7 soruluk
   örneklemde gürültü payı içinde), ama **en kritik metrik olan
   `not_found_accuracy`'de v1 kesin üstün** (2/2'ye karşı 1/2 — v2 bir
   context-dışı soruda halüsinasyon yaptı, Sprint 6'nın temel "uydurma
   yapma" hedefiyle doğrudan çelişen bir hata). **Karar: v1, aktif varsayılan
   olarak KALIYOR** (`app/shared/config.py:active_prompt_version="v1"` zaten
   buydu — bu sprint bunu iddia olmaktan çıkarıp veriyle doğrulanmış bir
   karara çevirdi).
2. **k/n (Sprint 5) — gerçek veriyle bilgilendirildi, kod değiştirilmedi.**
   `top_k=20/top_n=5` (mevcut varsayılan) ile `top_k=10/top_n=3`
   karşılaştırıldı: precision `0.122 → 0.204` (iyileşme), recall aynı
   kaldı (`0.556`). Yani daha küçük `n`, recall kaybı olmadan precision'ı
   artırıyor. **Kod değiştirilmedi** — bu sonuç 6 sayfalık tek bir golden
   set'e dayanıyor, gerçek/çeşitli bir doküman korpusunda doğrulanmadan
   varsayılanı değiştirmek riskli; bulgu gelecekteki bir ayarlama için not
   düşüldü.
3. **Chunk boyutu (Sprint 1) — corpus'a bağlı olduğu netleşti, tek bir sayı
   olarak kesinleşmedi.** `500/50` (mevcut) ile `100/10` **birebir aynı**
   sonucu verdi (`precision=0.122, recall=0.556`) — gerçek chunk sayıları
   kontrol edildiğinde ikisinin de sayfa başına tek chunk ürettiği görüldü
   (golden doküman paragrafları ~40-60 kelime, her ikisi de aynı chunk
   sınırını üretiyor). `40/5`'e (paragraf granülaritesi) düşürülünce
   precision `0.232`'ye (~2x), recall `0.861`'e çıktı — açık bir iyileşme,
   ama **golden dokümanın kısa paragraflarına özgü** bir sonuç; genel ilke
   (chunk boyutu içeriğin gerçek granülaritesine göre ayarlanmalı, sabit bir
   sayı evrensel değil) kesinleşti, ama varsayılan `500/50` kod değişikliği
   olmadan bırakıldı.

**Rapor formatı/aracı**: `scripts/run_evaluation.py` — golden source PDF'i
anlık üretip ingest ediyor, golden set'i (`--golden-set` ile override
edilebilir, `--limit` ile alt kümeye indirilebilir) çalıştırıp JSON rapor
üretiyor (`--output`). `--skip-generation-metrics` ile sadece retrieval
karşılaştırmaları hızlıca (~40s) çalıştırılabiliyor.

**Beklenmeyen, önemli bulgu #1 — model-swap tuzağı**: İlk tasarımda
`run_evaluation()` her soru için sırayla embed→generate (3B)→judge (7B)
yapıyordu. Gerçek bir koşum bunun 20 soru için 40+ dakika sürdüğünü
gösterdi (izole ölçümlerden beklenen ~11 dakikanın 4 katı) — Ollama her
seferinde 3B/7B arasında model değiştirmek zorunda kalıyordu. **Düzeltme**:
`run_evaluation()` artık iki ayrı faz çalıştırıyor — önce tüm sorular için
generation (tek model, swap yok), sonra tüm sorular için judge (tek model,
swap yok). Bu, model swap'ını tamamen ortadan kaldırdı.

**Beklenmeyen, önemli bulgu #2 — gerçek bir production bug bulundu ve
düzeltildi**: İki-fazlı düzeltmeden sonra bile küçük bir smoke koşumu
gerçek bir hatayla patladı: `httpx.ReadTimeout`,
`app/llm/ollama_client.py`'deki **sabit 10 saniyelik timeout**'tan
kaynaklanıyordu — 7B judge (ve yoğun yükte 3B generation) bazı çağrılarda
10 saniyeden uzun sürebiliyor. Bu, **Sprint 0'dan beri** kod tabanında olan
ve daha önce fark edilmemiş gerçek bir bug'dı; muhtemelen önceki "takılmış"
görünen 30+ dakikalık koşunun asıl nedeniydi (sessiz timeout+retry
döngüleri). **Düzeltme**: `DEFAULT_TIMEOUT_SECONDS=120.0`, `OllamaClient`
artık yapılandırılabilir bir `timeout` parametresi alıyor
(`tests/test_ollama_client.py`'a regresyon testleri eklendi). Bu düzeltme
sonrası, önceden kaynak çakışması/timeout yüzünden kararsız görünen 4 e2e
test (`test_generation_e2e.py` × 3, `test_tracing_e2e.py` × 1) tekrar
çalıştırıldı ve hepsi geçti — gerçek bir regresyon değil, gerçek bir bug
tespiti ve düzeltmesiydi.

108 test yeşil (14 yeni: `test_retrieval_metrics.py`,
`test_generation_metrics.py`, `test_harness.py`,
`test_ollama_client.py`'a timeout testleri), `ruff check` temiz.

Sıradaki: Sprint 10 — Docker Compose Polish.

## Sprint 10 — Docker Compose Polish

Amaç: Tüm sistemin tek komutla ayağa kalkmasını sağlamak.

Scope:

- `docker compose up`: Qdrant + Jaeger + backend
- Ollama'nın native prerequisite olduğu README'de net şekilde belirtiliyor (kurulum adımlarıyla)
- Mimari diyagramı ve hızlı başlangıç rehberi README'ye ekleniyor

Definition of Done: Sıfırdan bir makinede (Ollama kurulu olmak kaydıyla) `docker compose up` + `make ingest` + bir örnek sorgu ile sistem uçtan uca çalışıyor.

### Kapanış Notu (2026-08-06)

Sprint 10 tamamlandı, DoD karşılandı. Açık soru karara bağlandı:

- **Backend container'a girdi, Ollama native kaldı.** Planın orijinal scope
  satırı zaten "`docker compose up`: Qdrant + Jaeger + backend" diyordu — bu
  sprint bunu gerçekten uyguladı. Ollama'nın native kalma gerekçesi
  değişmedi (Sprint 0: Docker Desktop macOS'ta Metal GPU passthrough yok).
- **`make ingest` (CLI) container'a GİRMEDİ, host/venv'de kaldı.** Bilinçli
  bir kapsam kararı: ingestion host'taki PDF dosyalarını okuyan bir batch
  işi; container'a taşımak dosya mount'u gibi ek karmaşıklık gerektirirdi ve
  bu sprint'in asıl kanıtlaması gereken şey (serving path'inin container'dan
  native Ollama'ya gerçekten ulaşması) için gerekli değildi.

**Sprint 0'dan beri bekleyen varsayım gerçekten test edildi**: `.env.example`'daki
`OLLAMA_BASE_URL=http://host.docker.internal:11434` üç ayrı adımda doğrulandı,
hiçbiri varsayılmadı:
1. `docker compose exec backend curl http://host.docker.internal:11434/api/tags`
   — container'ın gerçekten native Ollama'ya ulaştığı, ham `curl` ile.
2. Backend'in kendi `/health/ollama` endpoint'i — `qwen2.5:7b-instruct,
   nomic-embed-text, qwen2.5:3b-instruct, gemma2:2b` tam model listesini döndü.
3. **Uçtan uca gerçek sorgu**: host'tan `make ingest` ile bir PDF yüklendi,
   container'daki backend'e gerçek bir `/chat` isteği atıldı — streaming
   cevap, doğru `[s.1/0]` citation'ıyla ve `grounded: true` ile döndü. Tüm
   pipeline (embed → retrieve → rerank → generate, container içinden native
   Ollama'ya) çalıştığı kanıtlandı.

**Sıfırdan kurulum gerçekten test edildi (varsayılmadı)**: `docker compose
down -v` (tüm container/volume/network silindi) sonrası `docker compose up -d`
ile sistem 8 saniyede tekrar `healthy` duruma geldi — `/health` ve
`/health/ollama` temiz durumda da 200 döndü.

**Beklenmeyen bulgu — gerçek bir bağımlılık drift'i yakalandı**: `docker
compose build` ilk denemede `pydantic-settings==2.7.1` (Sprint 0'dan beri
sabit) ile `deepeval==4.1.5`'in gerektirdiği `pydantic-settings>=2.10.1`
arasında **gerçek bir çakışma** verdi. Kontrol edildiğinde, yerel venv'de
zaten sessizce `2.14.2`'ye yükselmiş olduğu görüldü (Sprint 9'da `deepeval`
kurulurken pip otomatik çözmüştü) — ama `requirements.txt` hiç
güncellenmemişti. Bu, **container build'i temiz bir ortamda çalıştığı için**
yakalanabilen, host venv'de fark edilmeyen gerçek bir drift'ti.
`requirements.txt` düzeltildi (`pydantic-settings==2.14.2`), 108 test hâlâ
yeşil.

**Not**: Build sırasında bir kez de geçici bir ağ kaynaklı wheel hash
uyuşmazlığı (`torch`'un indirilmesi sırasında) yaşandı — retry ile
kendiliğinden düzeldi, kod/bağımlılık sorunu değildi.

**Diğer kararlar**:
- Cross-encoder/sparse-encoder modelleri için `hf_cache` adlı bir named
  volume eklendi — `docker compose down` + `up` her seferinde ~9s+'lik
  model indirmesini tekrarlamasın diye.
- Backend servisinin ortam değişkenleri `.env` dosyasından değil,
  `docker-compose.yml`'in kendi `environment:` bloğundan geliyor (container
  içi doğru servis adları — `qdrant`, `jaeger`, `host.docker.internal` —
  host'ta native çalıştırırken kullanılan `localhost` değerlerinden farklı
  olduğu için).
- `Dockerfile`: `python:3.12-slim` taban imaj, `/health` üzerinden Docker
  healthcheck.

Sıradaki: Sprint 11 — UI (stretch).

## Sprint 11 — UI (stretch)

Amaç: Streaming cevap ve citation'ları gösteren basit bir arayüz.

Scope:

- Streamlit (ya da minimal bir Next.js sayfası) ile chat arayüzü
- Streaming token'ların gerçek zamanlı gösterimi
- Citation'lara tıklanınca ilgili sayfa/paragrafın vurgulanması

Definition of Done: PDF yükle → soru sor → streaming cevabı citation'larla birlikte gör, uçtan uca tarayıcıda doğrulanmış.

### Kapanış notu

**Kapsam netleştirildi**: Gerçek kullanıcı talebi, PLANNING.md'deki taslak
scope'tan biraz farklıydı — citation'lara tıklanınca vurgulama yerine sadece
görsel olarak ayırt edilebilir olmaları istendi (bold `[s.page/paragraph]`),
ve backend'e (FastAPI) hiç dokunulmaması, mevcut `/chat` SSE endpoint'ine
sadece istemci olarak bağlanılması net bir kural olarak belirlendi. Streamlit
tercih edildi (Next.js değil) — minimal, Python-only, mevcut ingestion
kodunu doğrudan import edebiliyor.

**Host'ta mı, container'da mı — host'ta çalıştırılıyor**: Backend Sprint
10'dan beri container'da, Ollama native. Streamlit'i de container'a almak
(a) ingestion zaten host'ta `make ingest` ile çalışıyor ve UI'nin ingestion
wrapper'ı aynı host-side kodu çağırıyor, (b) backend zaten `8000` portundan
dışa açık olduğu için container'dan da host'tan da erişilebilir durumda, (c)
~50 dakikalık backend build'ini tekrar şişirmemek için gerekçesi yoktu. UI
`make ui` ile host'ta, ayrı bir venv'den çalıştırılıyor.

**Gerçek bir bağımlılık çakışması bulundu (varsayılmadı, `pip install` ile
doğrulandı)**: `streamlit==1.61.1`, `starlette>=0.46` istiyor; backend'in
pin'lediği `fastapi==0.115.6` ise `starlette<0.42` istiyor — aynı ortamda
çözülemez bir çakışma. UI kodu zaten `app.main`/`app.api.chat`'i hiç import
etmediği (sadece `app.ingestion.cli` ve HTTP üzerinden `/chat`) için ayrı,
minimal bir `requirements-ui.txt` + ayrı bir venv (`.venv-ui`) ile çözüldü.
`fastapi`, `uvicorn`, `sentence-transformers`, `deepeval` UI'nin hiç
ihtiyaç duymadığı için bu listeye alınmadı.

**Kod tekrarı yok**: `app/ingestion/cli.py`'deki private `_run` fonksiyonu
`run_ingestion()` adıyla public'e çıkarıldı; hem CLI (`make ingest`) hem de
Streamlit'in `app/ui/ingest_helper.py`'si aynı fonksiyonu çağırıyor — embed
client, Qdrant store, sparse encoder wiring'i tek yerde.

**SSE tüketimi**: Streamlit'in kendi execution modeli sync olduğu için
`httpx.stream(...)` (async değil) kullanıldı; `app/ui/sse_client.py`'deki
`parse_sse_lines()` backend'in gerçek `event:`/`data:` formatını (Sprint
6'daki `event: metadata`, düz `data:` token'lar, `event: grounding`) satır
satır parse ediyor. `st.empty()` placeholder'ı her token geldiğinde
güncelleniyor — cevap toplanıp sonda tek seferde basılmıyor.

**Gerçek bir Streamlit çalıştırma hatası bulundu ve düzeltildi**: `streamlit
run app/ui/streamlit_app.py` doğrudan çalıştırıldığında `app.ui.*`
import'ları `ModuleNotFoundError: No module named 'app'` ile patlıyordu —
Streamlit script'in kendi dizinini `sys.path`'e ekliyor, proje kökünü değil.
`Makefile`'daki `ui:` hedefine `PYTHONPATH=.` eklenerek düzeltildi.

**Uçtan uca tarayıcı doğrulaması gerçekten yapıldı (curl ile değil)**: Backend
stack (`docker compose`) ve `make ui` ayağa kaldırıldı, tarayıcı aracıyla
`localhost:8501`'e gidildi. Sprint 9'un golden-set PDF'i (`nimbus_handbook.pdf`,
programatik üretilen, gerçek/doğrulanabilir içerikli) dosya input'una gerçek
bir `File`/`DataTransfer` enjeksiyonuyla yüklendi (native dosya diyaloğu
sandbox'lı tarayıcıda görünmediği için), "Ingest" tıklandı — "Upserted 6
chunk(s) from 1 file(s)" gerçek Qdrant upsert'i doğruladı. Sonra gerçek bir
soru soruldu ("What are the three paid storage tiers and their monthly
prices?"): token'ların ekranda tek tek büyüdüğü canlı olarak yakalandı,
final cevap golden source'taki üç tier'ı ($2.99/$7.99/$19.99) doğru
citation'larla (`[s.2/0]`) verdi, ve "✅ Grounded — citations: [[2, 0], [2,
0]]" göründü.

**Bu doğrulama sırasında ikinci gerçek bug bulundu ve düzeltildi**:
Streamlit'in markdown render'ı çıplak `$` işaretini LaTeX inline math
başlangıcı sanıyor — cevaptaki `$2.99` ve `$7.99` ekranda `$` işareti
olmadan, farklı bir fontla (math render'ı) çıkıyordu; sadece `$19.99` (çift
tırnak/parantez bağlamı farklı olduğu için) düzgün görünüyordu. Gerçek bir
okunabilirlik hatasıydı (fiyatlar bozuk gösteriliyordu), scope dışı
sayılmadı: `highlight_citations()` artık citation'ları bold yapmadan önce
metindeki `$` karakterlerini `\$` ile escape ediyor. Yeni bir test eklendi
(`test_escapes_dollar_signs_so_they_are_not_read_as_latex`), düzeltme
tarayıcıda tekrar doğrulandı.

**Kapsam dışı bırakılanlar (bilinçli)**: Çoklu doküman/oturum yönetimi,
kullanıcı auth, konuşma geçmişinin kalıcı hale getirilmesi (DB yazımı) —
hepsi `st.session_state` ile sadece o oturum için tutuluyor, sayfa
yenilenince sıfırlanıyor. Citation'lara tıklayınca vurgulama da kapsam
dışıydı — sadece görsel ayırt edilebilirlik (bold) yeterliydi.

**Son doğrulama**: 119 test yeşil (Sprint 10'daki 118'e, yeni `$`-escape
testi eklendi), `ruff check` temiz.

Proje sprint 0'dan 11'e kadar plana göre tamamlandı.

### Post-release bug fix: doküman kimliği olmayan citation/grounding

**Gerçek kullanımda bulundu**: Sprint 11'in tarayıcı doğrulaması sırasında
kullanıcı ayrıca kendi CV'sini yükledi (`OmerFaruKOC__CV.pdf`), aynı Qdrant
koleksiyonuna `nimbus_handbook.pdf` (test fixture) ile birlikte girdi. "What
programming languages does this person know" sorusuna verilen cevapta model
`[s.2/0]`, `[s.3/0]`... gibi sürekli artan sayfa citation'ları üretti — ama
CV tek sayfaydı (page 1); bu numaralar aslında **nimbus_handbook.pdf'in
sayfalarına** aitti. Grounding check bazılarını (page/paragraph context'te
hiç yoktu) doğru şekilde "ungrounded" işaretledi, ama en az birini (`s.2/0`)
yanlışlıkla "grounded" saydı çünkü o koordinat gerçekten retrieved context'te
vardı — sadece **başka bir dokümandan**.

**Kök sebep**: `app/llm/grounding.py`'deki `check_grounding`, citation'ları
`(page_number, paragraph_index)` çiftine göre doğruluyordu — hangi
dokümandan geldiğine bakmıyordu. `SearchResult.payload`'da `doc_id` ve
`source_filename` zaten vardı (Sprint 1'den beri), sadece hiç okunmuyordu.
İki doküman aynı koleksiyonda aynı (sayfa, paragraf) koordinatını
paylaşabildiği için (her PDF kendi sayfa 1'inden başlar), bu bir yanlış
pozitif (false grounded) riskiydi.

**Düzeltme**: Citation formatı `[s.PAGE/PARAGRAPH]`'tan `[s.DOC:PAGE/PARAGRAPH]`'a
genişletildi — `DOC`, `source_filename`'in uzantısız, alfanümerik-güvenli
kısa hâli (`app/llm/prompt.py:doc_label`). Bu fonksiyon hem context'i
LLM'e sunan `build_context`'te (Kaynak etiketine doküman adı eklendi) hem de
`grounding.py`'deki doğrulamada kullanılıyor — artık bir citation, SADECE
aynı dokümandan aynı (sayfa, paragraf) çiftiyle eşleşirse "grounded"
sayılıyor. `prompts/answer_v1.txt` ve `v2.txt` yeni format için güncellendi;
`app/ui/citation_formatting.py`'nin regex'i de yeni formatı yakalayacak
şekilde değiştirildi. Yeni bir regresyon testi eklendi
(`test_grounding_rejects_citation_whose_page_paragraph_matches_a_different_document`)
— iki farklı dokümanın aynı koordinatı paylaştığı, yanlış doküman etiketiyle
citation verildiği senaryoyu doğrudan test ediyor.

**Gerçekten doğrulandı**: Container yeniden build edilip (`docker compose
build backend`) ayağa kaldırıldıktan sonra hem CV hem nimbus_handbook
sorguları tekrar denendi — citation'lar artık her zaman doğru doküman adını
taşıyor (`[s.OmerFaruKOC__CV:...]`, `[s.nimbus_handbook:...]`), önceki gibi
yanlış dokümana sızma yok. **Ayrı ve bu fix'in kapsamı dışında kalan bir
gözlem**: model (qwen2.5:7b-instruct) bazen doğru doküman içinde bile yanlış
sayfa/paragraf numarası üretiyor — bu artık grounding tarafından daha
tutarlı yakalanıyor (⚠️ uyarısı çıkıyor), ama modelin citation hassasiyeti
ayrı, çözülmemiş bir sınırlama olarak kayda geçildi.

**Yan bulgu — build altyapısı**: Bu fix'i container'a yansıtmak için
`docker compose build backend` çalıştırılırken, `sentence-transformers`'ın
transitive bağımlılığı olan `torch`'un manylinux aarch64'te varsayılan
olarak **CUDA'lı build'i** (~2GB, `nvidia_cublas`, `nvidia_cudnn` vb. dahil)
çektiği fark edildi — container'da hiç GPU yok (Ollama native, Sprint 10).
`Dockerfile`'a `pip install torch --index-url .../whl/cpu` adımı eklenerek
CPU-only torch zorlandı; sonraki `pip install -r requirements.txt` torch'u
zaten karşılanmış görüp CUDA varyantını atladı. Rebuild süresi buna bağlı
olarak dramatik kısaldı.

121 test yeşil, `ruff check` temiz.

### Takip iyileştirmesi: model sayfa/paragraf numarasını yanlış hatırlıyordu

**Gözlem**: Yukarıdaki fix'ten sonra bile, aynı soruyu tekrar tekrar sorunca
model bazen doğru dokümanı doğru şekilde etiketliyor ama sayfa/paragraf
numarasını yanlış üretiyordu (örn. gerçek koordinat `1/0` iken model `3/9`,
`4/10`, `18/0` gibi rastgele sayılar yazdı). Grounding bunları doğru
yakalayıp uyarıyordu — sistem güvenliydi — ama kullanıcı deneyimi kötüydü
(sık sık ⚠️ uyarısı).

**Kök sebep**: `build_context`, LLM'e "[Kaynak: DOC, Sayfa X, Paragraf Y]"
biçiminde bir *insan-okur* etiket veriyordu; model bunu `[s.DOC:X/Y]`
citation formatına **kendi zihninde dönüştürmek** zorundaydı — bu dönüşüm
sırasında (özellikle 7B gibi küçük bir modelde) sayı transkripsiyon hatası
oluyordu.

**Düzeltme**: `build_context` artık her chunk'ın etiketine kullanıma hazır,
kopyalanabilir citation tag'ini de ekliyor: `"[Kaynak: DOC, Sayfa X,
Paragraf Y — citation tag: [s.DOC:X/Y]]"`. Prompt (`answer_v1.txt`,
`answer_v2.txt`) artık modele bu tag'i **kendi hesaplamak yerine harfiyen
kopyalamasını** söylüyor. Yeni bir test eklendi
(`test_build_context_includes_a_ready_made_citation_tag_per_chunk`).

**Gerçekten doğrulandı**: Container yeniden build edilip aynı soru art arda
4 kez soruldu. Önceki denemelerde her seferinde en az bir ungrounded
citation vardı; düzeltmeden sonraki 4 denemenin **hiçbirinde ungrounded
citation çıkmadı** — model bazen hiç citation vermedi (zararsız, kabul
edilebilir), ama her citation verdiğinde koordinat gerçekten doğruydu.
Kalan bir gözlem: modelin bazen konuyla ilgisiz bir dokümandan (nimbus
handbook) içerik karıştırması — bu retrieval alaka düzeyiyle ilgili, ayrı
ve kapsam dışı bir konu.

122 test yeşil, `ruff check` temiz.

### Küçük takip: aynı citation tag'i her kelimede tekrarlanıyordu

**Gözlem**: Yukarıdaki fix'ten sonra bile, model bazen aynı citation tag'ini
listedeki her madde/kelime için ayrı ayrı tekrarlıyordu (`"Python
[s.doc:1/8] SQL [s.doc:1/8] FastAPI [s.doc:1/8]..."`) — yanlış değildi
(grounded kalıyordu) ama okunabilirliği bozuyordu.

**Düzeltme**: Prompt'a (`answer_v1.txt`, `answer_v2.txt`) "cite each tag
ONLY ONCE per sentence or list, not after every word or every list item"
talimatı eklendi. Yeni bir regression testi eklendi
(`test_load_system_prompt_v1_warns_against_repeating_the_tag_per_word`).

**Gerçekten doğrulandı (ve dürüstçe raporlandı)**: Aynı soru 3 kez daha
soruldu. 2/3 denemede model artık tek, temiz bir citation kullandı; 1/3
denemede hâlâ eski davranışa (kelime başına tekrar) döndü. Bu, küçük bir
modelin (7B) talimat takibindeki doğal tutarsızlığı — kesin/deterministik
bir garanti değil, olasılıksal bir iyileşme. Bilinçli olarak UI-tarafı bir
"ardışık aynı tag'leri birleştir" post-processing eklenmedi (istenirse
sonra eklenebilir) — mevcut iyileşme yeterli kabul edildi.

123 test yeşil, `ruff check` temiz.

## Sprint 12 (mini) — Observability in UI

Amaç: Jaeger'a hiç gitmeden, Streamlit UI'da her sorgunun pipeline
adımlarının (embed → retrieve → rerank → generate) gerçek süresini görmek.

### Kapanış notu

**Karar: Jaeger API'sini backend değil, Streamlit çağırıyor.** Yeni bir
backend proxy endpoint'i eklemek yerine, `app/ui/trace_client.py` doğrudan
Jaeger'ın kendi HTTP API'sine (`GET /api/traces/{traceID}`) bağlanıyor.
Gerekçe: Jaeger zaten Sprint 0'dan beri host'tan erişilebilir
(`docker-compose.yml`'deki `16686:16686` port mapping'i), backend'e sadece
bu iş için bir JSON proxy'si eklemenin (yeniden build gerektirir, Sprint
10/11'de ~50dk'ya varan sürelerle görüldü) bir gerekçesi yok. Sprint 11'in
kurduğu deseni (UI, backend'e salt-okur bir istemci olarak bağlanıyor,
backend'i değiştirmeden) Jaeger için de tekrarladı.

**Trace ID taşıma**: `app/llm/generate.py`'deki `stream_answer`, `"generate"`
span'i başladıktan hemen sonra `span.get_span_context().trace_id`'yi
32-karakterlik hex'e çevirip (`format(trace_id, "032x")`, Jaeger API'sinin
beklediği format) mevcut metadata event'ine (Sprint 7) ekliyor. `generate`
kök span değil (`chat_request` kök) ama trace_id trace genelinde aynı
olduğu için ayrıca kökü aramaya gerek yok — gerçek bir `InMemorySpanExporter`
testiyle doğrulandı (`test_stream_answer_metadata_trace_id_matches_the_generate_span`).

**Jaeger API'sinin gerçek response şekli (varsayılmadı, curl ile
doğrulandı)**: `GET /api/traces/{traceID}` → `{"data": [{"spans": [{
"operationName": ..., "startTime": <mikrosaniye>, "duration": <mikrosaniye>,
...}]}]}`. Gerçek bir trace ID ile (`curl http://localhost:16686/api/traces/...`)
doğrulandı, tüm 6 span'in (`chat_request`, `load_models`, `embed_query`,
`retrieve_hybrid`, `rerank`, `generate`) beklenen alanlarla döndüğü görüldü.

**Gerçek bir bug bulundu ve düzeltildi — kısmi indexlenmiş trace**:
Tarayıcı doğrulaması sırasında panel bazen `generate` (en uzun süren, son
kapanan span) barını hiç göstermiyordu. Kök sebep: `BatchSpanProcessor`
(Sprint 8) span'leri toplu export ediyor — bazı child span'ler (`embed_query`,
`rerank`) Jaeger'a ulaşmışken, en son kapanan span henüz export edilmemiş
olabiliyor. İlk `fetch_trace_spans` implementasyonu "herhangi span geldi mi"
diye kontrol ediyordu, bu yüzden kısmi bir batch'i "tamam" sayıp erken
dönüyordu. **Düzeltme**: retry artık `chat_request` (kök span, her zaman en
son kapanan — Sprint 8) spesifik olarak görününceye kadar devam ediyor,
sadece "spans boş değil" değil. Yeni bir regresyon testi eklendi
(`test_fetch_trace_spans_keeps_retrying_when_root_span_is_missing`) — bu
tam senaryoyu (kısmi batch → tam batch) simüle ediyor.

**Retry/polling kararı**: Varsayılan 5 deneme, 1s ara — sınırsız değil.
Tüm denemeler boşsa (ya da kök span hiç gelmezse) `fetch_trace_spans` hata
fırlatmadan boş liste döndürüyor; UI bunu "Trace not indexed by Jaeger yet"
mesajıyla gösteriyor, spinner'da asılı kalmıyor.

**Gerçekten doğrulandı (iki kaynak yan yana)**: Backend yeniden build edilip
(`docker compose build backend`, CPU-only torch sayesinde hızlı), `make ui`
ile Streamlit başlatıldı. Tarayıcıdan gerçek bir soru soruldu, "🔍 Pipeline
trace" paneli açıldı — 5 span'in hepsi (`embed_query`, `retrieve_hybrid`,
`rerank`, `generate`, `load_models`) bar chart'ta göründü, "Total: 6485.1 ms"
yazısı çıktı. Aynı trace ID ile `curl http://localhost:16686/api/traces/{id}`
çekildi: `chat_request` (kök) süresi **6485.1ms** — UI'daki "Total" ile
**birebir aynı**. Bar chart'taki her span adı da curl çıktısındaki span
adlarıyla bire bir eşleşti.

**Kapsam dışı / not edilen (bu sprint'in hedefi değil)**: Doğrulama
sırasında modelin bazen citation vermediği (boş `citations_found`) ve
context label'ının (`"[Kaynak: ..., citation tag: ...]"`) bazen cevabın
içine sızdığı gözlemlendi — bunlar Sprint 11+ post-release notlarındaki
bilinen model-tutarlılığı sınırlamalarının devamı, bu sprint'in kapsamı
(gözlemlenebilirlik paneli) dışında, ayrıca dokunulmadı.

129 test yeşil, `ruff check` temiz.
