# LONG1 — 84 katı LONG_AVOID girişinde ARM ve kârdan dönüş analizi

Rapor tarihi 20 Kasım 2026; veri 11–15 Kasım 2026.
NEARUSDT Futures, 3x. Dondurulmuş 84 sanal giriş. Research ONLY.

## Girişlerin kimliği

Kaynak: LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json
development.book_strict.trades dizisinden cohort==LONG_AVOID
olan **tam 84 giriş**. Başlangıç sinyali kapanmış 1m
mumun koşulları, varsayımsal fill sıradaki 1m OPEN.
Geriye dönük LONG_AVOID etiketi, canlı emir açma veya
emir engelleme şartı değildir; bu 84 işlem geçmiş
tarama çıktısının istatistiksel alt kümesidir.

11–15 Kasım önceden kaydedilmiş resmi Binance aggTrade
arşivinden 819.943 satır sıralı trade basımı.
İşlem sırası: transact_time + agg_trade_id. Artık 1m
OHLC içinde fiyat önce yukarı mı aşağı mı gitmiş
sorusunu daha ayrıntılı inceleyebiliyoruz.
Fakat piyasa orderbook, bid/ask, native conditional stop
ve gerçek gerçekleşmiş broker fill verisi YOK.

## Aynı 84 giriş, aynı 5 dakika araştırma penceresi

| Çıkış modeli | Kâr | Zarar | Toplam net 3x ROI puanı |
|---|---:|---:|---:|
| Eski 5. dakika 1m CLOSE | 6 | 78 | -95.1794 |
| Yeni 0,22 / 0,35 altı kademe partial | 11 | 73 | -61.3081 |
| Yalnız altı kademe runner, partial yok | 11 | 73 | -62.0798 |
| Partial + 0,10 ROI pp ek execution cost | 6 | 78 | -69.7081 |

Eski 78 zarardan 6 tanesi yeni partial ile kazanca döndü;
eski 6 kazançtan 1 tanesi zarar oldu. Net +5 kazançlı
işlem artışı var. Toplam net ROI puanı iyileşmesi
 +33.8713;
ama strateji hâlâ negatif. Bu artış gerçek sermaye
getirisi veya dört bot toplam sonucu değildir.

## 78 zararlı girişte ilk 5 dakikanın maksimum ROI dağılımı

| Girişten sonraki en yüksek BRÜT 3x ROI | Pozisyon |
|---|---:|
| %0,22 altında | 41 |
| %0,22–%0,35 | 7 |
| %0,35–%0,50 | 7 |
| %0,50–%0,80 | 11 |
| %0,80–%1,00 | 3 |
| %1,00–%1,40 | 7 |
| %1,40 ve üzeri | 2 |

- 37 / 78 eski zararlı giriş ilk %0,22 ARM seviyesine ulaşmış.
- 30 / 78 eski zararlı giriş ikinci %0,35 ARM seviyesine ulaşmış.
- 77 / 78 giriş, önce bir tepe gördükten sonra tekrar giriş fiyatının altına düşmüş.
- Zararlı girişlerde medyan en yüksek brüt ROI: %0.1918.
- %0,22 seviyesine hiç ulaşmayan 41 işlemin erken
  ARM ile korunması mümkün değil; gerçek giriş kalitesi
  / ilk zarar kontrolü gerektiriyor.
- Teorik ilk net taban: 0,22 - 0,10 - 0,24 =
  **-%0,12 ROI**. ARM görülmesi net kâr garantisi değil.

## Eski 78 zararlı girişe yeniden uygulandığında

- Kısmi TP ile yeni kazançlı: 6;
  hâlâ zararlı: 72.
- Kısmi TP altında 78 işlemin toplam net ROI puanı: -61.830386.
- Eski 78 işlemin toplam net ROI puanı: -96.574784.
- Kısmi satış olayı: 55.
- Beş dakikalık tick-trailing çıkışı: 37;
  beş dakika sonunda kalan kapanışı: 41.

60 dakikalık pozisyon sürdürme duyarlılığında aynı
84 pozisyonun karşılaştırılması gerçekleşmiştir;
fakat girişler 5m çakışma kuralıyla seçildiği
için uzun vadeli 60m girişler birbirinin üzerine
binebilir. 60m sonuçları gerçek tek-pozisyon strateji
PnL olarak değerlendirilmemelidir.

