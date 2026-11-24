# Binance1 — 40 coin / 8 strateji / Telegram manuel sinyal merkezi

24 Kasım 2026. Aşama: araştırma mimarisi, önizleme ve izole testler.
**Yeni botlar canlıya alınmadı. Otomatik AL/SAT emir sistemi yoktur.**
LONG1, SHORT1 ve merkezi risk / emir servisleri KAPALI kalır.

## Kullanıcı kararı

- **Toplam 40 farklı Binance USD-M Futures USDT perpetual coin.**
- İlk 15 büyük/likit coin istemiyor, BTC ile aynı yönde
  hareket etme eğilimi nedeniyle dışlamak istiyor.
- LONG1–4 strateji motoru: her biri 10 farklı coin'de
  yükseliş fırsatlarını araştırır.
- SHORT1–4 strateji motoru: **aynı 40 coin** üzerinde
  her biri 10 coin'de düşüş fırsatlarını araştırır.
- 80 adet farklı piyasa akışı yok: tek sembol veri
  önbelleği, 40 sembol, 80 yön-strateji inceleme slotu.
- Telegram'da WATCH / READY / INVALIDATED /
  TARGET_OBSERVED / STOP_OBSERVED gönderilir.
- Ticaret MANUEL. Bu proje için yeni sistemde
  exchange execution dependency, order emit ve API
  trade key kullanımını DEVRE DIŞI tut.

## İlk 15 kavramının kritik anlam farkı

Bu prototipte Binance USD-M /fapi/v1/ticker/24hr
quoteVolume (son 24 saatlik USDT işlemi) sıralamasının
**ilk 15'i** çıkarılır. Bu Binance piyasa değeri sırası
DEĞİLDİR ve ilk 15'in BTC korelasyonu yüksek olduğunun
kanıtı değildir. Sıralama kısa süreli spekülatif hacimle
çok hızlı değişebilir. Uzun vadeli gerçek tasarımda:
- Top15 by market cap seçeneği (harici veri kaynağı
  ve olası API maliyeti açıklanmalı);
- 7/30 günlük ortanca hacim sırası;
- Her coinin BTC ile rolling 1h return korelasyonu
  ve beta ölçümü, seçici yasaklamadan önce koşullu
  farkların doğrulanması
araştırılacak. Bunlardan hiçbiri bu aşamada
gerçek sayısal sonuç olarak ileri sürülmedi.

## İlk kamusal canlı metadata anlık önizleme

REST exchangeInfo ve ticker/24hr yalnız bir kez
anahtarsız okundu, gerçek emir üretilmedi. Evren:
TRADING + USDT quote + PERPETUAL + >=5m USDT
24h quote volume; sıralamada ilk 15 atlandı.
Bu liste **kalıcı konfigürasyon değil**, dinamik örnek:
- Dışlanan ilk 15: BTCUSDT, ETHUSDT, SOLUSDT,
  ZECUSDT, XRPUSDT, HYPEUSDT, NEARUSDT, DOGEUSDT,
  BNBUSDT, 1000PEPEUSDT, BLESSUSDT, EVAAUSDT,
  LISTAUSDT, ENAUSDT, SUIUSDT.
- LONG1/SHORT1 (aynı 10): ADAUSDT, MMTUSDT,
  UNIUSDT, LINKUSDT, PROMUSDT, WLDUSDT,
  PIEVERSEUSDT, ARIAUSDT, AVAXUSDT, ELSAUSDT.
- LONG2/SHORT2: AAVEUSDT, AIOTUSDT, PUMPUSDT,
  INJUSDT, CYSUSDT, TAOUSDT, LTCUSDT, ACEUSDT,
  FILUSDT, PAXGUSDT.
- LONG3/SHORT3: TRUMPUSDT, ONUSDT, ARBUSDT,
  AKEUSDT, VVVUSDT, BULLAUSDT, LITUSDT,
  BCHUSDT, QNTUSDT, XLMUSDT.
- LONG4/SHORT4: ONDOUSDT, INXUSDT, XMRUSDT,
  DOTUSDT, ZROUSDT, TRXUSDT, SAHARAUSDT,
  WLFIUSDT, FETUSDT, MUBARAKUSDT.

Bir coinin listedeki yeri LONG veya SHORT tavsiyesi
DEĞİLDİR. Hacim sıralaması tek başına sinyal değildir.
40'tan az kaliteli coin bulunursa zorla doldurulmaz.
Aynı yönde coin tekrar edilmez; 8 strateji farklı
setup'lar geliştirebilir, LONG/SHORT tek havuzu
ters yönden değerlendirebilir.

## Yeni sinyal mimarisi

                   PUBLIC MARKET DATA
               (40 distinct coin universe)
                          |
                 Shared OHLCV / flow cache
                          |
        +-----------------+------------------+
        |                                    |
  LONG1..LONG4                         SHORT1..SHORT4
  trend/pullback/                       downtrend/rally
  breakout/reversal                     fade/breakdown
        |                                    |
        +---------------+--------------------+
                        |
             NORMALIZED SIGNAL BUS
       WATCH / READY / INVALIDATED / TARGET / STOP
                        |
             CENTRAL SIGNAL VALIDATOR
       source/asof/candle identity, strategy setup,
       liquidity, spread, freshness, duplicate alert,
       contradictory LONG/SHORT and conflict veto
                        |
              TELEGRAM NOTIFY GATE
         chat/user authorization + opt-in send
                        |
               USER'S MANUAL DECISION

