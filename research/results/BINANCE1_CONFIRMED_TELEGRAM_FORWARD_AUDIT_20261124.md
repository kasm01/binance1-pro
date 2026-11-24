# BINANCE1 — Telegram'a GERÇEKTEN gönderilen sinyaller / sonraki fiyat yolu denetimi

24 Kasım 2026. İnceleme anı Binance sunucu zamanı:
2026-11-24 18:30:59 UTC = 21:30:59 Europe/Istanbul.

**Kapsam:** systemd günlüklerinde Telegram API sonucu SENT olarak
kaydedilen 5 güçlü WATCH + 4 erken WATCH. Önizlemeler, DEDUPED,
PILOT_FILTERED ve GLOBAL_3MIN_GAP olayları **gerçek gönderim sayılmadı**.
ELSA 20:20 ve 20:21 iki gerçek teslimat olmakla birlikte aynı hareketin
tekrarıdır; bağımsız gözlem olarak sayılmamalıdır.

## Hesaplama yöntemi

- Bildirim zamanının hemen öncesinde kapanan 1 dakikalık Binance USD-M
  mumu referans alınır; fiyat bu mumun kapanış fiyatıdır.
- Sonraki yalnız tam kapanmış 1m OHLC mumlardan yönlü 1/3/5/15/30/60m
  kapanış getirisi, maksimum lehte (MFE) ve aleyhte (MAE) hareket ölçülür.
- LONG yönlü getiri = future close / reference close - 1;
  SHORT yönlü getiri = 1 - future close / reference close.
- Mumun high/low seviyeleri **gerçek alış/satış veya ulaşılabilir işlem
  sonucu değildir**. Yüksek ve düşük fiyatların mum içindeki sırası
  bilinmez. Spread/komisyon/kayma/fonlama ve kaldıraç ROI yoktur.
- Henüz zamanı dolmamış ufuklar PENDING, kesinlikle 0 getiri değil.
- Kaynak: 1 adet public Binance time + 8 benzersiz coin için 1m kline
  REST sorgusu. Yeni sürekli piyasa servisi veya Binance emir API'si yok.

## Gerçek erken Telegram bildirimleri

| Türkiye saati | Yön | Referans | 5dk yönlü kapanış | 5dk MFE / MAE | 15dk kapanış | Akış |
|---|---|---:|---:|---:|---:|---|
| 21:11 PIEVERSEUSDT | LONG | 3.0345 | +0.2439% | +0.8107% / -0.1582% | -0.4185% | FLOW_SUPPORTIVE |
| 21:15 SAHARAUSDT | LONG | 0.0057 | -0.3860% | +0.6491% / -0.4561% | -0.4386% | FLOW_MIXED |
| 21:19 MONUSDT | SHORT | 0.00983 | +1.4242% | +2.8484% / -0.2035% | PENDING | FLOW_SUPPORTIVE |
| 21:23 GUAUSDT | LONG | 0.03378 | +1.1249% | +2.8419% / -0.5921% | PENDING | FLOW_MIXED |

GUA fiyat yolu çift yönlüdür: ilk 1m içinde >=0.5% ters fiyat
hareketi görülmesine rağmen 5dk kapanış sinyal yönündedir.
PIEVERSE ve SAHARA 5m içinde bir miktar lehte hareket gösterip
15m sonunda sinyalin tersine kapanmıştır.

## Gerçek güçlü WATCH Telegram bildirimleri

| Türkiye saati | Yön | Referans | 5dk kapanış | 15dk kapanış | 30dk kapanış | Giriş katmanı |
|---|---|---:|---:|---:|---:|---|
| 20:20 ELSAUSDT | SHORT | 0.08373 | +0.1672% | -0.3464% | -0.3464% | ENTRY_PENDING (late >3 ATR) |
| 20:21 ELSAUSDT | SHORT | 0.08374 | -0.2150% | -0.2627% | +0.0239% | ENTRY_PENDING (last 1m unconfirmed) |
| 20:24 SYRUPUSDT | SHORT | 0.07257 | -0.7579% | -0.8130% | -1.0610% | ENTRY_PENDING (late >3 ATR) |
| 20:34 ZROUSDT | LONG | 1.0466 | +0.0860% | +0.5733% | +0.3917% | COST_REJECT shallow best quote |
| 20:37 AIOTUSDT | SHORT | 0.0834 | -0.2278% | +1.8945% | -2.2542% | ENTRY_PENDING (late >3 ATR) |

- SYRUP: sinyal yönüne göre 5m MFE -0.0138%, MAE -0.9646%;
  2. dakika içinde 0.5% ters fiyat hareketi görülmüştür;
  15m MAE -1.4744%.
- AIOT: ilk 2 dakikada >=0.5% ters hareket; 15m MFE +2.7818%,
  ancak 30m MAE -3.0695%. Zaman sıralaması bilinmeden kâr kilidi
  sonucu çıkarılamaz.
- ZRO: 15m +0.5733%; ancak orijinal public quote
  COST_REJECT/shallow_best_quote. Kâr görünmesi girişin
  uygulanabilir olduğunu kanıtlamaz.
- ELSA 60m getirisi +1.8392% / +1.8629%; bu, ilk 15m
  ters dönüşü veya iki sinyalin tek fiyat hareketi olduğu
  gerçeğini ortadan kaldırmaz.
- SYRUP 60m sinyal yönlü kapanış -0.1102%.
- ZRO ve AIOT 60m verileri inceleme anında henüz tamamlanmamıştı.

## Yorum / öncelikler

1. İlk 5m için 4 erken bildirimden 3'ü lehte, biri aleyhte kapanmış.
   Ancak tamamlanmış iki 15m erken olayının ikisi de ters kapanmış.
   Örneklem çok küçüktür; yüksek erken sinyal başarısı kanıtlanmadı.
2. Güçlü 5 WATCH'ın üçü 15m sonunda ters, ikisi lehte
   kapanmış. ELSA iki kez aynı hareket olduğu için bağımsız oran
   gibi yorumlanmamalı.
3. Yeni strong-WATCH bağlam/kotasyon filtresi bu beş eski
   bildirim örneğini geçmişe dönük olarak engellerdi.
4. GUA ve AIOT gibi fırsatlar için yalnız 5/15m kapanış değil,
   intra-interval adverse excursion ve ilk ters hareket süresi
   gereklidir.
5. Taker FLOW_SUPPORTIVE tek başına 15m devam garantisi değil:
   PIEVERSE örneği bunu doğrudan gösterir.
6. Şimdilik Telegram erken bildirimleri açık kalır, etiketi
   ERKEN İZLEME ve otomatik emir/READY kapalı. Kullanıcının
   talebi doğrultusunda ne canlı strateji motoru ne Telegram
   eşikleri bu denetimde değiştirilmiştir.
7. Sonraki analiz: en az birkaç gün canlı olay, 5/15/30/60m
   tamamlanma oranı, coin ve zaman bazlı bağımsızlaştırma,
   ufuk içi ters hareketin sırası için daha yüksek frekans
   veri, gerçek spread ve işlem maliyetleri.

Risk: Bu sonuçlar ticari yatırım tavsiyesi veya gerçek P&L değildir.
