# Sprint 5 — Cross-Encoder Reranking Planı

## Amaç
Hybrid search'ten gelen top-k adayları gerçek alaka düzeyine göre yeniden sıralamak.

## Latency Ölçümü — Gerçek Chunk Boyutunda (varsayılmadı)

M2 CPU'da, gerçek chunk boyutunda (~500 karakter, warehouse/order senaryosu)
`cross-encoder/ms-marco-MiniLM-L-6-v2` ile top-20 aday çifti (query, chunk)
skorlandı:

| Aşama | Süre |
|---|---|
| Model yükleme (ilk, indirme dahil) | ~73s (bir kerelik) |
| Model yükleme (cache'den) | ~9s (proses başına bir kerelik) |
| 20 çiftin skorlanması (ilk çağrı, warmup) | ~180ms (9ms/çift) |
| 20 çiftin skorlanması (ısınmış) | ~60ms (2.8ms/çift) |

Sprint 3'teki SPLADE deneyiminin aksine (~134ms/chunk, kabul edilemez), bu
sefer top-20 rerank başına eklenen gecikme **60-180ms** — bir kullanıcı
sorgusu başına kabul edilebilir bir maliyet (LLM generation zaten
saniyeler sürecek). **Karar: `ms-marco-MiniLM-L-6-v2` kullanılacak,
alternatif aramaya gerek yok.**

## Modül

```
app/reranker/
├── __init__.py
└── cross_encoder.py    # CrossEncoderReranker: rerank(query, candidates) -> top-n
```

## Kararlar

- **Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2` (CPU'da hızlı, MS MARCO
  passage ranking için eğitilmiş, retrieval-rerank için standart seçim).
- **k=20, n=5 — GEÇİCİ değerler** (Sprint 1'deki chunk boyutu kararı gibi):
  hybrid search'ten `top_k=20` aday çekilecek, rerank sonrası `top_n=5`'e
  daraltılacak. Bu sayılar Sprint 9'un (RAGAS/DeepEval evaluation) gerçek
  metriklerine göre kesinleşecek — şimdilik makul bir başlangıç varsayımı.
- **Skor**: CrossEncoder ham logit skoru döndürüyor (olasılık değil) —
  `SearchResult.score`'u rerank sonrası bu skorla değiştireceğiz, orijinal
  RRF skoru `payload` içinde değil ayrı bir alanda saklanmayacak (rerank
  sonrası "hangi skor" sorusu ortadan kalkıyor çünkü rerank skoru nihai
  sıralamayı belirliyor).
- **search.py entegrasyonu**: `hybrid_search(top_k=20)` → `rerank(query,
  candidates, top_n=5)` → final sonuç. Rerank adımı opsiyonel bir parametre
  ile atlanabilir olacak (`rerank: bool = True`) ki ileride A/B karşılaştırma
  (Sprint 9) kolay olsun.

## Test-First Plan

1. `tests/test_reranker.py` — gerçek `CrossEncoderReranker` ile:
   - Bariz şekilde alakalı bir chunk'ın, bariz şekilde alakasız bir chunk'tan
     daha yüksek skor aldığını doğrula
   - `top_n` parametresinin sonuç sayısını doğru sınırladığını doğrula
   - Rerank sonrası sıralamanın skора göre azalan olduğunu doğrula
2. `tests/test_search.py`'a ekle — `search()`'e rerank entegrasyonu:
   sahte/deterministic bir reranker enjekte edilerek, hybrid'in top-k'sının
   rerank'e doğru iletildiği ve rerank sonucunun döndürüldüğü doğrulanacak
   (gerçek CrossEncoder'a bağımlı olmadan, hızlı test).
3. **Somut kanıt testi/scripti**: hybrid search'ün top-1 olarak verdiği ama
   aslında sorguyla alakasız bir chunk (örn. sadece sparse/BM25 çakışması
   sayesinde üste çıkan) ile gerçekten alakalı ama hybrid'in düşük sıraya
   koyduğu bir chunk'ı gerçek CrossEncoder ile skorla, ölçülmüş skor farkını
   raporla.

## Adımlar

1. `requirements.txt`'e `sentence-transformers` ekle
2. Kırmızı testleri yaz
3. `app/reranker/cross_encoder.py` implementasyonu
4. `search.py`'a rerank adımını entegre et
5. Testleri yeşile çevir, `ruff check` temiz
6. Gerçek verilerle rerank öncesi/sonrası somut karşılaştırma
7. `docs/PLANNING.md` kapanış notu — model seçimi, gerçek latency, k/n'in
   hâlâ geçici olduğu

## Definition of Done

- Rerank sonrası top-n sonuçların rerank öncesine göre daha alakalı olduğu
  somut örneklerle gösterilmiş
- Testler ve lint temiz