Central Risk Master remains a **future manual advisory**
layer, NOT automatically trusted executor. Legacy
TradeExecutor / order placement daemons must not
be launched via shadow_start.sh for signal center.

## Telegram eski kod audit

- tg_bot/telegram_bot.py: send-only currently; polling
  requested flag does NOT start polling. Existing
  send_message logs queued, which is not receipt evidence.
- tg_bot/commands.py: old sync CommandHandler code
  was not registered by main.py, used incompatible
  telegram.parsemode on PTB22.7; import corrected,
  legacy registration explicitly disabled to avoid
  accidental insecure/unsupported command service.
- tg_bot/guards.py: allowed list missing used to
  fail OPEN. Fixed to deny without allowlist.
- tg_bot/formatters.py: Python syntax error due to
  stray escaped f-string; corrected.
- tg_bot/message_formatter.py: invalid conditional
  float format when invoked; corrected.
- monitoring/alert_system.py: referenced nonexistent
  Notifier.send_message; fixed to safe sender method.
- core/notifier.py: asynchronous fire-and-forget
  existing behavior, not a verified delivery receipt.
- scripts/binance1_supervisor.sh /
  scripts/orch_watchdog.sh: independent legacy
  Telegram curl senders with separate cooldowns;
  no change; service OFF, new signal service will
  not start them.
- risk_manager + trade_executor: position open/close
  legacy notifications exist; new manual signal
  center must not instantiate the trade executor.
- Telegram bot token + chat configured in env;
  secrets never printed or added to Git.

## Yeni safe modules

- scanner/universe_40_v1.py: offline pure
  exchangeInfo/ticker-ranked 40 shared symbol selector.
- scanner/preview_universe_40_v1.py: no HTTP by default;
  explicit --fetch-public for 2 keyless public endpoints.
- tg_bot/signal_center_v1.py: strict schema,
  user-friendly informational messages, stale signal
  block, state-change dedup, dry-run by default.
  READY için ayrıca signal_asof_verified,
  market_context_verified, entry_confirmation_verified
  ve cost_check_pass gerçek kanıtlarından hepsi True
  gereklidir. Gönderimde sembolün ilgili botun
  10 coinlik bot_allocations listesinde bulunması
  zorunludur. Varsayılan boş listedeyken mesaj GİTMEZ.
- tg_bot/transport_v1.py: requires TWO explicit
  environment flags, authorized chat and verified
  successful Telegram API response before success.
- tg_bot/read_only_commands_v1.py: PTB22 async
  command service, default OFF. Only status, universe,
  bots, signals, risk, trades, positions, help, ping,
  whoami; NO trades or mutations. Mandatory chat
  allowlist, optional user allowlist.
- tests/test_manual_signal_center_v1.py: no network
  fake Telegram delivery, unauth, 40 symbols, NO ORDER.

## Varsayılan güvenlik

Telegram signal center send-only module:
READY ancak bağımsız market/entry/cost verisi
ileride güvenilir biçimde üretildiğinde oluşturulur.
Şimdiki kod veri sağlayan strateji motoru DEĞİLDİR:
kendi başına sinyal üretmez veya telegrama göndermez.
TELEGRAM_SIGNAL_CENTER_ENABLED=0
TELEGRAM_SIGNAL_CENTER_SEND_ENABLED=0
Command polling:
TELEGRAM_READONLY_COMMANDS_ENABLED=0
+ no --run => no connection.

No .env was modified and no systemd service created.
No actual Telegram test message sent. Enabling a
separate read-only command service later requires
ensuring it does not conflict with another poller;
existing main.py is send-only.

## Sıralı devam planı

1. **Sinyal merkezi mimari tasarımını onaylanabilir
   şekilde koru**, tüm eski emir daemons OFF.
2. 40 coinli ortak market cache, etkin veri sürümlerinin
   as-of quality checks, delist/new-listing eligibility,
   spread, min-age, ATR, market stress ve BTC
   korelasyon benchmark'ını implement et.
3. Sekiz ayrı stratejinin sinyal şemasını ve
   out-of-sample cost-aware testini oluştur;
   her strateji 10 coin, NO_TRADE doğal sonuç.
4. Yalnız test edilmiş sinyalleri Telegram'a bağla,
   dedup ve merkezi risk/conflict advisory katmanı,
   WATCH->READY->INVALIDATED durum geçişleri.
5. Sadece kullanıcı açıkça onaylayınca **ayrı**
   manual-signal-only servis/timer kur, Telegram
   gerçek tek test mesajını doğrula.
6. Geçmiş sinyalleri tahmin ile gerçek fill olarak
   karıştırmadan performans, gecikme, kaçırılmış
   fırsat, brüt/net ROI simülasyonu raporla.

Maliyet: tek coin verisini yeniden kullan, takipteki
40 sembol için çoklu time-frame bar aggregations;
sadece WATCH adayları için microstructure/depth.
24h symbol-wide ticker + exchangeInfo için rate
limit/TTL, retry/backoff kullan. Sekiz strateji
aynı pair için sekiz veri indirme döngüsü AÇMAMALI.
