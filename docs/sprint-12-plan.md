# Sprint 12 (mini) — Observability in UI Planı

## Amaç

Jaeger'a hiç gitmeden, Streamlit UI'da her sorgunun pipeline adımlarının
(embed → retrieve → rerank → generate) gerçek süresini görmek.

## Sprint 8'den hatırlanması gerekenler

`docs/PLANNING.md` Sprint 8 kapanış notundan:

- Bir `/chat` isteği tek bir trace altında 6 span üretiyor:
  `chat_request` (kök), `load_models`, `embed_query`, `retrieve_hybrid`,
  `rerank`, `generate`.
- `generate` span'i, `stream_answer`'ın **tüm** gövdesini (her `yield` dahil)
  sarıyor — generator tükenene kadar kapanmıyor. Metadata event'i bu span'in
  içinden, span başladıktan hemen sonra yield ediliyor (Sprint 7).
- OTLP export `BatchSpanProcessor` ile arka planda, senkron değil — yani bir
  span kapandıktan hemen sonra Jaeger'da aranabilir olacağı **garanti değil**.

## Karar — Jaeger API'sini kim çağıracak: Streamlit, backend değil

Backend'e yeni bir proxy endpoint eklemek yerine, Streamlit doğrudan
Jaeger'ın kendi HTTP API'sine (`GET /api/traces/{traceID}`) bağlanacak.
Gerekçe:

1. **Jaeger zaten host'tan erişilebilir** — `docker-compose.yml`'de
   `16686:16686` port mapping'i Sprint 0'dan beri var, ek bir expose
   gerekmiyor. Gerçek `curl http://localhost:16686/api/traces/{id}` ile
   doğrulandı (aşağıda).
2. **Backend'e yeni bir route eklemek, bu isteğin tek amacı olan bir JSON
   proxy'si için gereksiz bir dolambaç olurdu** — backend'i büyütmenin
   (yeniden build, Sprint 10/11'de görüldüğü gibi ~50dk'ya kadar sürebilen)
   bir gerekçesi yok, çünkü Jaeger zaten kendi başına sorgulanabilir bir HTTP
   API sunuyor.
3. **Sprint 11 zaten bu deseni kurdu**: UI, backend'e SSE istemcisi olarak
   bağlanıyor (`app/ui/sse_client.py`), backend'i değiştirmeden. Aynı desen
   burada da geçerli — UI, Jaeger'a salt-okur bir istemci olarak bağlanacak
   (`app/ui/trace_client.py`), backend sadece trace ID'yi üretip metadata
   event'ine ekleyecek (bu, backend'in zaten yaptığı iş — span'i açması —
   üzerine minimal bir ekleme, yeni bir endpoint değil).

## Jaeger API'sinin gerçek response şekli (varsayılmadı, curl ile doğrulandı)

```
GET http://localhost:16686/api/traces/{traceID}
```

döndürüyor:

```json
{
  "data": [
    {
      "traceID": "...",
      "spans": [
        {
          "operationName": "embed_query",
          "startTime": 1786015366454776,   // mikrosaniye, epoch'tan
          "duration": 31186,                // mikrosaniye
          "tags": [...],
          ...
        },
        ...
      ]
    }
  ]
}
```

Gerçek bir trace ID ile (`6f3af6e0560f191c39f54f5e2e0ebd17`, önceki bir
sorgudan) doğrulandı — 6 span'in hepsi (`chat_request`, `load_models`,
`embed_query`, `retrieve_hybrid`, `rerank`, `generate`) bekleneni verdi.

## Kapsam

