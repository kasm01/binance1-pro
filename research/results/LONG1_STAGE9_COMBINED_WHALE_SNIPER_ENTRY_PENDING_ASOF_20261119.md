# LONG1 Stage9 — Whale / Sniper / Entry Confirmation / PENDING as-of replay

19 Kasım 2026, TRT. Sadece LONG1 NEARUSDT. Araştırma; canlı emir yetkisi NO-GO.

## Tarihsel veri kapsamı
- 11–15 Kasım: 44 LONG_TARGET, 26 LONG_AVOID, 7 çakışma segmenti.
- 103 MODEL LONG, 112 intent, 10 Binance'de doğrulanan LONG açılışı,
  102 açılmayan intent. LONG_TARGET: 11 MODEL, 9 intent, sıfır gerçek açılış.
- Eski MODEL → SIGNAL → TOP5 tam kimlik zinciri yok; yalnız zaman+skor
  eşleşmeleri bulunuyor.
- Redis mikro-yapı geçmişi yalnız 14 Kasım 14:25 TRT sonrasını kapsıyor.
  Eski saatlerin 1m anlık body/retrace verileri eksik; tamamlandı sayılmadı.

## Whale veto: gerçek MasterExecutor fonksiyon testi
11 hedef MODEL yakınındaki 18 TOP5 kaydı üzerinde:
- 0,45 whale kontra eşiği → 10 veto.
- 0,55 shadow eşiği → yine 10 veto.
- 0,65 agresif araştırma → 1 veto.
0,55 bu örnekte pratik açılış farkı oluşturmuyor; 0,65'in diğer
piyasa rejimlerinde güvenli olduğu kanıtlanmadı.
Bu TOP5 kayıtları, eski MODEL close_id taşınmadığı için ilgili
MODEL olaylarıyla exact trace olarak eşleştirilmiş değildir.

## 15 Kas 00:18 MODEL LONG — as-of mikro-veri ile gerçek Entry metodu
Redis'ten 00:18:02–00:19:54 aralığında 12 tarihsel snapshot alındı.
Gerçek TradeExecutor._evaluate_long_entry_confirmation() fonksiyonu
test süreci ortam değişkenleri ile çalıştırıldı; üretim .env aynı.

| Profil | 12 snapshot OPEN | PENDING | BLOCK |
|---|---:|---:|---:|
| Mevcut quality=0,52, retrace_max=0,50 | 1 | 10 | 1 |
| Shadow quality=0,48, retrace_max=0,60 | 2 | 9 | 1 |

- 00:18:13–23: directional span yok → PENDING.
- 00:18:33: strong reversal → BLOCK.
- 00:19:03: iki profilde de READY. Mum progress ~0,058.
- 00:19:13: retrace=0,50; mevcut PENDING, shadow READY;
  progress ~0,230. Her iki snapshot Sniper nominal %5–%60
  mum zaman aralığında. Gerçek Sniper metodu tam replay edilmedi.
- Gerçek TradeExecutor._classify_long_pending_window() ile
  00:18:13 confirmation PENDING'in 00:19:03 yeni mumuna
  taşınırken EXPIRED olduğu doğrulandı. Yeni niyet olmadan
  READY anının emir yetkisi yoktur. 3m/5m recovery ve Contra-Trend
  bağımsız olarak doğrulanmadı.

## SHORT içermez: yalnız LONG fiyat yolu karşıolgusalı
İki 00:19 READY gözleminde fiyat yaklaşık 2,918 NEARUSDT.
Giriş dakikasını dışlayıp sonraki tam 1m mumlarda 60m boyunca
3x brüt TP ROI +%1,25, fiyat SL −%2,99 ile ilk temasa bakıldı.
Her iki senaryoda sonraki 00:20 mumunda TP_FIRST, farazi
+%1,25 brüt, %0,08 notional gidiş-dönüş ücret örneğiyle
+%1,01 ROI. Gerçek stop, emir dolumu, slippage, funding,
likidasyon ve diğer risk izinleri simüle edilmedi.
Sanal kârlılık, yeni Entry ayarının kârlılığı kanıtı değildir.

## Kontrol ve geliştirme kararı
- Whale 0,55 bu örnekte açılış sayısını değiştirmiyor.
- Entry retrace 0,60 bir ek as-of OPEN anı yaratıyor, ancak
  yeni bağımsız intent, 3m/5m context ve Risk Master olmadan
  bu olay emir açabilir diye yorumlanamaz.
- 1m confirmation PENDING'inin yeni mumda geçersizleşmesi korunmalı.
- Rolling gate, Contra-Trend, tek pozisyon, Native Stop, merkezi
  canlı NO-GO ve çakışmalarda NO_TRADE korunmalı.
- Sıradaki aşama: sinyalden sonraki as-of sniper progress,
  Entry quality/body/retrace, pending_attempt_id, 3m/5m
  kapanmış mum kimliği ve kontrolleri tek event-driven shadow
  kaydında üretmek; ancak servisleri otomatik başlatmamak.
- Eski diğer saatlerde mikro snapshot olmadığı için gerçek geçmiş
  A/B filtresi doğrulamasının kapsamı bir hedef olay ile sınırlı.
  Başka günlerde prospetif out-of-sample shadow testi gerekli.

## Dosyalar
- research/trace/replay_long1_actual_entry_gate_micro_asof_20261115.py
- research/trace/verify_long1_pending_continuity_asof_20261115.py
- research/trace/replay_long1_0019_ready_micro_future_price_20261115.py
- research/results/LONG1_ACTUAL_ENTRY_GATE_MICRO_20261115_0018.json
- research/results/LONG1_FULL_GATE_SETTINGS_TARGET_CONFLICT_REPLAY_20261119.md

Binance emir POST'u, gerçek üretim Redis yazması, bot servis
başlatması veya üretim config değişikliği yapılmadı.
