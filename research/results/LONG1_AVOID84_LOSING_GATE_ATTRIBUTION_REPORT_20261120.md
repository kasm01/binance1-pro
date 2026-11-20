# LONG1 — Zararlı AVOID adaylarına hangi kapı izin verdi?

20 Kasım 2026; NEARUSDT USDT-M 3x. Sadece araştırma.
11–15 Kasım katı as-of LONG_AVOID 84 sentetik adayın
sabit brüt %0,35 TP modelinde 48 tanesi net zararlı.
Bu 84 işlem gerçek broker emri veya doğrulanmış
MODEL→Intent soy bağı anlamına GELMEZ.

## Veri kaynağı ve kesin ayrım

Araştırma adayı: tamamen kapanmış yeşil 1m mumun
OPEN→CLOSE 3x ROI >=+%0,22 hareketi, sonraki 1m
OPEN varsayımsal giriş, 5m maksimum pozisyon.
MODEL yoksa araştırma taraması başlı başına
yeni bir trade adayı oluşturmuştur; gerçek executor
bu sinyale otomatik işlem açmış sayılamaz.

| Aşama | Gözlem | Doğrulama düzeyi |
|---|---|---|
| Research closed 1m trigger | 84/84 geçti | Kesin, araştırma girdisi |
| Research body/retrace/flow + price trend | 84/84 geçti | Kesin, araştırma hesaplaması |
| Gerçek MODEL event aynı dakika | 2/84 | Arşivlenmiş olay var, parent Intent yok |
| Rolling Model Score Gate | 2 olaya ait stage13 model_score_pass=True | Diğer 82 olayda ispat yok |
| Stage13 Contra Trend | Aynı iki olay CONTRA_WAIT_30M | Gerçek live guard yeniden kurulmadı |
| Canlı Entry Confirmation | 84/84 bilinmiyor | Mum ortası snapshot yok |
| Canlı Sniper / whale / Risk Master | 84/84 bilinmiyor | Yürütme kökeni doğrulanmadı |

## Araştırma filtresinin izin verdiği as-of değerler

- 1m OPEN→CLOSE brüt 3x ROI >= +%0,22 ve yeşil
- 1m body >=0,22 ve araştırma retrace <=0,35
- 1m signed flow >=0,03; 3m signed flow pozitif
- flow3 improvement >=0,08; 3m return pozitif
- 3m return improvement >=0,10 yüzde puan
- geçmiş 5 kapanmış 1m return pozitif

48/48 zararlı aday bu eşikleri geçmişti.
48 kaybın 41 tanesi sonradan ilk +%0,22
fiyat hareketine bile ulaşamadı. Dolayısıyla
araştırma geçiş koşulları, fiyatın devamı hakkında
yeterli güvenlik sağlamıyor.

## Native executor kaynak kodu / fiili .env

core/trade_executor.py kodundaki canlı Entry
Confirmation şu parametrelerle açıktır:

| Üretim ayarı (sadece okunmuş) | Değer |
|---|---|
| ENTRY_CONFIRM_ENABLE | 1 |
| ENTRY_CONFIRM_SHADOW | 0 |
| ENTRY_CONFIRM_MIN_BODY_RATIO | 0.15 |
| ENTRY_CONFIRM_MAX_RETRACE_RATIO | 0.50 |
| ENTRY_CONFIRM_REJECT_RETRACE_RATIO | 0.75 |
| ENTRY_CONFIRM_MIN_QUALITY | 0.52 |
| LONG_CONTRA_GUARD_ENABLE | 1 |
| LONG_ROLLING_MODEL_GATE_MIN | 0.491 |
| LONG_ROLLING_MODEL_GATE_MAX | 0.525 |
| SNIPER_ENTRY_MIN_CANDLE_PROGRESS | 0.05 |
| SNIPER_ENTRY_MAX_CANDLE_PROGRESS | 0.60 |

