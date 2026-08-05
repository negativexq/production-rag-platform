# Sprint 7 — Prompt Versioning Planı

## Amaç
Prompt'ları kod değişikliği gerektirmeden versiyonlayıp, hangi versiyonun
kullanıldığını izlenebilir kılmak.

## Taşıma Kararı — Sıfırdan Yazma, Mevcut Çalışanı Versiyona Al

Sprint 6'da gerçek `qwen2.5:3b-instruct` ile test edile edile sabitlenmiş
`SYSTEM_PROMPT_V1` (özellikle: `[s.PAGE/PARAGRAPH]` formatı, açık örnek —
`"[Kaynak: Sayfa 3, Paragraf 0]" için [s.3/0] yaz` — ve "Kaynak/Sayfa/
Paragraf kelimelerini kullanma" talimatı) **birebir aynı metinle**
`prompts/answer_v1.txt`'e taşınacak. Bu metin ilk denemede çalışmamış,
gerçek model davranışıyla düzeltilmişti (bkz. Sprint 6 kapanış notu) — bu
yüzden yeniden yazılmayacak, sadece dosyaya taşınacak.

## Modül Değişiklikleri

```
prompts/
├── answer_v1.txt    # Sprint 6'nın sabitlenmiş prompt'u, birebir taşındı
└── answer_v2.txt     # yeni, daha kısa/farklı bir varyasyon — versiyonlama
                       # mekanizmasını göstermek için, "daha iyi" olması şart değil

app/shared/config.py   # + active_prompt_version: str = "v1" (env: ACTIVE_PROMPT_VERSION)
app/llm/prompt.py       # refactor: load_system_prompt(version) dosyadan okuyor,
                         # build_messages(question, chunks, version) artık version parametresi alıyor
app/llm/generate.py     # stream_answer(..., prompt_version) — kullanılan versiyonu
                         # bir "metadata" event'i olarak stream'in başında yayınlıyor
app/api/chat.py          # settings.active_prompt_version'ı okuyup generate'e geçiyor
```

## Kararlar

- **Versiyon seçimi nerede**: `app/shared/config.py`'a `active_prompt_version`
  eklendi (`.env`'de `ACTIVE_PROMPT_VERSION=v2` ile değiştirilebilir).
  `build_messages()`/`stream_answer()` versiyonu **parametre olarak** alıyor,
  kendi içinde `settings`'i okumuyor — böylece fonksiyonlar saf/test edilebilir
  kalıyor, config okuma sorumluluğu sadece `app/api/chat.py`'de (çağrı
  zincirinin en üstünde, gerçek HTTP isteğini işleyen yerde) kalıyor.
- **Versiyonun response'ta görünürlüğü — KARAR: stream'in başında ayrı bir
  `metadata` SSE event'i.** Sprint 6'da zaten `token` ve `grounding` diye iki
  event tipi var; üçüncü bir `metadata` event'i (`{"type": "metadata",
  "prompt_version": "v1"}`) stream'in en başında (ilk token'dan önce)
  gönderilecek. Alternatifi (grounding event'inin sonuna eklemek) reddedildi
  çünkü kullanıcı/istemci hangi versiyonun cevap verdiğini stream bitene kadar
  bilemezdi — metadata baştan gelirse UI anında gösterebilir, loglama da
  daha erken/güvenilir olur (generation hata verip yarıda kesilse bile
  versiyon bilgisi zaten gönderilmiş olur).
- **v2 içeriği**: v1'in aksine açık örnek ve "Kaynak/Sayfa/Paragraf kelimelerini
  kullanma" uyarısı olmadan, tek cümlelik kısa bir talimat: *"Answer using
  ONLY the given context. Cite sources as [s.PAGE/PARAGRAPH] after each
  fact. If you don't know from the context, say: '{not_found_phrase}'"*
  Bunun v1'den daha kötü/daha az güvenilir davranması **beklenen ve
  istenen** bir sonuç — Sprint 6'nın bulgusunu (açık örnek olmadan format
  takip edilmiyor) tekrar üreterek versiyonlar arası **gerçek** bir
  davranış farkı göstermek, yapay bir fark değil.
- **`{not_found_phrase}` placeholder**: Her iki template dosyasında da
  `NOT_FOUND_PHRASE` sabitinin yeniden yazılmasını önlemek için `.format()`
  ile doldurulan bir placeholder olarak kullanılacak — tek doğruluk kaynağı
  `app/llm/prompt.py:NOT_FOUND_PHRASE` olarak kalıyor.

## Test-First Plan

1. `tests/test_prompt.py` (mevcut testler regression için tekrar çalıştırılacak,
   yeni testler eklenecek):
   - `load_system_prompt("v1")`'in dosyadan okuduğunu ve Sprint 6'daki
     `SYSTEM_PROMPT_V1` içeriğiyle birebir eşleştiğini doğrula (taşımanın
     hatasız olduğunun kanıtı)
   - `load_system_prompt("v2")`'nin farklı bir içerik döndürdüğünü doğrula
   - `build_messages(..., version="v2")`'nin v2 prompt'unu kullandığını
     doğrula
   - Bilinmeyen bir versiyon istenirse (`version="v99"`) açık bir hata
     fırlatıldığını doğrula (sessizce v1'e düşmüyor)
2. `tests/test_generate.py`'a ekle — `stream_answer`'ın stream'in ilk
   event'i olarak `{"type": "metadata", "prompt_version": ...}` yayınladığını
   doğrula (fake Ollama ile, hızlı test).
3. `tests/test_config.py` (yeni) — `active_prompt_version`'ın `.env`
   üzerinden değiştirilebildiğini doğrula.

## Somut Kanıt Planı (gerçek Ollama)

`scripts/demo_prompt_versions.py` — aynı soru + aynı context, v1 ve v2 ile
ayrı ayrı gerçek Ollama'ya gönderilecek, iki cevap ve `check_grounding`
sonuçları yan yana raporlanacak. Beklenti (Sprint 6 bulgusuna dayanarak):
v1 tutarlı şekilde `[s.PAGE/PARAGRAPH]` formatını kullanırken, v2'nin format
konusunda daha az güvenilir olması — bu, versiyonlar arasında gerçek,
ölçülmüş bir davranış farkı olacak, iddia değil.

## Adımlar

1. `prompts/answer_v1.txt`'i Sprint 6'nın `SYSTEM_PROMPT_V1` metniyle
   birebir oluştur (placeholder'lı)
2. `prompts/answer_v2.txt`'i kısa varyasyonla oluştur
3. Kırmızı testleri yaz
4. `app/shared/config.py`'a `active_prompt_version` ekle
5. `app/llm/prompt.py`'ı dosyadan okuyacak şekilde refactor et
6. `app/llm/generate.py`'a `prompt_version` parametresi ve `metadata` event'i ekle
7. `app/api/chat.py`'ı güncelle
8. Testleri yeşile çevir — Sprint 6'nın testlerinin (`test_generation_e2e.py`
   dahil) hâlâ geçtiğini doğrula (regression yok)
9. `ruff check` temiz
10. `scripts/demo_prompt_versions.py` ile gerçek fark kanıtı
11. `docs/PLANNING.md` kapanış notu

## Definition of Done

- Aktif prompt versiyonu tek bir config değişikliğiyle değiştirilebiliyor
- Her response'ta kullanılan versiyon net şekilde görülebiliyor
- Testler ve lint temiz
