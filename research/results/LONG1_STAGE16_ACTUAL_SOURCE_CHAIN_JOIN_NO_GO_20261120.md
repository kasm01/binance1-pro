# LONG1 Aşama 16 — Gerçek Stage6/7 parent fonksiyonları ile yeni Intent denetimi

20 Kasım 2026, TRT. Yalnız NEARUSDT LONG1, araştırma, NO-GO.
Google Cloud VM bağlantısı yeniden doğrulandı; bütün binance1
servisleri ve collector/timer süreçleri kapalı.

## Teknik boşluk
Aşama 14 tarihsel 103 MODEL ve 112 intent satırının 32
araştırma READY olayını tam MODEL→SIGNAL→CANDIDATE→Intent
parent kimliğiyle bağlayamadığını ortaya koydu.
Aşama 15 yalnız verilen attestasyon bayraklarının birbirleriyle
uyumunu sınayan saf bir doğrulayıcı oluşturdu.
Aşama 16'da doğrulayıcıya gerçek Stage6/7 köken
fonksiyonlarıyla hesaplanan SOURCE CHAIN sonucu eklendi.

## Yeni modül
orchestration/trace/long1_fresh_intent_source_chain_v1.py
fonksiyonları:
- exact_new_chain: gerçek candidate_parent fonksiyonuyla
  signal Redis stream ID ve parent_trace_id hash hesaplar;
  candidate üzerindeki source signal ID, model_evaluation_id,
  event ID ve wallclock close bucket değerleri eşleşmeli.
- candidate_intent_parent kullanılarak candidate Redis stream ID,
  candidate_id ve bütün upstream kimlik alanları yeniden
  türetilir; Trade Intent verisindeki aynı alanlarla eşleşmeli.
- Origin ve yeni MODEL kimliği farklı, origin ve yeni
  Intent kimliği farklı, NEARUSDT + long zorunlu.
- research_fresh_reentry: Aşama 15 fail-closed doğrulayıcıya
  sadece bu gerçek Stage6/7 kaynak fonksiyonlarının sonucu olan
  parent zinciri attestasyonunu sağlar. 3m/5m bağlamı,
  yeni 1m Sniper/Entry, PENDING expiration, broker flat ve
  Risk Master kayıtlarını bağımsız üretmez veya doğrulamaz.
- Hiçbir fonksiyon Redis, Binance veya dosya I/O yapmaz,
  gelecekteki sinyali kendi kendine oluşturmaz,
  emir açma hakkı vermez.

## İzole kanıtlar
- test_long1_stage16_real_source_chain_v1.py:
  Stage6 candidate_parent + Stage7 candidate_intent_parent
  gerçek fonksiyonlarıyla olumlu kaynak örneği.
- Sinyal stream ID, candidate stream ID, parent trace hash,
  source event, model ID, intent ID ve sembol/yön dahil
  **15 farklı bozma testi** -> eksik veya hatalı kaynak zinciri,
  NO_GO.
- Yeni MODEL / Intent yeniden kullanılırsa NO_GO.
- Eski PENDING EXPIRED kanıtı false ise NO_GO.
- Tüm örnek attestasyonlar sağlandığında bile
  live_order_authorized false.
- Aşama15 kimlik/expiry testleri PASS.
- Stage24 canlı Risk Master güvenlik engeli PASS.

## Önemli sınırlar
Buradaki olumlu test verileri sentetiktir; gerçek kayıtlarda
MODEL→SIGNAL→CANDIDATE→Intent eşleşmelerinin sonradan
kanıtlandığı veya 32 eski araştırma READY olayının gerçek
OPEN olacağı iddia edilmez. Model close bucket gerçek
tamamlanmış exchange 3m candle identity DEĞİLDİR.
Stage6/7 hash ve stream identity kaynak taşınması kanıtıdır;
kötü niyetli üretici veya order fill'in kriptografik kanıtı değildir.
Bir üst uygulamada gerçek transport snapshot ve market
verileri olmadan model-intent parent tamam demek yasak.

## Sonraki iş
Bu tamamen saf kimlik köprüsünü kullanıcı onayı sonrası
forward-only, default-off izleyiciye bağlayıp gerçek
yeni MODEL/Intent üretildiğinde aynı kimlikle olayların
geldiğini ölçmek; sonra full-1m Entry ve merkezi Risk
kanıtlarını ayrı aşamalarda birleştirmek.

Bu commit yalnız araştırma modülü/test/rapor içerir:
TradeExecutor, MasterExecutor ORDER yolu, LONG1 production env,
SHORT1, Redis üretim state ve servisler değiştirilmedi.
