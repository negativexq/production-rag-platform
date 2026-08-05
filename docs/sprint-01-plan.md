# Sprint 1 — PDF Ingestion + Chunking Planı

## Amaç
PDF'lerden sayfa/paragraf metadata'sı korunarak temiz text chunk'ları çıkarmak.

## Kapsam Dışı (bilinçli karar)
Taranmış / image-only (OCR gerektiren) PDF'ler bu sprint'in kapsamı dışında.
Sadece text-layer'ı olan PDF'lerle çalışılıyor. Bir sayfada text-layer yoksa
(PyMuPDF `page.get_text()` boş dönerse) o sayfa boş chunk üretmeden atlanır —
sessizce veri kaybı değil, gelecekte OCR fallback eklenene kadar bilinen bir
sınırlama olarak README/PLANNING'de belgelenir.

## Modül

```
app/ingestion/
├── __init__.py
├── models.py     # Chunk, dataclass: {doc_id, page_number, paragraph_index, char_range, text}
├── parser.py     # PyMuPDF ile PDF -> sayfa bazlı paragraf listesi
└── chunker.py    # Paragraflardan token-bazlı, cümle sınırına duyarlı chunk üretimi
```

## Kararlar

- **PDF kütüphanesi**: PyMuPDF (`fitz`) — hız ve sayfa/blok bazlı text extraction için.
- **Paragraf tespiti**: PyMuPDF'nin `page.get_text("blocks")` çıktısı, aynı sayfadaki
  metin bloklarını paragraf sınırı olarak kabul eder (blok = PyMuPDF'nin layout
  analizinde birbirine yakın satırları grupladığı birim; boş satır/blok araları
  paragraf ayracı olarak yorumlanır).
- **Chunking stratejisi (GEÇİCİ — bkz. Açık Sorular)**: 500 token / %10 (50 token)
  overlap, kaba bir whitespace tokenizer ile (gerçek bir LLM tokenizer'ı henüz
  bağlanmadı — Sprint 6/9'da model tokenizer'ına geçiş değerlendirilebilir).
  Chunk sınırı bir cümleyi ortadan bölmeyecek şekilde, cümle sonu noktalama
  işaretlerine (`.`, `!`, `?`) en yakın noktadan kesilir.
- **doc_id**: dosya içeriğinin SHA-256 hash'i (Sprint 2'deki idempotent
  ingestion'la tutarlı olacak şekilde, içerik değişirse doc_id de değişir).
- **char_range**: chunk'ın kaynak sayfa metni içindeki `(start, end)` karakter
  aralığı — grounding/debug için.

## Test-First Plan

1. `tests/fixtures/` altına gerçek, çok sayfalı, birden fazla paragraflı basit
   bir PDF fixture'ı oluştur (PyMuPDF'nin kendisiyle programatik üretilecek —
   böylece bağımlılık eklemeden, deterministik ve depoya küçük boyutta
   commit'lenebilir bir örnek elde edilir).
2. `tests/test_parser.py`
   - Her sayfanın doğru sayfa numarasıyla (1-indexed) döndüğünü doğrula
   - Paragraf sınırlarının korunduğunu doğrula (bilinen paragraf sayısı)
3. `tests/test_chunker.py`
   - Chunk'ların ~500 token civarında olduğunu, overlap'in uygulandığını doğrula
   - Bir chunk'ın ortasında yarım bırakılmış cümle olmadığını doğrula
   - Her chunk'ın metadata'sının (`doc_id`, `page_number`, `paragraph_index`,
     `char_range`) doğru sayfaya eşlendiğini doğrula — bilinçli olarak "sayfa 3'teki
     metin" içeren bir chunk'ın `page_number == 3` döndürdüğünü kontrol eden bir test

## Adımlar

1. `requirements.txt`'e `pymupdf` ekle, kur
2. Test fixture PDF'i üreten script/fonksiyon yaz (`tests/fixtures/make_sample_pdf.py`
   veya conftest fixture olarak, PDF'i test çalışırken üretip geçici dosyaya yaz)
3. Kırmızı testleri yaz (`test_parser.py`, `test_chunker.py`)
4. `app/ingestion/models.py`, `parser.py`, `chunker.py` implementasyonu
5. Testleri yeşile çevir
6. `ruff check` temiz
7. `docs/PLANNING.md` Sprint 1 kapanış notu — chunk boyutu kararının geçici
   olduğunu, Sprint 5 ve Sprint 9 sonrası revize edileceğini vurgula
8. Commit (AI co-author satırı yok)

## Açık Sorular (bu sprint'te KESİNLEŞMİYOR)

- Chunk boyutu (500 token / %10 overlap) başlangıç varsayımı — Sprint 5
  (reranking kalitesi) ve Sprint 9 (evaluation metrikleri) sonuçlarına göre
  revize edilecek.
- Taranmış PDF / OCR desteği — v1 kapsamı dışı, ileride ayrı bir sprint/görev
  olarak değerlendirilebilir.

## Definition of Done

- Örnek bir PDF setinde her chunk doğru sayfa numarasına eşleniyor, birim
  testlerle doğrulanmış
- `make test` ve `make lint` temiz
