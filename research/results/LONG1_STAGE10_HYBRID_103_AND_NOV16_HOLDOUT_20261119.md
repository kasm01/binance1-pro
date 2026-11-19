# LONG1 Stage10 — 103 sinyalin hibrit çıkış karşılaştırması ve 16 Kasım holdout

Tarih: 19 Kasım 2026. Yalnız LONG1 NEARUSDT, araştırma/NO-GO.
Binance işlemi, Redis production yazması, canlı servis başlatması veya ayar değişikliği yapılmadı.

## Yöntem ve güvenilirlik
Geliştirme: 11–15 Kasım döneminin 103 gerçek MODEL LONG olayı ve 8640 Binance arşiv 1m mumu. Önceki as-of katı, dengeli ve esnek araştırma giriş adayları SABİT tutuldu. Yeni girişler modeli tekrar eğitmedi, geçmiş LONG_TARGET etiketi bir giriş izni değildir. Her yeni karar yalnız tamamen kapanmış mumları kullanıyor, fiyat varsayımı SONRAKİ 1m OPEN. Gerçek 1m partial Entry, Sniper, Whale ve ortak Risk Master yeniden çalıştırılmadı. 60m maksimum pozisyon süresi, fiyat stopu %2,99, brüt ROI TP +%1,25, 3x kaldıraç ve gidiş-dönüş notional %0,08 maliyet (0,24 ROI puanı) varsayılıyor. Funding, spread/slippage, likidasyon, native stop gerçek fill, piyasa emri maliyeti ve exchange kuyruk sırası YOK.

Altı kademeli ROI ARM/giveback: 0,60/0,10; 0,95/0,15; 1,20/0,15; 1,65/0,20; 2,00/0,20; 2,50/0,20. Tamamlanan 1m CLOSE ile trailing tetiklenir, sonraki 1m OPEN tahmini çıkıştır. Bar içinde stop/TP ikisi görülürse stop öncelikli, açılış gap stop altındaysa gap fiyatı kullanılır. HYBRID altı kademe + %1,25 sabit TP; RUNNER sabit TP olmadan altı kademe.

## Geliştirme dönemindeki tek pozisyon simülasyonu

| LONG giriş araştırma profili | Çıkış | Açılan farazi | Toplam net ROI puanı | Sonuçlar |
|---|---|---:|---:|---|
| Katı | Sabit TP | 20 | -21,954 | 12 TP, 1 stop, 7 timeout |
| Katı | HYBRID | 20 | -18,795 | 10 TP, 3 trailing, 1 stop, 6 timeout |
| Katı | RUNNER | 19 | -17,685 | 12 trailing, 1 stop, 6 timeout |
| Dengeli | Sabit TP | 36 | -31,533 | 23 TP, 2 stop, 11 timeout |
| Dengeli | HYBRID | 39 | -17,331 | 17 TP, 13 trailing, 1 stop, 8 timeout |
| Dengeli | RUNNER | 37 | -6,115 | 28 trailing, 9 timeout |
| Esnek | Sabit TP | 43 | -44,475 | 30 TP, 4 stop, 9 timeout |
| Esnek | HYBRID | 47 | -24,551 | 24 TP, 13 trailing, 2 stop, 8 timeout |
| Esnek | RUNNER | 45 | -11,639 | 35 trailing, 1 stop, 9 timeout |

Toplam ROI puanları portföy sermaye getirisi değildir. Farklı çıkış süresi farklı yeni girişe yer açtığı için simüle açılış sayıları değişir. Aynı adaylara ait çiftli karşılaştırmalar da JSON'da korunmuştur. Geliştirme döneminde dokuz çıkış/profil birleşiminin HEPSİ negatif kaldı; bu sonuçla üretim ayarı değiştirilmedi.

## Bağımsız 16 Kasım tarih testi (frozen)

16 Kasım UTC ana LONG1 MODEL-SCORE loglarında 419 değerlendirme, 24 LONG var. Binance NEARUSDT public 1m resmi ZIP dosyası (1440 mum) SHA256 CHECKSUM ile doğrulandı. 15 Kasım son mumları 16 Kasım analizinde yalnız geriye dönük 3m flow/return verisi için kullanıldı. Önceden dondurulmuş Katı Recovery şartları değiştirilmedi: maksimum beş tamamlanmış 1m recheck, body/range >=0,22, üst retrace <=0,35, 1m signed taker flow >=0,03, origin'e göre 3m flow iyileşmesi >=0,08, 3m return iyileşmesi >=0,10 yüzde puan, son 3m fiyat ve flow pozitif.

24 LONG sinyal -> 5 araştırma READY -> tek pozisyonla 4 farazi açılış.
- Sabit TP: 4/4 TP_FIRST, tahmini maliyet sonrası +4,0400 ROI puanı.
- Altı kademe HYBRID + sabit TP: yine 4/4 TP_FIRST, +4,0400 ROI puanı.
- Saf runner: 4/4 trailing NEXT_OPEN, +3,3039 ROI puanı.

Bu tek günlük holdout, 11–15 Kasımın negatif toplamını düzeltmez. İlk veri setinde exit/entry ayarlarının seçilmiş olması ve gerçek Sniper/Entry/PENDING/Whale kapılarının eksikliği sebebiyle bu test canlı kazanç garantisi veya gerçek LONG1 açılış sayısı değildir. 24 farklı LONG sinyali olup 419 MODEL değerlendirmesi tam gün ile aynı anlama gelmez; mevcut logların kapsadığı kısım hesaplandı.

## Risk sınırları ve sonraki geliştirme
- 7 geçmiş kullanıcı çakışma aralığının NO_TRADE kuralı korunuyor; simülasyonda yeni giriş yok.
- Aynı anda yalnız 1 sanal LONG; gerçek Binance pozisyonlarıyla birleştirilmiş kesin hesap simülasyonu değil.
- PENDING kimliği + 3m/5m yeniden doğrulama + as-of partial 1m body/retrace, whale ve Sniper kayıtlarının gerçek trace ile bağlanması gerekiyor.
- Alınan fiyat barları order-book derinliği, Whale orijinal metrikleri ve native stopun fill sırasını içermez.
- Canlı LONG1 .env, Entry Confirmation, Master whale, Sniper, Contra-Trend, Native Stop, Risk Master canlı OPEN veto ve bütün servisler DEĞİŞMEDİ. SHORT1 kapsam dışı.
- Daha fazla bağımsız tarih ve gerçeğe yakın kâr kilidi/funding/slippage kontrolü olmadan production GO verilmemeli.

## Çıktılar
- research/results/LONG1_103_ASOF_HYBRID_SIX_TIER_REPLAY_20261119.json
- research/results/LONG1_NOV16_FROZEN_STRICT_HOLDOUT_20261119.json
- research/results/LONG1_NOV16_FROZEN_HYBRID_HOLDOUT_20261119.json
- research/trace/replay_long1_103_hybrid_exit_archive_v1.py
- research/trace/fetch_near_20261116_holdout_kline_v1.py
- research/trace/replay_long1_nov16_holdout_frozen_v1.py
- research/trace/replay_long1_nov16_frozen_hybrid_holdout_v1.py

Ham 16 Kasım ZIP yerel gitignore cache içinde; GitHub'a yüklenmez.
