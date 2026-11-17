# LONG1: ortak 11–15 Kasım referansından 12–14 Kasım trace örnek testi
Tarih: 18 Kasım 2026. Salt-okunur tarihsel dosya karşılaştırması.
Canlı servisler, emirler, Redis ve üretim eşikleri değişmedi.

## Kaynaklar
- `research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json`
- `research/results/LONG1_FUNNEL_TRACE_READONLY_V1_20261111_15.json`
- `research/results/LONG1_ACTUAL_OUTCOMES_REFERENCE_20261111_15.json`
- `research/results/LONG1_FOUR_FAST_REVERSALS_20261112_14_20261115.md`
- Stage6 trace kodu: `orchestration/trace/long1_lineage_v1.py` (geçmiş kayıtlarda mevcut değil)

## Test
`PYTHONPATH=. ./venv/bin/python research/trace/test_long1_shared_reference_trace_replay_20261112_14_v1.py`

- 12, 13, 14 Kasım yerel saatlerinde **89 MODEL LONG** kaydı var.
- User reference dosyasındaki 70 [start,end) aralığı ile bütün 89 kayıt
  baştan etiketlendi; mevcut funnel etiketiyle 89/89 eşleşti.
- 12 Kasım: LONG_TARGET 2, LONG_AVOID 18, UNLABELLED 11.
- 13 Kasım: LONG_TARGET 1, LONG_AVOID 22, UNLABELLED 1,
  CONFLICT_NO_TRADE 1.
- 14 Kasım: LONG_TARGET 4, LONG_AVOID 27, UNLABELLED 2.
- Toplam: hedef 7, kaçın 67, etiketsiz 14, çakışmalı 1.
- 12 Kas 01:36:16, 14 Kas 17:06:14, 19:06:12, 23:57:09
  model LONG sinyalleri LONG_AVOID; kapanış skorları sırasıyla
  .497407, .499819, .500040 ve .510074.
- Dört örneğin legacy context değerlendirmesi:
  PENDING, VETO_ADVISORY, PENDING, PENDING.
  Özellikle 19:06'daki iki entry PENDING log eşleşmesi
  HEURISTIC_SCORE_TIME'dır; exact parent trace / fill kanıtı değildir.
- Önceki 1m hipotetik replay'de 19:06 için +5 dakika ilk kapanış
  fiyatına göre 3x brüt ROI -%4,352 gösterilmişti; bu gerçekleşmiş
  borsa işlem P&L'si değildir.
- Yedi pozisyon sonucu telemetry row'u var (12–14 Kasım):
  4 UNLABELLED, 3 LONG_AVOID. LONG_AVOID üçlüsünde
  2 pozitif net ROI (%1,0799 ve %1,3622), 1 negatif net ROI
  (-%9,792). Bunlar farklı OPEN timestamp'lerine ait outcome
  telemetrisidir; 89 MODEL-score kaydına bire bir bağlanmamıştır
  ve bu çalışmada exchange fill bağımsız doğrulanmamıştır.
- Legacy 89 sinyalde `model_evaluation_id` ve
  `parent_signal_event_id` bulunmadığından yeni Stage6 exact
  model->signal->candidate join bu tarihsel arşive geriye dönük
  uygulanamaz. Exact historical stage6 linkage **0**, dürüstçe
  MISSING_OBSERVABILITY/UNLINKED kabul edilir.

## Yorum ve güvenlik
- Referans etiketleri retrospektif kullanıcı pencereleridir; işlem
  aç/kapat talimatı, eğitim etiketi, nedensel başarı ölçüsü veya
  zaman-saat filtresi değildir.
- Örnekler, negatif çoklu zaman dilimi rejimi için önceki
  Market Context / Contra-Trend / PENDING guard hipotezlerini
  destekleyebilecek araştırma adaylarıdır, kanıtlanmış performans
  artışı değildir. Özellikle kârlı LONG_AVOID pozisyonlar nedeniyle
  basit kategorik veto faydalı fırsatları da silebilir.
- Kod testi yeni emir, Binance API veya Redis üretim çağrısı yapmaz.
  Gelecekte gerçek trace chain için Stage7 Candidate->TradeIntent
  parent provenance zorunludur.
- LONG1 ve SHORT1 ortak live risk guard hâlâ kapalı (NO-GO).

## Çıktılar
- `research/trace/test_long1_shared_reference_trace_replay_20261112_14_v1.py`
- `research/results/LONG1_SHARED_REFERENCE_TRACE_STAGE6_REPLAY_20261112_14.json`