Native Entry Confirmation retro hesaplama ayrımı:
body = abs(px - open)/(high-low); retrace =
(high-px)/(high-open) (LONG için, directional span).
Kalite = 0,30 direction + 0,25 body_quality +
0,25 retrace_quality + 0,20 close_location_quality.
Araştırma retrace=(high-close)/(high-low) idi.
Native değerler üretimde KISMİ MUM üzerinden
hesaplanır. Burada yalnız kapanmış mumun bu
formüllerdeki **illustrative** görünümü var;
bu LIVE READY/SNIPER/ORDER ispatı DEĞİLDİR.
- 48 zararlı adayın 47 tanesi
  kapanmış mumun native shape/quality koşullarını
  sağlayacak görünümdeydi. Zarar doğrulanmış canlı
  Entry Confirmation açılışı değildir.

## Üç kötü örnek ve gerçek native retrospektif ayrım

| Giriş TR | Body | Research retrace | Native close-only retrace | Native close-only quality | 3m flow | 5m return % | %0,35 TP sonucu net ROI |
|---|---:|---:|---:|---:|---:|---:|---:|
| 11-14 01:01 | 0.846 | 0.000 | 0.000 | 1.000 | 0.425 | 0.143 | -3.243 |
| 11-14 18:28 | 0.833 | 0.167 | 0.167 | 0.925 | 0.092 | 0.344 | -3.320 |
| 11-14 19:27 | 0.308 | 0.308 | 0.500 | 0.813 | 0.174 | 0.321 | -3.023 |

14 Kasım 19:27: Native close-only retrace =0,50;
ENTRY_CONFIRM_MAX_RETRACE_RATIO=0,50 ise
kod >= karşılaştırmasıyla PENDING gerekir.
Fakat bu candle-close snapshot değeridir;
sinyal anındaki live candle snapshot bilinmediği
için gerçek geçmiş PENDING kararı iddia edilemez.

## Arşiv MODEL izi olan iki özel örnek

| Research giriş saati TR | Stage13 MODEL araştırma kararı | Aynı dakika Score Gate | %0,35 TP sanal net ROI |
|---|---|---|---:|
| 11-13 05:49 | CONTRA_WAIT_30M | [True] | -2.2528 |
| 11-13 17:55 | CONTRA_WAIT_30M | [True] | -0.7455 |

İki olayın arşivlenmiş MODEL skor araştırma geçişi
olsa bile CONTEXT yönü ters görüldüğü için
Stage13 kararları CONTRA_WAIT_30M olmuştur.
Bu olayları gerçek order accept diye sınıflamak
veya bunların PENDING korumasını gevşetmek yanlış.

## Yapısal kök neden ve sonraki doğrulama

1. Bu 84 adaya işlemi "izin veren" gerçek executor
   değil, MODEL kimliği gerektirmeyen synthetic
   CLOSED_1M_GREEN_ARM022 araştırma tetikleyicisidir.
2. Araştırma 3m ve 5m fiyat+flow toparlanmasını
   pozitif görürken daha geniş 15m satış rejimini
   kesin veto ile yeniden hesaplamamıştır.
3. 1m mum gövde ve kalite şekli güçlü olsa bile
   ilk +%0,22 ARM seviyesine gidemeyen kötü girişler
   vardır. Kısa sıçrama/sürdürme ayrımı gereklidir.
4. Önce gerçek archived MODEL→Intent→Stage kararlarını
   eksiksiz eşleştir; gerçek Live Entry Confirmation
   snapshot ve as-of 3m/5m/15m Market Context ile
   CONTEXT/PENDING/REJECT nedenlerini tekrar incele.
5. Research-only deneylerde ek kontrolleri
   yalnız bağımsız yeni tarihlerde değerlendirmek
   gerekir; kullanıcı işaretli saatler input olamaz.
6. Üretim gate veya ücretli veri/servis çağrısı
   DEĞİŞMEDİ. Risk Master / aynı coin tek pozisyon
   / final safety / native stop fail closed korunur.

Kaynak: research/trace/audit_long1_losing_avoid_gate_attribution_v1.py
Rapor JSON: LONG1_AVOID84_RESEARCH_VS_LIVE_GATE_ATTRIBUTION_20261120.json
