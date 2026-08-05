# Sprint 4 — Metadata Filtering Planı

## Amaç
Hybrid search'e payload bazlı filtreleme eklemek.

## Kapsam Kararı — Mevcut Alanlarla Sınırlı

Sprint 1-3'ten beri chunk payload'ında zaten şu alanlar var: `doc_id`,
`page_number`, `paragraph_index`, `char_range`, `text`, `source_filename`.
Bu sprint **yeni bir ingestion alanı eklemiyor** — filtreleme, var olan
`doc_id` ve `source_filename` alanları üzerinden yapılacak (enterprise
senaryosu: "sadece şu dosyada/dosyalarda ara"). `page_number` da filtre
parametresi olarak desteklenecek (örn. "sadece 3. sayfada ara").

**Tarih/tag gibi alanlar bu sprint'in kapsamı dışında** — ingestion'da
(`app/ingestion/models.py:Chunk`, `qdrant_store.py`) bugün böyle bir alan
yok, ve PDF'lerden otomatik tarih/tag çıkarımı ayrı bir tasarım kararı
gerektiriyor (dosya sistem tarihi mi, PDF metadata'sı mı, manuel etiketleme
mi). Bu, ileride ayrı bir mini-sprint olarak ele alınmalı: ingestion'a geriye
dönük tarih/tag alanı eklemek + payload index'i + filtre desteği. Şimdilik
`docs/PLANNING.md`'de bir not olarak bırakılıyor.

## Doğrulanan Gerçek (varsayılmadı, gerçek Qdrant'a karşı test edildi)

**Soru**: Qdrant Query API'de `prefetch` (dense + sparse) + top-level
`query=FusionQuery(fusion=RRF)` + top-level `query_filter` kombinasyonunda,
filtre fusion'dan ÖNCE mi (prefetch adayı seçilirken) yoksa SONRA mı (fusion
sonrası final listede) uygulanıyor?

**Deney**: Bir collection'a `doc_id="A"` olan 1 point (dense skoru düşük) ve
`doc_id="B"` olan 50 point (dense skoru yüksek, sorguyla bire bir eşleşen)
eklendi. `prefetch_limit=1` (en agresif senaryo — sadece 1 aday alınabilir)
ile `query_filter={doc_id="A"}` uygulanan bir sorgu çalıştırıldı.

**Sonuç**: Sorgu doğru şekilde `A` point'ini döndürdü — 50 tane daha yüksek
skorlu `B` point'i varken ve prefetch limiti sadece 1 iken bile. Bu,
**top-level `query_filter`'ın prefetch aşamasına da uygulandığını** (filtre
fusion'dan önce, aday havuzunu daraltırken devreye giriyor) kanıtlıyor —
filtreyi ayrıca her `Prefetch`'e tekrar tekrar geçirmeye gerek yok. (Bkz.
`/tmp/probe_filter3.py` — geçici deney script'i, kalıcı değil.)

**Sonuç/karar**: `hybrid_search()` ve `dense_only_search()`'e tek bir
top-level `filters` parametresi eklenecek, her iki `Prefetch`'e ayrı ayrı
geçirilmeyecek — çünkü gerekli değil, gereksiz karmaşıklık olur.

## Modül Değişiklikleri

```
app/retrieval/
├── filters.py          # build_filter(doc_ids, source_filenames, page_numbers) -> qmodels.Filter | None
├── hybrid_search.py     # + filters parametresi (dense_only_search, hybrid_search)
└── search.py            # + filters parametresi, search() imzasına ekleniyor
```

## Kararlar

- Filtre şeması: `{"doc_ids": [...], "source_filenames": [...], "page_numbers": [...]}`
  — her alan opsiyonel, verilenler AND ile birleşiyor (`Filter(must=[...])`),
  her alanın kendi içindeki liste değerleri OR (`MatchAny`).
- Filtre `None`/boş ise `query_filter` hiç gönderilmiyor (filtresiz davranış
  aynı kalıyor, ek bir "filtre yok" özel durumu yok).

## Test-First Plan

1. `tests/test_filters.py` — `build_filter()`'ın doğru `Filter`/`FieldCondition`/
   `MatchAny` yapısını ürettiğini, boş/None girişte `None` döndürdüğünü doğrula.
2. `tests/test_hybrid_search.py`'a ekle — gerçek Qdrant'a karşı (docker-compose,
   `:memory:` değil, çünkü bu tam olarak sunucu davranışını test ediyoruz):
   iki farklı `doc_id`'den chunk'lar ekle, aynı sorguyu filtresiz ve
   `doc_id` filtreli çalıştır, sonuç setlerinin **farklı ve doğru** olduğunu
   assert et (DoD'nin istediği somut kanıt).
3. `tests/test_search.py`'a filtre parametresinin `search()`'e doğru
   iletildiğini doğrulayan bir test ekle.

## Adımlar

1. Kırmızı testleri yaz
2. `app/retrieval/filters.py` implementasyonu
3. `hybrid_search.py`, `search.py`'a filtre parametresi ekle
4. Testleri yeşile çevir, `ruff check` temiz
5. Gerçek Qdrant'a karşı manuel/otomatik bir örnekle filtreli/filtresiz
   sonuç farkını göster
6. `docs/PLANNING.md` kapanış notu — filtre+fusion bulgusu, filtrelenebilir
   alanlar, tarih/tag'in kapsam dışı kaldığı notu

## Definition of Done

- Filtreli ve filtresiz aynı sorgu farklı, doğru sonuç setleri döndürüyor
- Testler ve lint temiz
