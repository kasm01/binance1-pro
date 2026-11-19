# LONG1 — 11–15 Kasım Binance resmi geçmiş veri tamamlaması

Araştırma tarihi: 19 Kasım 2026. Yalnız LONG1 / NEARUSDT USD-M.
Binance public arşiv: https://data.binance.vision/
11–15 Kasım TRT aralığını tamamen kapsamak amacıyla 10–15 Kasım
UTC günlük dosyaları kullanıldı.

## İndirilen veriler
- Altı günlük 1m klines ZIP dosyası: 8.640 kapanmış 1m mum.
- Altı günlük aggTrades ZIP dosyası: 979.324 toplulaştırılmış işlem.
- Toplam 12 ZIP, 14.435.996 sıkıştırılmış byte.
- Binance'in kendi SHA256 CHECKSUM'ları 12/12 eşleşti; ZIP CRC geçti.
- VM: research/local_market_data/near_usdm_20261110_15/
- Ham arşiv GitHub'a yüklenmedi, yalnız yeniden üretme kodu ve rapor.

## Kapanmış 1m signed taker flow
- Kline quote volume ve taker buy quote volume kullanılarak:
  signed_flow = (2 * taker_buy_quote_volume - quote_volume) / quote_volume
- 8.640/8.640 1m için hesaplandı.
- aggTrades ile hacim karşılaştırması: 8.545 dakika uyumlu,
  95 dakika farklı; bu 95 aggTrades bölümü kesin dakikalık
  kanıt kabul edilmedi. Kline içindeki kendi taker buy alanı ana veri.
- Sıkıştırılmış kompakt araştırma çıktısı:
  near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz (~337KB).
- Girişten sonra oluşacak mum bilgilerinin karara sızmasına izin yok.

## LONG1 referans örnekleri
- Eski 103 ayrı MODEL LONG olayının 103'ünde geriye dönük
  tamamlanmış 1m mumlardan 3m/5m/15m/60m taker akışı hesaplandı.
- LONG_TARGET 11, LONG_AVOID 70, UNLABELLED 21, CONFLICT 1.
- LONG_TARGET 11 olayın 10'unda as-of 15m taker flow NEGATİF.
- Bu ölçüm önceki farklı kaynaktan gelen Market Context signed-flow
  metriğiyle aynı değil; önceki 48/89 eksik kaynak kaydı artık
  asıl as-of Binance piyasa verisiyle KARSILASTIRILABİLİR,
  fakat önceki whale kararı yeniden oluşturulmuş sayılmaz.

## Geri getirilemeyenler
- Botun kaydetmediği PENDING state, eski MODEL->SIGNAL exact kimliği.
- Anlık bid-ask derinliği ve whale kimliği: 1m kline/aggTrades içinde yok.
- Kaydedilmemiş 1m kısmi mum anlık body/retrace/Sniper progress;
  günün nihai mum high/low bilgisi sinyal zamanında henüz bilinmiyordu.
- Gerçek emir native stop dolumu, exchange execution ve spread'in
  tüm geçmiş anlık durumları bu public arşivde yok.

## Tekrar çalıştırılabilir işlemler
PYTHONPATH=. ./venv/bin/python research/trace/fetch_near_usdm_archives_20261110_15.py
PYTHONPATH=. ./venv/bin/python research/trace/build_near_archive_asof_flow_20261110_15.py
PYTHONPATH=. ./venv/bin/python research/trace/rebuild_long1_reference_flow_from_binance_archive_v1.py

Önerilen sonraki çalışma: 11 hedef LONG dahil 103 model olayında
tamamlanmış 3m/5m/15m as-of context ve 1m taker flow
ile LONG kararlarını konservatif net ücretli simülasyonda tekrar
karşılaştırmak. SHORT1 yok, canlı servis ve üretim ayarı değişmedi.
