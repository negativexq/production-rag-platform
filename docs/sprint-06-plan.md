# Sprint 6 — Grounded Generation + Streaming + Citations Planı

## Amaç
Reranked context'i kullanarak, sayfa/paragraf referanslı, streaming bir cevap üretmek.

## Doğrulanan Gerçek — Ollama Streaming API (varsayılmadı)

`curl http://localhost:11434/api/chat -d '{"model":"qwen2.5:3b-instruct",
"messages":[...],"stream":true}'` ile gerçek bir çağrı yapıldı. Sonuç:
newline-delimited JSON, her satır `{"message": {"role": "assistant",
"content": "<token>"}, "done": false}` formatında, son satır `"done": true`
ve toplam istatistikler. `/api/generate` (düz prompt) yerine `/api/chat`
kullanılacak — instruct model olduğu için system/user mesaj ayrımı daha
temiz bir prompt yapısı sağlıyor.

## Modül

```
app/llm/
├── ollama_client.py     # + stream_chat(messages, model) -> AsyncIterator[str]
├── prompt.py             # SYSTEM_PROMPT_V1, NOT_FOUND_PHRASE, build_context(), build_messages()
├── grounding.py           # check_grounding(answer, chunks) -> GroundingResult
└── generate.py            # answer_question(): search -> rerank -> prompt -> stream -> grounding
app/api/
└── chat.py                # POST /chat, SSE (StreamingResponse)
```

## Kararlar

- **Citation formatı**: Context'teki her chunk `[Kaynak: Sayfa {page_number},
  Paragraf {paragraph_index}]` etiketiyle modele veriliyor. Modelden, her
  iddiadan sonra `[s.{page}/{paragraph}]` biçiminde (örn. `[s.3/0]`) bir
  referans eklemesi isteniyor — hem insan-okunur hem regex ile ayrıştırılabilir.
- **"Bulunamadı" davranışı**: Sistem prompt'u, context soruyu yanıtlamıyorsa
  modelin tam olarak `"I could not find this in the document."` cümlesini
  kullanmasını istiyor — sabit bir sentinel string, tespit edilebilir olması
  için.
- **Prompt versiyonu**: Bu sprint'te tek bir ilk versiyon (`SYSTEM_PROMPT_V1`)
  yeterli — Sprint 7'de versiyonlama (`prompts/answer_v1.txt` vb. dosya
  tabanlı sisteme taşınacak) ekleniyor. Şimdilik kod içinde sabit string.
- **Grounding check başarısız olursa — KARAR: reddetmiyor, uyarı olarak
  işaretliyor.** Gerekçe: check post-hoc (plan metninde de böyle tanımlı) —
  streaming zaten kullanıcıya token token gönderilmiş oluyor, generation
  bitmeden grounding kontrolü yapılamaz (citation'lar cevabın içinde).
  Cevabı "reddetmek" ancak yeniden üretim (regenerate) ile mümkün olur ki bu
  sprint'in kapsamında yok. Bunun yerine: stream bitince ayrı bir SSE event'i
  (`event: grounding`) ile `{grounded: bool, ungrounded_citations: [...]}`
  gönderiliyor — istemci (ya da ileride UI) bunu bir uyarı olarak gösterebilir.
  Regenerate-on-failure, ileride ayrı bir mini-sprint olarak değerlendirilebilir.
- **Model instance'ları**: `CrossEncoderReranker` ve `SparseEncoder` pahalı
  (model yükleme ~9s) — FastAPI'de her istekte yeniden yaratılmayacak,
  `app/api/chat.py`'de process başına bir kez (lazy singleton) oluşturulacak.

## Test-First Plan

1. `tests/test_prompt.py` — `build_context()`'in sayfa/paragraf etiketlerini
   doğru formatladığını, `build_messages()`'ın system+user mesajlarını doğru
   ürettiğini doğrula.
2. `tests/test_grounding.py` — **DoD'nin istediği somut kanıt**: context'te
   sadece sayfa 2/paragraf 0 varken, cevapta kasıtlı olarak `[s.99/0]`
   (context dışı, uydurulmuş) bir referans geçen bir test yaz — `check_grounding`
   bunu `grounded=False` ve `ungrounded_citations=[(99,0)]` ile yakalamalı.
   Ayrıca geçerli bir citation'ın `grounded=True` verdiğini de doğrula.
3. `tests/test_ollama_client.py`'a ekle — `stream_chat()`'in mock'lanmış NDJSON
   stream'i doğru parse ettiğini, token'ları sırayla yield ettiğini doğrula.
4. `tests/test_generation_e2e.py` — **gerçek Ollama'ya karşı** (mock yeterli
   değil, plan bunu açıkça istiyor):
   - Gerçek bir soruya, gerçek context ile streaming cevap üretiliyor mu,
     birden fazla ayrı chunk halinde mi geliyor (tek blok değil — gerçek
     streaming kanıtı)
   - Üretilen cevaptaki citation'lar `check_grounding` ile context'e karşı
     doğrulanıyor mu (gerçek model çıktısıyla)
   - Context dışı bir soru sorulduğunda model "bulunamadı" cümlesini
     kullanıyor mu

## Adımlar

1. Kırmızı testleri yaz
2. `app/llm/prompt.py`, `grounding.py` implementasyonu
3. `OllamaClient.stream_chat()` implementasyonu
4. `app/llm/generate.py` (orkestrasyon) implementasyonu
5. `app/api/chat.py` (FastAPI SSE endpoint), `main.py`'a route ekle
6. Testleri yeşile çevir, `ruff check` temiz
7. Gerçek bir soru ile `/chat` endpoint'ini `curl` ile manuel doğrula
   (streaming gerçekten akıyor mu)
8. `docs/PLANNING.md` kapanış notu — grounding check başarısız olma politikası
   (reddetme değil, uyarı) ve gerekçesi netleştirilecek

## Definition of Done

- Streaming cevap gerçek zamanlı akıyor
- Her cevap doğrulanmış sayfa/paragraf referansı içeriyor
- Context dışı sorularda uydurma yapmıyor
- Testler ve lint temiz
