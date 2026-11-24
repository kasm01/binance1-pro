# Binance1 — Ortak 40 Coin Kapalı 1m Mum Motoru: İlk Pilot

24 Kasım 2026. Salt-okunur, tek seferlik public piyasa verisi pilotu. Canlı LONG1/SHORT1 servisleri kapalı. Binance emirleri yok; Telegram gönderimleri yok.

## Mimari

40 benzersiz Binance USD-M USDT perpetual coin. LONG1–4 ve SHORT1–4 aynı 40 coin evrenini farklı yönlerden değerlendiriyor, her stratejiye en çok 10 coin atanıyor. İlk 15 coin 24h USDT quote-volume sırasına göre hariç: **bu piyasa değeri veya BTC korelasyonu kanıtı değildir**. Extreme mover discovery ile 12'ye kadar slot, yeterli hacimli sert hareket edenlere ayrılıyor; diğerleri hacim sırasından tamamlanıyor.

- scanner/shared_market_snapshot_v1.py: ortak saf fonksiyon, tek sembol kaynağı iki yönde yeniden kullanılır. Tam kapanmış UTC 1m bar; 60000ms adım, exact close/open timestamps, no future/partial, gap/duplicate/bozuk OHLCV blokları. Eski universe metadata ve stale candle bloklanır. WATCH sonucu yönlere göre ayrıştırılır. READY veya ORDER authority verilmez.
- scanner/one_shot_shared40_pilot_v1.py: **varsayılan no I/O**; yalnız --fetch-public ile Binance public exchange time, exchangeInfo, ticker/24hr ve en çok 10 unique symbol için 70x 1m kline okur; keyless ve hiç emir yoktur. Limit=10 için 13 public API istek.
- Telegram Signal Center ve gerçek Entry/Market Context/Risk Master bu modüle bağlanmış değil. Ayrıca long ve short teknik yön kontrolü shared cache'den ayrı ayrı değerlendiriliyor.

## Bir kez gerçekleştirilen canlı public veri örneği

Komut: PYTHONPATH=. ./venv/bin/python scanner/one_shot_shared40_pilot_v1.py --fetch-public --limit 10

10 örnek coin: AIOTUSDT, PROMUSDT, ELSAUSDT, ZROUSDT, PHAROSUSDT, AKEUSDT, FLOCKUSDT, ATUSDT, USELESSUSDT, SYRUPUSDT.

- Kaynak exchange server time ile as-of.
- 9 SUPPRESSED_WEAK (fiyat zayıf veya 5m/15m yön uyumsuz).
- 1 STRONG_WATCH: **AIOTUSDT SHORT**, 15m fiyat hareketi **−6,7311%**, hacim genişlemesiyle birlikte gözlendi.
- LONG WATCH 0; SHORT WATCH 1; READY 0; gerçek ORDER 0; Telegram 0.
- Bu sonuç doğrudan short önerisi, emir, kâr/zarar kanıtı, pozisyon fill'i veya istatistiksel performans iddiası DEĞİLDİR. 10 coin tek anlık pilot, tüm piyasa değildir.

## Güvenlik ve teknik doğrulama

Sadece kamuya açık REST endpointlerine 13 GET, ücretli üçüncü taraf feed yok; Binance key kullanılmadı. Partial candle ve duplicate/gap/bozuk kaynak veri test edildi. 40 coin havuzu limiti ve aynı coin LONG/SHORT yön ayrımı kontrol edildi. Gecikmiş market data ve universe timestamp fail-closed. Mevcut Telegram komutleri kapalı ve üretim servisleri başlatılmadı.

## Sonraki adım

40 sembol için tek shared market data collector: düşük maliyetli bounded websocket subscribe + REST bootstrap, reconnection/backpressure, deterministic closed-bar cache, liste güncellendiğinde abonelik revizyonu, geçersiz/delist coine sinyal göndermeme. Önce LONG1/SHORT1 10'ar sembollü, salt WATCH pilotunu gözlemleyip maliyet/false positive/latency raporu çıkarma. Daha sonra gerçek giriş bağlamı ve maliyet kanıtı varsa READY değerlendirme. Otomatik emir yok, Telegram gerçek mesajı henüz yetkilendirilmedi.
