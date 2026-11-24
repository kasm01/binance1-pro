# LONG1 Aşama 20 — Kapanmış 3m/5m mum kimliği ve PENDING güvenliği

24 Kasım 2026. NEARUSDT, 3x LONG1, research-only.
Kullanıcının Market Context → PENDING Revalidation → Risk Master
mimarisini bozmadan, gerçek zamanlı izin vermeyen saf bir
kapanmış-mum doğrulayıcısı geliştirildi.

## Kaynak

11–15 Kasım 2026 Binance arşivinden oluşturulmuş
8640 adet tam kapanmış 1m candle kaynağı ve önceden
kaydedilmiş 103 arşiv MODEL olayının Stage13 research kararları.
Bu 103 olay gerçek MODEL gözlemleridir; 32 research READY
olayı gerçek yeni Intent veya gerçekleşmiş trade DEĞİLDİR.

Yeni fonksiyonlar:
- Tamamlanmış 1m bar kimliklerini UTC 3m/5m bloklarına
  gruplayarak başlangıç ve kapanış milisaniyesini üretir.
- Barlar eksik veya source flag hatalıysa CLOSED saymaz.
- Kapanış anı as-of karar zamanından büyükse reddeder.
- PENDING origin MODEL timestamp sonrasında hem yeni kapalı
  3m hem de kapalı 5m mum gerektirir; aynı Intent ID tekrar
  kullanılırsa bloklar.
- Kapanmış 3m/5m mum yükselişi yalnız ARŞİV PROXY'dir:
  canlı structure, whale, taker flow, entry quality,
  last-book/partial candle veya Binance order-fill KANITI
  değildir. Pozitif proxy asla order authority üretmez.

## 103 arşiv MODEL olayının ayrımı

Önceki Stage13 kararları:
- 29 CONTRA_WAIT_30M
- 40 ENTRY_PENDING_EXPIRED
- 32 RESEARCH_READY_NO_REAL_INTENT
- 1 MODEL_GATE
- 1 CONFLICT_ORIGIN

Yalnız 32 research READY olayın eski 1m karar anında
bağımsız arşiv kaynağından 3m/5m kapanışları incelendi:

| Archive-only as-of 3m/5m görüntüsü | Olay |
|---|---:|
| MODEL saatinden sonraki yeni 3m/5m iki mum mevcut ve ikisi yükseliş yönünde | 20 |
| İki mumdan biri yükseliş yönünde değil | 8 |
| MODEL saatinden sonra kapanmış yeni 3m + 5m birlikte yok | 4 |
| TOPLAM | 32 |

Bunlar geçmişte emir açılabilir 20 pozisyon anlamına gelmez.
İki mumun pozitif olması gerçek Contra-Trend recovery değildir.
Stage13 model timestamp, gerçek PENDING store origin-Intent
timestamp'inin bağımsız kanıtı değildir. Yeni Intent ID'leri
burada yalnız denetleyicinin fail-closed davranışını
test eden sentetik kimliklerdir.

## Testler

- UTC-uyumlu 3m ve 5m tam kaynak bar kapanış saati.
- 5m kapanışından 1ms önce geleceğin fiyatını kullanmama.
- Eksik ya da değiştirilmiş 1m kaynak barı reddi.
- Kapanış zamanı karar anını aşarsa reddetme.
- Orijinal Intent'in yeniden kullanılmasını reddetme.
- Origin sonrası yeni kapalı 3m/5m yoksa reddetme.
- Yükseliş göstermeyen archive candle'ı proxy-recovery
  olarak kabul etmeme.
- Olumlu saf proxy sonucunda bile new MODEL/Intent
  ve Risk Master doğrulaması sağlanmış saymama.
- Stage18/19 kimlik denetimi ve Stage24 emir engeli
  regresyonları PASS.

## Kontrol sınırı

Bu modül mevcut production Entry Confirmation,
LONG Contra Guard, Sniper, Market Context veya
risk katmanındaki parametreleri değiştirmez.
Stage19'da gerçek kaynağı doğrulanmış yeni Intent
oluşursa bile buradaki tarihsel mum proxy'si canlı
kapanmış 3m/5m source proof yerine GEÇMEZ.

Sonraki iş: üretim karar anından gelen bağımsız
3m/5m kapalı candle kaynağı + PENDING attempt/origin
Intent kimliğini forward-only gözlem izine bağlamak.
Ondan sonra gerçek işlemlerin yanlış veya doğru
yetki aldığı olayların net getirisiyle ilişkilendirmek.
16 Kasım holdout daha önce profiller için
kullanıldığından yeni temiz doğrulama dönemi şart.

## Maliyet ve durum

İlave ücretli API, websocket, Redis collector,
daemon veya timer eklenmedi. Yalnız mevcut sıkıştırılmış
dosya ve önceden kayıtlı araştırma verisi kullanıldı.
Redis yazımı: 0; Binance emri: 0; gerçek canlı OPEN: 0.
Servisler duruyor. LONG2–4 / SHORT2–4 çoğaltılmadı.

Kod:
- research/trace/long1_stage20_closed_candle_pending_shadow_v1.py
- research/trace/test_long1_stage20_closed_candle_pending_shadow_v1.py
- research/results/LONG1_STAGE20_ASOF_3M5M_CANDLE_PENDING_EVIDENCE_20261124.json