## 78 zararlı giriş: tam saat / nereden döndü?

Aşağıdaki zamanlar Türkiye (UTC+03:00).
MFE: girişten sonraki en yüksek brüt ROI.
MFE sonrasındaki dip: tepe gerçekleştikten sonra
aynı 5 dakikada görülen en düşük brüt ROI.
Bunlar fiyat serisi gözlemleridir, elde edilebilir
çıkış garantisi veya geçmiş fill kanıtı değildir.

| # | Giriş TRT | MFE % | MFE zamanı TRT | MFE sonrası en düşük ROI % | Eski 5m net % | Yeni partial net % |
|---:|---|---:|---|---:|---:|---:|
| 2 | 11-12 01:09 | +0.081 | 11-12 01:09:01 | -0.812 | -0.971 | -0.971 |
| 3 | 11-12 01:19 | +0.000 | 11-12 01:19:00 | -1.541 | -1.618 | -1.618 |
| 5 | 11-12 05:32 | +0.333 | 11-12 05:32:28 | -1.664 | -1.821 | -0.065 |
| 6 | 11-12 06:00 | +0.673 | 11-12 06:02:31 | -0.336 | -0.576 | -0.139 |
| 7 | 11-12 06:10 | +0.000 | 11-12 06:10:00 | -1.093 | -1.249 | -1.249 |
| 8 | 11-12 06:29 | +0.844 | 11-12 06:32:32 | -0.253 | -0.493 | -0.278 |
| 9 | 11-12 06:58 | +0.421 | 11-12 07:01:31 | -0.421 | -0.577 | -0.139 |
| 10 | 11-12 07:05 | +0.253 | 11-12 07:05:19 | -0.843 | -0.746 | -0.139 |
| 11 | 11-12 07:29 | +0.084 | 11-12 07:29:02 | -1.688 | -1.422 | -1.422 |
| 12 | 11-12 08:23 | +0.425 | 11-12 08:25:32 | -0.679 | -0.410 | -0.138 |
| 13 | 11-12 08:30 | +0.679 | 11-12 08:31:32 | -0.340 | -0.410 | -0.062 |
| 14 | 11-12 08:39 | +0.085 | 11-12 08:39:03 | -1.185 | -1.256 | -1.256 |
| 15 | 11-12 11:35 | +0.173 | 11-12 11:35:39 | -0.864 | -0.845 | -0.845 |
| 16 | 11-12 11:50 | +0.346 | 11-12 11:51:10 | -0.692 | -0.672 | -0.058 |
| 17 | 11-12 12:04 | +0.086 | 11-12 12:04:14 | -0.692 | -0.845 | -0.845 |
| 18 | 11-12 15:52 | +0.175 | 11-12 15:52:04 | -1.485 | -1.550 | -1.550 |
| 19 | 11-12 19:19 | +0.000 | 11-12 19:19:00 | -1.307 | -0.763 | -0.763 |
| 20 | 11-12 19:48 | +0.614 | 11-12 19:49:33 | -0.877 | -0.152 | -0.135 |
| 21 | 11-13 00:35 | +0.000 | 11-13 00:35:00 | -1.304 | -0.762 | -0.762 |
| 22 | 11-13 00:50 | +0.175 | 11-13 00:50:10 | -2.620 | -2.598 | -2.598 |
| 23 | 11-13 01:06 | +0.352 | 11-13 01:07:58 | -0.617 | -0.240 | -0.134 |
| 24 | 11-13 03:23 | +0.000 | 11-13 03:23:00 | -0.878 | -1.031 | -1.031 |
| 25 | 11-13 05:49 | +0.088 | 11-13 05:49:00 | -3.763 | -2.253 | -2.253 |
| 26 | 11-13 06:29 | +0.089 | 11-13 06:29:00 | -2.391 | -1.923 | -1.923 |
| 27 | 11-13 06:45 | +0.357 | 11-13 06:45:58 | -1.605 | -1.489 | -0.133 |
| 29 | 11-13 07:18 | +0.722 | 11-13 07:21:19 | -1.624 | -1.593 | -0.024 |
| 30 | 11-13 07:54 | +0.182 | 11-13 07:54:06 | -1.186 | -1.335 | -1.335 |
| 31 | 11-13 12:01 | +1.277 | 11-13 12:01:55 | +0.000 | -0.155 | +0.386 |
| 33 | 11-13 12:53 | +0.000 | 11-13 12:53:00 | -1.030 | -1.098 | -1.098 |
| 34 | 11-13 13:18 | +0.855 | 11-13 13:19:07 | -1.539 | -1.608 | -0.060 |
| 36 | 11-13 17:55 | +0.084 | 11-13 17:55:03 | -1.516 | -0.745 | -0.745 |
| 37 | 11-13 18:07 | +0.338 | 11-13 18:07:21 | -2.961 | -2.101 | -0.062 |
| 38 | 11-13 18:29 | +0.172 | 11-13 18:29:02 | -2.326 | -0.843 | -0.843 |
| 39 | 11-13 22:49 | +0.085 | 11-13 22:49:02 | -0.761 | -0.832 | -0.832 |
| 40 | 11-13 22:59 | +0.000 | 11-13 22:59:00 | -1.436 | -1.169 | -1.169 |
| 41 | 11-13 23:08 | +1.100 | 11-13 23:10:07 | -0.254 | -0.494 | -0.062 |
| 42 | 11-13 23:36 | +0.085 | 11-13 23:36:10 | -1.018 | -0.749 | -0.749 |
| 43 | 11-14 00:25 | +0.599 | 11-14 00:27:01 | -0.342 | -0.154 | -0.060 |
| 44 | 11-14 01:01 | +0.086 | 11-14 01:01:01 | -3.347 | -3.243 | -3.243 |
| 45 | 11-14 03:43 | +0.260 | 11-14 03:44:45 | -0.607 | -0.413 | -0.136 |
| 46 | 11-14 05:01 | +0.175 | 11-14 05:03:49 | -0.525 | -0.765 | -0.765 |
| 47 | 11-14 05:59 | +0.439 | 11-14 06:00:57 | -0.351 | -0.064 | -0.135 |
| 48 | 11-14 06:22 | +0.530 | 11-14 06:25:07 | -1.060 | -1.124 | -0.028 |
| 50 | 11-14 10:04 | +0.089 | 11-14 10:04:00 | -0.800 | -0.862 | -0.862 |
| 51 | 11-14 17:09 | +0.091 | 11-14 17:09:00 | -2.007 | -1.699 | -1.699 |
| 52 | 11-14 17:46 | +1.110 | 11-14 17:46:25 | -2.683 | -2.553 | -0.129 |
| 53 | 11-14 18:02 | +0.000 | 11-14 18:02:00 | -2.502 | -2.093 | -2.093 |
| 54 | 11-14 18:28 | +0.093 | 11-14 18:28:01 | -3.920 | -3.320 | -3.320 |
| 55 | 11-14 18:44 | +1.399 | 11-14 18:46:43 | -0.093 | -0.053 | -0.128 |
| 56 | 11-14 19:00 | +0.560 | 11-14 19:00:58 | -2.425 | -2.106 | +0.054 |
| 57 | 11-14 19:27 | +0.096 | 11-14 19:27:07 | -4.319 | -3.023 | -3.023 |
| 58 | 11-14 19:34 | +1.356 | 11-14 19:37:01 | -0.194 | -0.046 | -0.124 |
| 59 | 11-14 19:41 | +0.865 | 11-14 19:42:06 | -3.362 | -2.738 | -0.125 |
| 60 | 11-14 19:51 | +0.192 | 11-14 19:51:06 | -2.117 | -0.721 | -0.721 |
| 61 | 11-14 20:12 | +1.067 | 11-14 20:12:16 | -0.970 | -0.725 | +0.167 |
| 62 | 11-14 20:59 | +2.498 | 11-14 21:02:17 | -0.480 | -0.720 | -0.125 |
| 63 | 11-14 21:22 | +1.062 | 11-14 21:25:33 | -0.676 | -0.723 | -0.008 |
| 64 | 11-14 21:32 | +0.096 | 11-14 21:32:00 | -1.339 | -0.910 | -0.910 |
| 65 | 11-14 23:01 | +0.193 | 11-14 23:01:00 | -1.838 | -2.078 | -2.078 |
| 66 | 11-15 02:01 | +0.506 | 11-15 02:01:09 | -2.836 | -2.164 | -0.027 |
| 67 | 11-15 03:41 | +0.000 | 11-15 03:41:00 | -1.958 | -0.925 | -0.925 |
| 68 | 11-15 04:07 | +0.000 | 11-15 04:07:00 | -5.162 | -3.020 | -3.020 |
| 69 | 11-15 04:20 | +0.099 | 11-15 04:20:00 | -4.868 | -2.723 | -2.723 |
| 70 | 11-15 04:50 | +2.037 | 11-15 04:50:52 | -1.732 | -1.157 | +0.274 |
| 71 | 11-15 06:36 | +0.477 | 11-15 06:38:15 | -1.241 | -1.481 | +0.061 |
| 72 | 11-15 07:01 | +0.095 | 11-15 07:01:01 | -2.481 | -1.958 | -1.958 |
| 73 | 11-15 07:21 | +0.287 | 11-15 07:21:22 | -1.914 | -2.154 | -0.125 |
| 74 | 11-15 07:28 | +0.479 | 11-15 07:30:28 | -1.438 | -1.678 | -0.125 |
| 75 | 11-15 10:00 | +0.000 | 11-15 10:00:00 | -2.101 | -1.577 | -1.577 |
| 76 | 11-15 10:10 | +0.000 | 11-15 10:10:00 | -1.528 | -1.195 | -1.195 |
| 77 | 11-15 10:23 | +0.191 | 11-15 10:23:16 | -0.669 | -0.718 | -0.718 |
| 78 | 11-15 10:29 | +0.000 | 11-15 10:29:01 | -0.859 | -1.004 | -1.004 |
| 79 | 11-15 15:32 | +0.562 | 11-15 15:32:16 | -1.404 | -1.550 | -0.015 |
| 80 | 11-15 15:45 | +0.282 | 11-15 15:45:13 | -0.846 | -0.992 | -0.127 |
| 81 | 11-15 15:55 | +0.658 | 11-15 15:57:30 | -0.376 | -0.334 | +0.056 |
| 82 | 11-15 16:21 | +0.188 | 11-15 16:21:27 | -0.939 | -1.085 | -1.085 |
| 83 | 11-15 16:52 | +0.189 | 11-15 16:52:06 | -0.850 | -0.996 | -0.996 |
| 84 | 11-15 17:11 | +0.669 | 11-15 17:11:27 | -0.096 | -0.336 | -0.011 |

