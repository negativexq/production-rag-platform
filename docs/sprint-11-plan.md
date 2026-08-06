# Sprint 11 — UI (minimal, stretch) Planı

## Amaç
Streaming cevap ve citation'ları gösteren basit bir arayüz.

## Karar — Streamlit Host'ta Çalışıyor, Container'a Girmiyor

- **Ingestion pipeline zaten host/venv'de** (Sprint 10 kararı) — UI'ın "PDF
  yükle" özelliği bu pipeline'ı doğrudan çağıracağı (kod tekrarı olmadan,
  `app.ingestion.ingest.ingest_path` fonksiyonunu import ederek) için,
  Streamlit'i de host'ta tutmak dosya sistemi erişimini basitleştiriyor —
  container'da çalıştırsaydık, yüklenen PDF'i container içine mount etmek
  gibi ek bir karmaşıklık gerekirdi.
- **Backend zaten `localhost:8000`'e port-mapped** (container'da olsa da) —
  Streamlit'in backend'e nereden bağlandığı (host ya da container) fark
  etmiyor, HTTP/SSE her iki durumda da `localhost:8000` üzerinden çalışıyor.
  Bu yüzden "backend'e yakın dur" argümanı bu kararı etkilemiyor.
- **Backend Docker image'i zaten ağır** (Sprint 10'da build ~50 dakika sürdü,
  torch/sentence-transformers gibi büyük bağımlılıklar yüzünden). Streamlit'i
  bu image'e eklemek yeniden build gerektirir ve stretch/opsiyonel bir UI
  için gereksiz bir maliyet. Streamlit kendi hafif bağımlılığını
  (`requirements-ui.txt`, backend'in `requirements.txt`'inden ayrı) host
  venv'inde tutuyor.
- **Sonuç: Streamlit host'ta, `make ui` ile başlatılıyor, container'a
  girmiyor.** Ollama zaten native (Sprint 0), ingestion zaten host'ta
  (Sprint 10) — bu üçü "host'ta ve hafif" grubunda kalıyor, sadece backend
  (ağır ML bağımlılıkları olan, gerçek serving path'i) container'da.

## Modül

```
app/ui/
├── __init__.py
├── streamlit_app.py     # Streamlit sayfası — chat + PDF upload
├── sse_client.py          # SSE satırlarını (data:/event:) yapılandırılmış event'lere ayrıştırma
├── citation_formatting.py  # [s.sayfa/paragraf] referanslarını görsel olarak işaretleme
└── ingest_helper.py         # ingest_path()'i UI'dan çağıran ince wrapper (kod tekrarı yok)
requirements-ui.txt          # streamlit + httpx (backend'in requirements.txt'inden ayrı, image'i şişirmesin)
```

## Kararlar

- **SSE tüketimi**: Streamlit senkron bir script modeli kullanıyor (her
  etkileşimde script baştan sona çalışır). Gerçek zamanlı streaming
  görünümü için `httpx.stream()` (senkron mod) ile backend'in `/chat`
  endpoint'ine bağlanılıp, her `data:`/`event:` satırı geldikçe bir
  `st.empty()` placeholder'ı güncellenecek — backend'in cevabı tamamlamasını
  bekleyip topluca basmak yerine, gerçekten token token ekrana yazılacak.
  Bu, `event: grounding` satırı gelene kadar devam edecek.
- **Citation gösterimi**: `[s.<sayfa>/<paragraf>]` deseni regex ile
  yakalanıp `**[s.X/Y]**` (kalın) olarak render ediliyor — tıklanabilir
  olması bu sprint'in kapsamı dışı bırakıldı (plan metninde de "illa
  gerekmiyor" deniyor), ama görsel olarak ayırt edilebilir.
- **Grounding uyarısı**: stream bitince gelen `grounding` event'i
  `grounded: false` ise turuncu bir `st.warning()` ile hangi citation'ların
  doğrulanamadığı gösterilecek; `true` ise sessiz bir `st.caption()` ile
  "grounded" onayı — hiçbir durumda event sessizce yutulmayacak.
- **PDF yükleme**: `st.file_uploader` ile alınan dosya geçici bir dizine
  yazılıp `app.ingestion.ingest.ingest_path` (Sprint 2-3'ün gerçek
  fonksiyonu) çağrılıyor — ayrı bir ingestion mantığı yazılmıyor.

## Test-First Plan

UI'ın kendisi (widget'lar, layout) geleneksel anlamda birim test edilemez;
bu yüzden test-first, **saf mantık** içeren modüllere uygulanacak:

1. `tests/test_sse_client.py` — `parse_sse_line()`/event birleştirme
   mantığının `data:`/`event:` satırlarını doğru ayrıştırdığını doğrula
   (gerçek backend'in ürettiği format — Sprint 6'daki `app/api/chat.py`
   çıktısıyla birebir aynı).
2. `tests/test_citation_formatting.py` — citation regex'inin doğru
   eşleştiğini, eşleşmeyen metni bozmadığını doğrula.

`ingest_helper.py` ayrıca test edilmeyecek çünkü zaten test edilmiş
`ingest_path`'i hiçbir ek mantık eklemeden çağırıyor (ince bir wrapper).

## Doğrulama Planı (gerçek, tarayıcıda)

1. `make up` (backend+qdrant+jaeger) + `make ui` (Streamlit, host'ta)
2. Tarayıcıda `http://localhost:8501` aç
3. Gerçek bir PDF yükle, ingest'in bittiğini UI'da gör
4. Gerçek bir soru sor, cevabın **token token** aktığını (curl ile SSE
   test etmek yeterli değil, tarayıcıda görsel akışı gerçekten izle) ve
   `[s.X/Y]` citation'ların vurgulu göründüğünü doğrula
5. Context dışı bir soru sorup grounding uyarısının/onayının göründüğünü
   doğrula

## Adımlar

1. `requirements-ui.txt` oluştur
2. Kırmızı testleri yaz (`sse_client`, `citation_formatting`)
3. Bu iki modülü implemente et, testleri yeşile çevir
4. `ingest_helper.py`, `streamlit_app.py` implementasyonu
5. `Makefile`'a `make ui` hedefi ekle
6. `ruff check` temiz
7. Gerçek tarayıcı doğrulaması (yukarıdaki plan)
8. `docs/PLANNING.md` kapanış notu

## Definition of Done

- PDF yükle → soru sor → streaming cevabı citation'larla birlikte gör,
  uçtan uca tarayıcıda doğrulanmış
- Testler ve lint temiz
