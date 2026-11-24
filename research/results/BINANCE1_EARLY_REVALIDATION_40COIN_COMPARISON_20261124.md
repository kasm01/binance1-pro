# BINANCE1 — Erken sinyal 1/3/5m yeniden doğrulama: 40 coinli sonuç karşılaştırması

24 Kasım 2026. Araştırma-only; otomatik emir ve READY kapalı.
40 adet Binance USD-M 1m kline REST + bir zaman isteği.
40/40 coin geçerli, her coinden son yaklaşık 12.5 saat tamamlanmış
1m OHLCV ve Binance taker alış hacmi.

## As-of metodoloji

- Mevcut erken hareket filtresi her CLOSED 1m mumunda değerlendirildi.
- Aynı coin ve yönde 60 dakika dedup; sonraki 30 dakika sonucu
  tamamlanmış **161** farklı aday raporlandı.
- 1., 3., 5. dakika kararında yalnız o dakikaya kadar kapanmış
  mum verisi kullanıldı. Geleceğe bakma yok.
- 15m/30m sonuçlar sinyal başlangıcından ve ayrıca kontrol
  dakikası kapanışından itibaren ayrıştırıldı.
- MFE/MAE mum high/low üzerinden teorik fiyat yolu;
  gerçekleştirilebilir işlem, kaldıraçlı ROI, fonlama, spread,
  komisyon veya slippage değildir.

## Tüm adaylar

15m: 161 adayın 103'ü ters kapanıyor (%64.0).
Ortalama yönlü kapanış -0.2286%, MFE +0.7562%, MAE -0.9837%.
30m: 161 adayın 81'i ters kapanıyor (%50.3),
ortalama yönlü kapanış -0.1197%.

## Beşinci dakika kontrolü

| Karar | Aday | 15m ters | 15m baştan yönlü kapanış |
|---|---:|---:|---:|
| CONTINUE_OBSERVE | 8 | 2/8 (%25.0) | +0.8836% |
| PENDING_RECHECK | 101 | 54/101 (%53.5) | +0.1272% |
| INVALIDATE_RESEARCH | 52 | 47/52 (%90.4) | -1.0907% |

KRİTİK: Yukarıdaki yüzdeler ilk 5 dakikanın zaten gerçekleşmiş
hareketlerini de içeriyor. Kontrol anından (5m kapanışı)
15m sonuna kadar gerçekleşen **ek** yönlü değişim:
- CONTINUE: 8 aday, ortalama -0.1077%, 5/8 ek dönemde ters.
- PENDING: 101 aday, ortalama -0.0844%.
- INVALIDATE: 52 aday, ortalama -0.0745%.

Bu nedenle CONTINUE gözlem sınıfı 5m sonunda kârlı giriş
öngörüsü değildir. INVALIDATE ise kötü ilk 5m fiyat yolunu
tanıyor, sonraki 10m düşüşünü kanıtlamıyor.

## 1. ve 3. dakika kontrolü

1m CONTINUE: 21 (7 ters, başlangıçtan 15m ort -0.3912%);
INVALIDATE: 20 (15 ters, -0.7849%);
PENDING: 120 (81 ters, -0.1074%).
1m CONTINUE grubunun 1m-sonrası 15m ek fiyat değişimi ortalama
-0.9234%; ilk 1m devamı sonraki yükseliş/düşüş için garanti değil.

3m CONTINUE: 8 (1 ters, +0.4711%);
INVALIDATE: 39 (34 ters, -0.7010%);
PENDING: 114 (68 ters, -0.1161%).

## İki zaman yarısı kontrolü

5m INVALIDATE:
- İlk yarı 17 adayın 14'ü 15m sonunda ters.
- İkinci yarı 35 adayın 33'ü ters.

5m CONTINUE:
- İlk yarı 6 adayın 2'si ters.
- İkinci yarı 2 adayın 0'ı ters.

Bu tek günün iki parçası, bağımsız out-of-sample test değildir.
CONTINUE grubunun n=8 olması ciddi istatistiksel sınırdır.
Coinler aynı piyasa koşullarında korelasyonlu olabilir.

## Canlı telemetri güncellemesi

- Watch outcome özetine revalidation_state_counts_by_minute eklenir.
- 1/3/5m CONTINUE/PENDING/INVALIDATE/UNVERIFIED olay sayıları
  aynı private status JSON'da görünür.
- Telegram erken/strong WATCH politikası değiştirilmez.
- Otomatik emir, READY, ek kalıcı API stream veya servis açılmaz.

Sırada: bağımsız günlerde sonuçları toplamak, kontrol anından
sonraki ileri fiyat davranışını analiz etmek ve komisyon,
spread, kayma, stop ve gecikme maliyetlerini hesaba katmak.
