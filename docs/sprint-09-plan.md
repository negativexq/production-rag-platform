# Sprint 9 — Evaluation (RAGAS/DeepEval) Planı

## Amaç
Sistemin retrieval ve generation kalitesini nesnel metriklerle ölçmek.

## Açık Soru Çözüldü — RAGAS mı DeepEval mi (gerçekten denendi, varsayılmadı)

### RAGAS: kullanılamaz durumda (bağımlılık çakışması, kod/tasarım sorunu değil)

`ragas` (hem güncel `0.4.3` hem eski `0.2.15`) kuruldu ve gerçek bir
`LangchainLLMWrapper(ChatOllama(...))` ile faithfulness/context precision
skorlamayı denedim. İkisi de aynı importda patladı:

```
ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'
```

Kök neden: `ragas` kendi içinde koşulsuz olarak
`langchain_community.chat_models.vertexai`'ı import ediyor, ama güncel
`langchain-community` (`0.4.2`) bu alt-modülü kaldırmış (Vertex AI desteği
ayrı bir pakete — `langchain-google-vertexai` — taşınmış). O paketi
kurmayı da denedim; `langchain_community` içindeki eski import yolu yine de
yok, üstelik `protobuf`'u OTel/qdrant-client'ın beklediği aralığın dışına
çıkarıp (Sprint 8'deki tracing kurulumunu bozma riskiyle) yeni bir çakışma
yarattı. `langchain-community`'yi eski bir sürüme (`0.3.27`) çekmeyi
denedim, bu sefer `langchain-core`/`langchain-openai`/`langgraph` zincirinde
çözülemeyen sürüm çatışmaları çıktı (`ContextOverflowError` import hatası).
**Sonuç: mevcut paket ekosisteminde (2026-08), RAGAS'ın langchain
bağımlılık zinciri iç tutarsız durumda — yerel Ollama desteğiyle ilgisi
yok, RAGAS'ı hiçbir judge modeliyle çalıştıramıyoruz.** Bu ortamda RAGAS
**kullanılmıyor**.

### DeepEval: mekanik olarak çalışıyor, ama küçük modelle güvenilmez

`deepeval` sorunsuz kuruldu ve import edildi (RAGAS'ın aksine
langchain'e bağımlı değil). `deepeval.models.OllamaModel` ile native yerel
Ollama desteği var. İlk denemede **`qwen2.5:3b-instruct`** judge olarak
kullanıldı:

- `FaithfulnessMetric` skoru **0.0** döndürdü, ama sentezlenen gerekçe
  *"there are no contradictions... does not deviate"* diyordu — yani metnin
  kendi açıklaması 1.0 gerektiriyordu. `verbose_mode=True` ile iç durum
  incelendi: claim için verdict `"no"` (= çelişkili) çıkmıştı ve
  `reason: null` idi (metrik `"no"` verdict'i için gerekçe istemesine
  rağmen). 3B model, açıkça tutarlı bir iddiayı yanlış "hayır" olarak
  işaretledi ve kendi iç JSON şemasını (verdict + reason) doğru dolduramadı.
  **Bu gerçek, ölçülmüş bir güvenilmezlik kanıtı** — iddia değil.

**Çözüm denendi**: sadece **judge** için daha büyük bir yerel model —
`qwen2.5:7b-instruct` (4.7GB, M2/16GB'de indirilebilir, disk/RAM kontrolü
yapıldı: 37GB boş disk, 16GB RAM). RAG'ın kendi generation modeli
(`qwen2.5:3b-instruct`, hız için) **değişmiyor** — sadece evaluation
harness'ının judge'ı 7B. Aynı test case'le tekrar denendi:

- `FaithfulnessMetric`: verdict artık `"yes"`, skor **1.0**, gerekçe
  tutarlı ("no contradictions present") — 3B'deki iç tutarsızlık düzeldi.
- `AnswerRelevancyMetric`: skor **1.0**, tutarlı gerekçe.
- **Latency**: faithfulness ~22s, answer relevancy ~11s (tek bir test case
  için — bu, judge'ın kendi içinde birden fazla LLM çağrısı yaptığı için
  3B'nin ~2-9s'lik tek-çağrı sürelerinden daha yüksek). 20 soruluk golden
  set için tahmini toplam: ~20 × (22+11)s ≈ **11 dakika** — bu, gerçek
  zamanlı serving'i değil, deploy-öncesi bir regression check'i etkiliyor,
  kabul edilebilir.

**Karar: DeepEval + `qwen2.5:7b-instruct` (sadece judge, RAG generation
modeli 3B'de kalıyor).** RAGAS bu ortamda tamamen devre dışı.

### Retrieval metrikleri için judge modeli gerekmiyor

Golden set'te her soru için **kesin** `(page_number, paragraph_index)`
referansları olduğundan (uydurma değil, gerçek PDF'ten), context
precision/recall klasik IR set-overlap formülüyle **deterministik**
hesaplanabiliyor — hiçbir LLM judge'a ihtiyaç yok. Bu hem daha hızlı hem
daha güvenilir (LLM judge'ın kendi hata payı devreye girmiyor).

## Golden Q&A Seti

`tests/fixtures/golden_source.py`: gerçek, doğrulanabilir bir kaynak PDF
üretiyor — kurgusal ama iç tutarlı bir "Nimbus Cloud Storage" destek
kılavuzu, 6 sayfa × 2 paragraf = 12 paragraf (hesap kurulumu, depolama
planları, dosya paylaşımı, senkronizasyon sorun giderme, faturalama/iade,
veri dışa aktarma/hesap silme). Gerçek parser ile test edildi: 6 sayfa ×
2 paragraf birebir doğru çıkıyor (varsayılmadı).

`tests/fixtures/golden_qa.json`: **20 soru**, gerçek içerikten türetildi:
- 16 tek-chunk soru (her biri tek bir `(page, paragraph)`'a karşılık geliyor)
- 2 çok-chunk sentez sorusu (iki farklı paragrafın birleşimini gerektiriyor
  — Sprint 6/7'deki "çoklu chunk" zorluğunu kapsıyor)
- 2 context-dışı soru (dokümanda hiç olmayan bilgi — Sprint 6'nın
  "bulunamadı" davranışını test ediyor, `expect_not_found: true` ile işaretli)

## Modül

```
app/evaluation/
├── __init__.py
├── retrieval_metrics.py    # compute_retrieval_metrics() — deterministik, judge yok
├── generation_metrics.py    # DeepEval FaithfulnessMetric + AnswerRelevancyMetric, judge=7B
└── harness.py                 # golden set'i yükleyip tam pipeline'ı çalıştıran, rapor üreten orkestrasyon
scripts/
└── run_evaluation.py           # CLI: harness'ı çalıştırıp raporu yazdırır/kaydeder
```

## Kararlar

- **Rapor formatı**: golden set'teki her soru için bir satır (soru id,
  precision, recall, faithfulness, answer_relevancy, grounded, geçen süre),
  altında agregat ortalamalar. JSON + insan-okunur özet ikisi de üretilecek
  (regression check için JSON, hızlı okuma için özet).
- **Karşılaştırma matrisi (bu sprint'in asıl hedefi)**: golden set, aşağıdaki
  geçici kararlar için gerçek veriyle çalıştırılacak:
  1. Sprint 1 chunk boyutu: 500/50 (mevcut) vs. daha küçük bir alternatif
     (örn. 200/20) — hangisi retrieval precision/recall'da daha iyi?
  2. Sprint 5 k/n: 20/5 (mevcut) vs. alternatif (örn. 10/3) — sonuç
     kalitesini ölçülebilir şekilde değiştiriyor mu?
  3. Sprint 7 prompt v1 vs v2 — hangisi faithfulness/answer relevancy'de
     daha iyi?
  En az biri bu sprint sonunda **kesinleştirilecek** (DoD'nin istediği gibi).

## Test-First Plan

1. `tests/test_retrieval_metrics.py` — deterministik precision/recall
   hesaplaması (yazıldı, geçti — judge gerekmiyor, hızlı).
2. `tests/test_generation_metrics.py` — DeepEval wrapper'ının doğru
   `LLMTestCase` oluşturduğunu, sahte/mock bir DeepEval metriğiyle
   (gerçek judge'a bağımlı olmadan) doğru skorları döndürdüğünü doğrula.
3. `tests/test_harness.py` — golden set yükleme, tek bir soru için
   uçtan uca metrik hesaplama akışını (mock retrieval/generation ile)
   doğrula.
4. **Gerçek e2e** (`scripts/run_evaluation.py` ile, otomatik pytest değil —
   ~11 dakika sürebileceği için CI/hızlı test suite'inin parçası
   yapılmıyor, ayrı bir manuel/regression komutu): golden set'in tamamı
   gerçek Ollama (3B generation + 7B judge) + gerçek Qdrant'a karşı
   çalıştırılıp rapor üretilecek.

## Definition of Done

- Golden set üzerinde çalıştırılan bir komut retrieval + generation
  metriklerini raporluyor
- En az bir önceki "geçici" karar (chunk boyutu, k/n, veya prompt
  versiyonu) gerçek veriyle kesinleştirilmiş
- Testler ve lint temiz
