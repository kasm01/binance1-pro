# LONG1 Aşama 14 — PENDING sonrası yeni niyet ve yanlış-saat giriş denetimi

19 Kasım 2026. Yalnız LONG1 NEARUSDT; NO-GO, tüm servisler OFF.
SHORT1, canlı parametre, execution risk ve native stop değiştirilmedi.

## Temel düzeltme: Gelecekteki toparlanma yeni işlem niyeti değildir

Aşama 13, geçmiş 103 MODEL LONG olayından 32'sinde tamamlanmış
3m/5m toparlanması ve 1m araştırma kalite kapısı bulmuştu.
Tek pozisyon sıralaması 18 farazi LONG göstermişti.
Ancak 30m recovery penceresi, gerçek LONG1 eski 1m PENDING
durumunun yaşadığını veya yeni MODEL/Intent üretildiğini göstermez.

Aşama 14, Redis'te tutulmuş 112 TRADE INTENT satırını ve
103 MODEL LONG zamanını recovery ile entry kararının arasındaki
yalnızca zaman pencerelerinde yeniden saydı. Eski MODEL ->
SIGNAL -> TOP5 -> intent exact ancestry yok. Aynı dakika
içinde bulunmak ilgili modelden türediğini kanıtlamaz.

| Retrospektif etiket | Stage13 READY | Toparlanma sonrası MODEL | Aynı pencere içinde intent | Tam kimlikle onaylanan OPEN |
|---|---:|---:|---:|---:|
| LONG_TARGET | 7 | 0 | 1 | 0 |
| LONG_AVOID | 18 | 1 | 1 | 0 |
| UNLABELLED | 7 | 1 | 2 | 0 |
| CONFLICT | 0 | 0 | 0 | 0 |
| TOPLAM | 32 | 2 | 4 | 0 |

32 READY olayının yalnız birinde hem bağımsız yeni MODEL hem
de TRADE INTENT aynı zaman penceresinde görünür: UNLABELLED.
Fakat parent trace bağlantısı kanıtlanmadığından bu da OPEN değildir.

## Stage13 portföyündeki 11 LONG_AVOID sanal LONG

- 11 araştırma girişi; 8 farazi TP/kârlı, 3 farazi
  60m TIMEOUT/zararlı. Gerçek Binance trade değildir.
- 10/11 adayda ilgili recovery->entry penceresinde yeni MODEL yok.
- 10/11 adayda aynı pencerede TRADE INTENT yok.
- Bir adayda yeni MODEL, farklı bir adayda eski TRADE INTENT
  bulunuyor; hiçbiri birlikte aynı tam parent lineage'e sahip değil.
- Bir adayın farazi giriş zamanı gerçekte borsada açık
  başka LONG ile çakışıyor.
- LONG_AVOID saatleri canlı blacklist/whitelist yapılmadı;
  amaç bütün sinyallere aynı giriş ve risk kurallarını uygulamak.
- Stage13'ün 18 farazi açılışının 2'si LONG_TARGET,
  11'i LONG_AVOID ve 5'i UNLABELLED. Hiçbiri bütün gerçek
  model->intent->entry->risk zincirini kanıtlamıyor.

## Teknik karar

- PENDING orijinal pending_origin_intent_id saklanmalı;
  yeni pending_recheck_intent_id ve yeni MODEL evaluation
  ancak gerçek kaynak tarafından üretildiğinde geçerli.
- Contra 3m/5m toparlanma, tek başına ENTRY READY izni değil.
- Eski 1m confirmation PENDING yeni mumda EXPIRED ise
  eski niyetten otomatik canlı emir oluşturulmamalı.
- Stage11/12 opt-in trace, niyet, PENDING attempt, as-of 3m
  mum zamanı ve gerçek 5m guard recovery gözlemini taşıyor.
  Özellik varsayılan kapalı; servis başlatılmadı.
- Sonraki adım: gerçek exact lineage ile forward-only shadow
  gözlemi. Whale, Sniper, Entry, PENDING ve merkezi Risk Master
  bağımsız onaylamadan GO yok.
- Stage13'teki 18 sanal OPEN ve +2,5265 ROI puanı gerçek
  emir fırsatı veya hesap getirisi değildir.
- Binance kline/aggTrades arşivi eski kısmi 1m/orderbook/
  PENDING state/eksik model-intent parent kimliğini yaratamaz.

## Kanıt
- research/trace/audit_long1_stage14_fresh_intent_avoid_103_v1.py
- research/trace/test_long1_stage14_freshness_audit_v1.py
- LONG1_STAGE14_FRESH_INTENT_AND_11_AVOID_AUDIT_20261119.json
- LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json

Hiç Binance POST, üretim Redis yazısı, gerçek emir,
canlı env değişikliği, strateji/stop/risk gevşetmesi yok.