1. **Trace ID'yi taşıma**: `app/llm/generate.py`'deki `stream_answer`,
   `"generate"` span'i başladıktan hemen sonra (mevcut `metadata` event'inin
   yanına) `span.get_span_context().trace_id`'yi 32-karakterlik hex string'e
   çevirip (`format(trace_id, "032x")`, Jaeger API'sinin beklediği format)
   ekleyecek: `{"type": "metadata", "prompt_version": ..., "trace_id": ...}`.
   `generate` span'i kök değil ama aynı trace içinde olduğu için trace_id
   aynı — kökü (`chat_request`) ayrıca aramaya gerek yok.
2. **`app/ui/trace_client.py`** (yeni, saf/test edilebilir modül, Sprint 11
   desenine uygun): `fetch_trace_spans(trace_id, jaeger_url, client=None)` —
   Jaeger'dan span'leri çekip `SpanSummary(name, duration_ms, start_time_us)`
   listesine çeviriyor, `start_time_us`'a göre sıralı (pipeline adım sırası).
   **Retry**: export gecikmesi olabileceği için (yukarıda not edildi), trace
   boş dönerse kısa bir bekleme ile birkaç kez tekrar denenecek (varsayılan:
   5 deneme, 1s ara) — sonsuz değil, belirli sayıda deneme sonrası boş liste
   dönüp UI'da "henüz indekslenmedi" gibi bir durum gösterilecek, spinner'da
   asılı kalınmayacak.
3. **`streamlit_app.py`**: cevabın altında `st.expander("🔍 Pipeline
   trace")` — içinde `st.bar_chart` ile adım adım süre (ms), altında Jaeger'a
   doğrudan link (`http://localhost:16686/trace/{trace_id}`).

## Test-First Plan

1. `tests/test_generate.py`'a yeni test: gerçek bir `InMemorySpanExporter`
   ile üretilen `generate` span'inin `trace_id`'si, metadata event'indeki
   `trace_id` alanıyla birebir eşleşiyor mu (zaten mevcut
   `_local_tracer_with_exporter` helper'ı kullanılacak).
2. `tests/test_trace_client.py`: `httpx.MockTransport` ile Jaeger API'sini
   simüle ederek (a) ilk denemede span'ler geldiğinde doğru parse edildiğini,
   (b) birkaç boş denemeden sonra span geldiğinde retry'ın çalıştığını, (c)
   tüm denemeler boş dönerse boş liste ile (hata fırlatmadan) çıkıldığını
   doğrula. Retry testlerinde gerçek `time.sleep` yerine `retry_delay_seconds=0`
   kullanılacak (testler yavaşlamasın).

## Doğrulama Planı (gerçek, iki kaynağı yan yana koyarak)

1. Backend yeniden build edilip (`docker compose build backend && docker
   compose up -d backend`) ayağa kaldırılacak.
2. `make ui` ile Streamlit başlatılacak.
3. Tarayıcıdan gerçek bir soru sorulacak.
4. UI'daki "Pipeline trace" panelinde görünen adım adım süreler not alınacak.
5. Aynı trace ID ile `curl http://localhost:16686/api/traces/{id}` (ya da
   Jaeger UI) çekilip span süreleri **birebir karşılaştırılacak** — varsayım
   değil, iki kaynak yan yana konacak.

## Adımlar

1. `tests/test_generate.py`'a trace_id testi (kırmızı) → `generate.py`'ye
   trace_id ekle (yeşil)
2. `tests/test_trace_client.py` (kırmızı) → `app/ui/trace_client.py`
   implementasyonu (yeşil)
3. `streamlit_app.py`'a expander + bar chart + Jaeger linki
4. `ruff check` temiz
5. Backend rebuild + gerçek tarayıcı doğrulaması + Jaeger ile çapraz kontrol
6. `docs/PLANNING.md` kapanış notu

## Definition of Done

- UI'da bir soru sorulduktan sonra, cevabın altında pipeline adımlarının
  gerçek sürelerini gösteren bir panel açılıyor
- Gösterilen süreler gerçek Jaeger trace'iyle karşılaştırılarak eşleştiği
  doğrulanmış (varsayılmamış)
- Testler ve lint temiz
