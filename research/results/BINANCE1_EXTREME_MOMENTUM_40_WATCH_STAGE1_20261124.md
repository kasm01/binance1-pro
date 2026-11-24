# Binance1 40 coin — Aşırı yükseliş/düşüş ve zayıf sinyal baskılama, Aşama 1

Tarih: 24 Kasım 2026. Yalnız araştırma, izole test, otomatik emir yok,
Telegram gerçek mesajı yok, hiçbir servis başlatılmadı.

## İstenen davranış

- Toplam 40 farklı Binance USD-M Futures USDT perpetual coin,
  ilk 15 likit coin dışarıda. LONG1-4 ve SHORT1-4 AYNI 40 coin'de
  ayrı yönleri / kendi 10 coin gruplarını değerlendirir.
- Sert yukarı/aşağı hareketleri yakalamak için sırf 24 saatlik hacimde
  16-55 sırasına takılı kalma: likidite koşulunu sağlayan ama
  daha aşağı hacim sıralarında olan anormal hareketlere rezerv ayır.
- Zayıf/noisy hareketleri engelle, ama olağanüstü fiyat değişimini
  hacim artışı yok diye kaybetme: CAUTION_WATCH tut, READY verme.
- Güçlü hareket ilk kez algılandığında YALNIZ WATCH. İleride
  bağımsız Market Context, taker flow, spread, candle provenance,
  maliyet ve Entry Confirmation gerekli. Asla yeni işlem yetkisi yok.

## Geliştirilen modüller

scanner/universe_extreme_overlay_v1.py
- Binance exchangeInfo + ticker/24hr **elde edilmiş** public response
  verisinden saf/çevrimdışı fonksiyon.
- İlk 15, 24 saatlik işlem hacmi sıralamasına göre dışlanır.
- 40 benzersiz slotun en fazla 12'si, 24h fiyat değişimi mutlak
  >= %8 olan ve 24h quote-volume >= 5m USDT olan dikkat çekici
  coinlere ayrılır. Diğerleri hacme göre doldurulur.
- Böylece 24h hacimde ilk 55 dışında olsa bile aşırı
  yükselen/düşen varlık keşfedilebilir.
- Bu %8, likidite ve 12 slot ayarları **denenmemiş tasarım
  hipotezi**; ortalama kazanç/yanlış alarm için optimize edilmedi.
- 24 saatlik hareket BUY veya SHORT yön kararına TEK BAŞINA yetmez.
- 40 slot dolmak zorunda değildir; hızlı listelenen veya düşük
  hacimli coinler seçilmez.

scanner/extreme_momentum_v1.py
- Tek bir coinin tam kapanmış, kesintisiz, UTC hizalı
  65 adet 1m OHLCV barını **yalnız as-of** işler.
- Son 5m, 15m, 60m fiyat dönüşü ve tamamlanan 5m hacmin
  önceki 60m median hacme oranı ölçülür.
- Anormal hareket ölçeği yakın geçmişteki 1m fiyat
  volatilitesiyle kıyaslanır; tahmin edilen hareketin kendisi
  volatilite referansına sokulmaz.
- İlk aday filtre: 15m mutlak fiyat hareketi >= max(%0,75,
  iki volatilite birimi) ve 5m hacim genişlemesi >=1,6x.
- Yalnız fiyat gerçekten olağanüstüyse hacim zayıf olsa da
  EXTREME_CAUTION_WATCH olarak gösterilir (READY değil).
- LONG ve SHORT yönü 5m + 15m işaret uyumuna bağlıdır.
  60m yönü tersse sadece WATCH / caution.
- Süresi geçmiş bar, future/partial candle, eksik fiyat/hacim
  veya kesintili 1m akış = INSUFFICIENT_DATA fail-closed.
- Çıktı yalnız STRONG_WATCH / EXTREME_WATCH /
  EXTREME_CAUTION_WATCH / WATCH / SUPPRESSED_WEAK /
  INSUFFICIENT_DATA.
- Üretim için eğitilmiş/alfa kanıtlanmış model değildir.

## İlk NEARUSDT geçmiş kaynak denemesi

11–15 Kasım arşivinden 8640 adet tam kapanmış 1m mum
elde edildi. Her 5 dakikada bir (yeterli tarih
başlangıç penceresinden sonra) toplam 1715 as-of gözlem:
- 1656 SUPPRESSED_WEAK
- 53 STRONG_WATCH
- 3 EXTREME_WATCH
- 3 WATCH (karşı trend / dikkat)
- 0 gerçek OPEN, 0 gerçek Telegram send

Not: Coin yalnız detektörün eski arşivde test edildiği
NEARUSDT'dir; NEAR'in gelecekteki ilk 15 dışı
coin evreninde olacağı varsayılmamıştır. Tekrar
edilen 5m izleme dilimleri bağımsız trade değildir.
False-positive, net getiri, slippage ve fırsat
kaybı henüz incelenmedi. Bu test üretim başarısı
veya kâr vaadi değildir.

## Kritik sınırlar

- Aşırı yükseliş, aynı anda aşırı yükselmiş ve ters
  dönmeye yakın olabilir; yüksek hacim bir fırsat garantisi
  değil, aşırı risk/likidasyon uyarısı da olabilir.
- İlk 15'i dışlama şu an **24h Binance işlem hacmine** göre,
  piyasa değeri veya ölçülmüş BTC korelasyonuna göre DEĞİL.
- 24h anormal fiyatı, uzun dönem alıcı-satıcı para
  akışını, orderbook spread, funding, taker flow
  ve minimum contract size doğrulamayı tek başına sağlamaz.
- Selektör ve detektör YALNIZ saf fonksiyonlar.
  Sistemde sürekli 40 coin dinleme, canlı veri
  websocket, Telegram bildirimi ya da 8 strateji
  kararı bu aşamada başlatılmamıştır.
- telegram READY kanıt gerekliliği değişmedi.
  WATCH, doğrudan AL/SAT tavsiyesi değildir.

## Sonraki adım

Ortak fiyat/hacim snapshot cache (40 unique coin, bounded
websocket subscription / REST TTL fallback), signal
freshness and delisting saf guard, ardından LONG1/SHORT1
10'ar coin pilot WATCH / READY giriş doğrulaması;
Telegram'ın gerçek uçtan uca test mesajı ancak kullanıcı
açıkça istediğinde. 8 ayrı API veri döngüsü kurulmamalı.