## Yapısal risk ve kaynak sınırı

- Geriye dönük kullanıcı etiketleri canlı işlem whitelist
  veya saat veti değildir. 84 adayın çoğunun MODEL/Intent
  soy bağlantısı eksiktir: gerçekten emir açıldığı
  iddia edilemez.
- Bir pozisyon 5 dakika içinde %0,22 seviyesine
  ulaşırsa tetikleme imkânı görüldüğü söylenebilir;
  sıfır gecikmeyle aggTrade fiyatında kısmi fill
  varsayımı gerçekte iyimserdir.
- Ücret: roundtrip nominal %0,08 ≈ 3x ROI %0,24;
  gerçek VIP/maker/taker/BNB, funding, spread,
  orderbook sıra/ACK, mark price stop ve likidasyon
  modellemesi yok.
- 4 bot planında 500 USDT, 8 bot planında 250 USDT
  sabit LONG1 teminat payı korunur. 84 işlemin dolar
  karşılığı bir araştırma senaryosudur, toplam 4/8
  bot portföy getirisi değildir.
- Contra-Trend, yeni MODEL/Intent, tam market context,
  Whale, Entry Confirmation ve Risk Master kapıları
  üretimde değiştirilmedi. Servisler OFF.

Kaynaklar:
- research/trace/replay_long1_84_avoid_aggtrade_reversals_v1.py
- research/trace/test_long1_84_avoid_aggtrade_reversals_v1.py
- LONG1_84_AVOID_AGGTRADE_6STAGE_REVERSAL_ANALYSIS_20261120.json
