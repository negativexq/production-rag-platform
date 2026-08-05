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
