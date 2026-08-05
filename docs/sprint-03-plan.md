# Sprint 3 — Hybrid Search (Native Qdrant) Planı

## Amaç
Dense + sparse vektörleri Qdrant içinde birleştirip tek bir hybrid retrieval sağlamak.

## Sparse Model Seçimi — Gerçek Ölçüm (varsayılmadı)

M2 CPU üzerinde, gerçek chunk boyutunda (~70 kelime) metinlerle FastEmbed'in
iki seçeneği ölçüldü:

| Model | Boyut (indirme) | Encode süresi |
|---|---|---|
| `prithivida/Splade_PP_en_v1` (SPLADE++) | 532 MB | **~134 ms/chunk** |
| `Qdrant/bm25` | 10 MB | **~0.1 ms/chunk** |

SPLADE, öğrenilmiş terim genişletmesi (semantic term expansion) sunan bir
transformer modeli — ama CPU'da chunk başına ~134ms, 1000 chunk'lık bir
ingestion'a ~2+ dakika ekliyor (dense embedding + parsing üstüne). M2 16GB'de
bu **gözle görülür ve kabul edilemez** bir yavaşlama (planın öngördüğü çıkış
koşulu). `Qdrant/bm25` ise saf istatistiksel (BM25 formülü, terim frekansı +
Qdrant tarafında hesaplanan IDF) bir sparse temsil — chunk başına ~0.1ms,
1000x'ten fazla hızlı, model indirmesi de 50x küçük.

**Karar: `Qdrant/bm25` kullanılacak, SPLADE değil.** Gerekçe: bu proje
enterprise-tarzı bir mimariyi M2/16GB gibi kısıtlı bir donanımda göstermeyi
hedefliyor; SPLADE'in getirdiği marjinal semantic-expansion kalitesi, ingestion
süresini kabul edilemez şekilde uzatma maliyetine değmiyor. `Qdrant/bm25`
ayrıca Qdrant'ın native sparse index `modifier="idf"` özelliğiyle *özel olarak*
tasarlanmış — corpus'u client tarafında "fit" etmeye gerek yok, IDF hesaplaması
Qdrant'ın kendi indexlediği corpus üzerinden sunucu tarafında yapılıyor. Bu da
"Qdrant native fusion" temasıyla tam örtüşüyor.

Kaynak kod incelendi (`fastembed/sparse/bm25.py`): `Bm25.embed()` (indexing) her
doküman için terim frekansı bazlı ağırlıklar üretiyor (`requires_idf=True` —
Qdrant'a "bu koleksiyonda IDF modifier'ı sen hesapla" sinyali); `Bm25.query_embed()`
ise sorgu tarafında sadece token varlığına göre (ağırlık=1.0) çalışıyor — klasik
BM25 query davranışı.

## Migration Notu — Mevcut Koleksiyona Sparse Ekleme

Qdrant, var olan bir collection'a yeni bir named vector (`sparse_vectors_config`)
**sonradan eklemeyi desteklemiyor** — collection'ın yeniden oluşturulması
gerekiyor. Kontrol edildi: şu an `rag_chunks` collection'ı boş (Sprint 2'nin
manuel test verisi temizlenmişti), yani gerçek bir migration/veri kaybı riski
yok. `QdrantStore.ensure_collection()` bu yüzden şu davranışı izleyecek: eğer
collection var ama sparse vector'ü yoksa, **drop edip yeniden oluşturur** —
bu, geliştirme ortamı için kabul edilebilir bir kısayol; gerçek bir prod
migration'ı (var olan point'leri koruyarak) ayrı bir reindex job'ı gerektirirdi
(scroll + sparse hesapla + yeni collection'a upsert + alias swap), bu sprint'in
kapsamı dışında.

## Modül

```
app/retrieval/
├── __init__.py
├── sparse.py           # Bm25 wrapper: embed_document(text), embed_query(text)
└── hybrid_search.py     # hybrid_search(), dense_only_search() — Qdrant Query API + RRF
app/ingestion/
├── qdrant_store.py      # + sparse vector config, upsert_chunks sparse parametresi
└── ingest.py            # + sparse embedding adımı
```

## Kararlar

- **Sparse vector adı**: `"sparse"` (dense zaten `"dense"`).
- **Sparse index modifier**: `Modifier.IDF` — Qdrant IDF'i kendi indexlediği
  corpus'tan hesaplar.
- **Query prefix**: Sprint 2'nin bıraktığı uyarı doğrultusunda, dense query
  embedding'i `"search_query: "` prefix'iyle alınacak (ingestion tarafı
  `"search_document: "` olarak Sprint 2'de zaten uygulanmıştı — değişmiyor).
  Sparse tarafta prefix kavramı yok (BM25 saf istatistiksel).
- **Fusion**: Qdrant Query API'nin native `FusionQuery(fusion=Fusion.RRF)`'i,
  `prefetch` ile dense ve sparse'tan ayrı ayrı top-k aday çekip (`prefetch_limit`,
  örn. 20) RRF ile birleştirecek.
- **Test stratejisi**: `:memory:` Qdrant client'ının `query_points` +
  `prefetch` + `FusionQuery` desteğini gerçek bir örnekle doğruladım (deneme
  script'i) — hızlı birim testler için kullanılabilir, gerçek sunucu davranışını
  taklit ediyor.

## Test-First Plan

1. `tests/test_sparse.py` — `Bm25` wrapper'ının doküman/sorgu embedding'i
   üretebildiğini, aynı metnin deterministic aynı sparse vektörü verdiğini
   doğrula.
2. `tests/test_qdrant_store.py`'a ekle — collection'ın hem dense hem sparse
   vector ile oluşturulduğunu, sparse'sız var olan bir collection'ın drop
   edilip yeniden oluşturulduğunu, upsert'in sparse vektörü doğru yazdığını
   doğrula.
3. `tests/test_hybrid_search.py` — `:memory:` Qdrant'a, biri sadece anahtar
   kelimeyle (BM25'in yakalayacağı) biri sadece semantik olarak alakalı
   (dense'in yakalayacağı, farklı kelimeler) iki chunk indexle. Sorguyu hem
   `dense_only_search` hem `hybrid_search` ile çalıştır, **hybrid'in bulduğu
   ama dense-only'nin bulamadığı somut bir örneği assert et** (DoD'nin istediği
   "iddia değil, çıktı" kanıtı).
4. `tests/test_ingest.py`'a ekle — ingest edilen chunk'ların Qdrant'ta sparse
   vektöre de sahip olduğunu doğrula.

## Adımlar

1. `requirements.txt`'e `fastembed` ekle
2. Kırmızı testleri yaz
3. `app/retrieval/sparse.py`, `qdrant_store.py` güncellemesi, `hybrid_search.py`
4. `ingest.py`'a sparse embedding adımını ekle
5. Testleri yeşile çevir, `ruff check` temiz
6. Gerçek bir örnek PDF ile: aynı sorguyu dense-only ve hybrid ile çalıştır,
   somut farkı göster (CLI/script çıktısıyla)
7. `docs/PLANNING.md` kapanış notu — sparse model kararı (BM25, SPLADE'e karşı
   gerekçeli), fusion ayarları, migration notu

## Definition of Done

- Hybrid search çalışıyor
- Sadece-dense'e göre farkı somut bir örnekle gösterilmiş
- Testler ve lint temiz
