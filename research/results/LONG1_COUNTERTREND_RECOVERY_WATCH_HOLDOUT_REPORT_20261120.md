# LONG1: Contra-Trend Recovery Watch — kapalı mum as-of / 16 Kasım holdout

Tarih: 20 Kasım 2026. LONG1 NEARUSDT. Araştırma-only,
NO-GO, servisler kapalı. SHORT1, merkezi Risk Master,
LONG1 native stop, yürütme katmanı veya üretim env değişmedi.
Gerçek Binance emri, üretim Redis yazısı, ücretli yeni veri yok.

## Problem
11–15 Kasım'da LONG_AVOID saatlerinde 70 gerçek MODEL
olayının 28'i Contra-Trend, 23'ü Entry/PENDING, 1'i
MODEL score nedeni ile reddedilmişti. MODEL'den bağımsız
kapanmış 1m yeşil mum araştırmasında LONG_AVOID içindeki
581 brüt %0,22 ROI kapanış mumunun sadece 95'i
katı 1m + geçmiş 5m pozitif filtresini geçmişti.
Geçmiş HIGH görünmesi, girilebilir veya kârlı
pozisyon anlamına gelmez.

## İki ayrı, kullanıcı etiketi kullanmayan araştırma profili
Bütün sinyal inputları karar anında tamamen kapanmış 1m
mumlarına dayanır; geçmiş fiyat MFE veya sonraki 5m
karar girdisi DEĞİLDİR. Yeşil mum OPEN→CLOSE ile
brüt 3x +%0,22 ROI görmüş olmalı. Body>=0,22;
retrace<=0,35; 1m signed flow>=0,03;
3m signed taker flow>0, 3m return>0,
3m flow improvement>=0,08, 3m price return
improvement>=0,10 yüzde puan.

STRICT: geçmiş beş kapanmış 1m fiyat return >0.
CONTRA WATCH: aynı tüm kurallar korunur,
son beş kapanmış 1m fiyat return [-0,35%,0%)
aralığında; 3m fiyat+flow pozitife dönmüş olmalı.
Bu bir YENİ research WATCH göstergesidir, gerçek
5m Market Context ve Risk Master veto override değildir.

Kullanıcının geçmiş LONG_WANTED/LONG_AVOID saatleri
kural seçmez, sadece ex-post rapor etiketi işlevi görür.
İkisi çakışırsa NO_TRADE, global tek coin tek pozisyon
için aynı anda en fazla 1 farazi pozisyon:
her sinyalden sonra 5 dakika yeni giriş yok.
MODEL/Intent üretildiği iddia edilmez.

## Çıktı / bağımsız holdout

| | STRICT | STRICT+CONTRA WATCH |
|---|---:|---:|
| 11–15 Kasım bruto aday havuzu | 401 | 462 |
| 11–15 Kasım 5m nonoverlap sanal açılış | 305 | 347 |
| 11–15 Kasım 5m kapanışında toplam net 3x ROI puanı | -113,72364 | -131,28121 |
| 11–15 Kasım ücret sonrası 5m pozitif sayısı | 104 | 114 |
| 16 Kasım bruto aday havuzu | 81 | 99 |
| **16 Kasım nonoverlap sanal açılış** | **61** | **73** |
| **16 Kasım toplam net 3x ROI puanı** | **-6,04174** | **-10,12950** |
| 16 Kasım 5m pozitif | 25 | 30 |

Çıktı: her farazi giriş 1m CLOSE'tan sonraki 1m OPEN,
her çıkış beşinci tamamlanmış 1m CLOSE.
Ücret = -0,24 ROI puanı / işlem (3x);
slippage, spread, funding, order acknowledgement,
min lot ve borsadaki gerçek STOP/TP dolumu YOK.
Beşinci kapanışta çıkmak kâr kilidi mekanizması
DEĞİLDİR, yalnız yeni adayların dayanıklılığını ölçen
sabit bir araştırma karşılaştırmasıdır.

Bu tarama mevcut MODEL sayısını / gerçek yürütme
sinyallerini yeniden üretmez ve LONG1'in gerçek
5m Contra Guard kodu ile eşdeğer değildir.
Tamamlanmış 5x1m rolling return, canlı exchange
5m mumunun son onayını eşitlemez.
Hedef/avoid pencereleri üzerinde yapılan aynı
dönem geliştirmesi yanıltıcı iyimserlik yaratabilir;
16 Kasım bütün parametreleri sabit tutularak sınandı.

## Karar
Ek WATCH modelinin 16 Kasım net toplamı kötüleşti.
Bu nedenle production model gate, kontra guard veya
ENTRY eşiklerini gevşetme gerekçesi YOK.
En yüksek ROI fırsatları gelecekteki mum tepesinde
görülmüş olabilir ancak bunlara başlangıçta
entry kabiliyeti atfedilemez.
Önce araştırma için daha gerçekçi 1/3m exit,
ARM %0,22/0,35 ile partial take profit ve
as-of tick / orderbook fill duyarlılığını incele.
Karşılaştırmayı ücret ve stop sonrası risk, false-positive
ve Risk Master çakışması ile değerlendir.
İleride gerçek yeni MODEL/Intent, full closed 3m/5m
bağlam ve 1m Sniper/Whale/Entry + merkezi Risk Master
olmadan asla canlı OPEN yetkisi verilmemeli.

Kaynak:
- research/trace/replay_long1_countertrend_recovery_shadow_v1.py
- research/trace/test_long1_countertrend_recovery_shadow_v1.py
- LONG1_COUNTERTREND_RECOVERY_WATCH_NOV16_HOLDOUT_20261120.json
