# LONG1 NEARUSDT — 2000 USDT ile çok küçük TP / erken kilit araştırması

20 Kasım 2026. Yalnız research, LONG1, 3x, NO-GO.
Gerçek Binance emirleri sıfır. SHORT1, .env, ENTRY,
Profit Lock, Stop, merkezi Risk Master değiştirilmedi.

## Çok küçük kar hedeflerinin maliyet sınırı

Hesap bakiye 2000 USDT; her işlem için:
- %10 başlangıç margin = 200 USDT, pozisyon nominali 600 USDT;
- %20 margin = 400 USDT, nominal 1200 USDT;
- %48 margin = 960 USDT, nominal 2880 USDT.
- Araştırma roundtrip taker toplam ücret varsayımı
  nominalin %0,08'i; 3x ROI'de **-0,24 yüzde puanı**.
- Bu oran gerçek kullanıcının Binance Futures VIP/BNB ve
  maker/taker seviyesi doğrulanmış ücret tarifesi değildir.
  Gerçek oran: Binance USDS-M Futures fee sayfası ve
  emir fill tipinden bağımsız kontrol edilmelidir.
- Funding, slippage, spread, mark price ve order book fill
  ekstra maliyeti burada bulunmuyor.

| Brüt ROI TP | Yaklaşık fiyat değişimi (3x) | Net ROI (ücret sonrası) | %10 margin net USDT | %48 margin net USDT |
|---|---:|---:|---:|---:|
| +0,30 | +0,1000% | +0,06 | +0,12 | +0,576 |
| +0,40 | +0,1333% | +0,16 | +0,32 | +1,536 |
| +0,60 | +0,2000% | +0,36 | +0,72 | +3,456 |
| +0,80 | +0,2667% | +0,56 | +1,12 | +5,376 |
| +1,00 | +0,3333% | +0,76 | +1,52 | +7,296 |
| +1,25 | +0,4167% | +1,01 | +2,02 | +9,696 |

Bunlar ideal TP fill varsayımıdır. TP seviyesinin
görülmesi ile limit emrinin gerçekten dolması aynı şey
değildir. Fiyat kayması ve piyasa emri masrafı küçük
hedefleri orantısız aşındırır.

## 32 Stage13 proxy entry, 11-15 Kasım 2026 geliştirme
Aynı girişleri as-of market context + closed 1m research
proxy ile seçtik. Bu veri setinde TP ve ARM varyasyonları
DENEYSEL olarak karşılaştırıldı; out-of-sample sonuç değildir.

| Profil | Sanal pozisyon | Toplam net ROI puanı |
|---|---:|---:|
| Sabit +0,40 ROI TP | 19 | -3,34148 |
| Sabit +0,60 ROI TP | 19 | -2,10715 |
| Sabit +0,80 ROI TP | 19 | +0,29285 |
| Sabit +1,00 ROI TP | 18 | -0,72347 |
| Sabit +1,25 ROI TP (mevcut research referans) | 18 | +2,52653 |
| +0,40 ARM / 0,10 giveback / +0,80 TP | 19 | -0,06558 |
| +0,50 ARM / 0,12 giveback / +1,00 TP | 18 | -2,01300 |
| Eski altı kademe ARM / +1,25 TP | 18 | +0,73700 |

Bütün kâr/zarar tutarları: 3x ROI yüzde puanları
toplamıdır, sermaye dönüşü veya Binance wallet PnL
değildir. Farazi girişlerin tamamının canlı MODEL->Intent,
1m partial Sniper, 5m Market Context ve Risk Master
geçişleri geriye dönük ispatlanmadı.
Önceden açık gerçek broker LONG saatlerini dışlayan
duyarlılık kontrolünde +0,80 TP sonucu -0,02715
ROI puanına düşüyor; her işlem başına ekstra
0,10 ROI puanı maliyette toplam -1,60715.

## ARM / TP fill gerçekliği
- ARM +0,40 ve giveback 0,10, ROI'nin +0,30
  üstünde kalacağına dair emir seviyesinde garanti değildir.
- Mevcut araştırma altı-tier trailing motoru full 1m
  CLOSE ile peak/geri çekilmeyi kontrol eder; tetiklenirse
  SONRAKİ 1m OPEN tahmini fill alır.
- Pozisyon +0,45 ROI görüp aynı dakikada negatife
  dönebilir; kapanış tabanlı trailing ARM bile
  çalışmayabilir. Tam güvence için canlı exchange-side
  reduce-only, korunmuş TP, fiyat tick-size/lot-size,
  aktivasyon/stop emir sırası ve order acknowledgement
  doğrulanmalıdır. Bu özelliklerin güvenli production
  entegrasyonu henüz test edilmedi.
- Reduce-only limit TP daha öngörülebilir bir
  hedef seviyesinde kapatma denemesidir; dolum garantisi yoktur.
  Korumasız software trailing ile kesin floor iddiası yasak.

## Kritik asimetri
Simülasyondaki fiyat stopu -%2,99, 3x
brüt -%8,97 ROI, ücretle -%9,21 ROI.
Brüt +0,40 ROI TP -> net +0,16 ROI:
yalnız TP/SL ile basit break-even kazanma gereği
9,21/(9,21+0,16) = %98,29.
Brüt +0,60 TP -> net +0,36 -> %96,24.
Brüt +1,25 TP -> net +1,01 -> %90,12.
TIMEOUT/partial fills/funding bu denklemi değiştirir.

## Pratik karar
1. +0,30 ROI gibi maliyete çok yakın hedefe production
   geçme; +0,40 / +0,60 da bu geliştirme verisinde
   negatif sonuç verdi.
2. Kilidi erken açmak gerekiyorsa +0,40 ARM/
   0,10 giveback ve +0,80 TP yalnız SHADOW
   araştırma adayı; bu model de -0,06558 ROI puan.
3. Daha fazla küçük kazanç öncesi başarısız giriş
   filtresi, kötü TIMEOUT/SL azaltma, gerçek intraminute
   execution ve broker emir kuyruk/funding modeli gerekli.
4. 2000 USDT hesabı %5-10 margin kullanmak
   tek stopun hesap üzerindeki zarar yüzdesini
   %48 margin kullanımından daha fazla sınırlar.
5. Örnek küçük TP sonucu karlı diye başlangıç
   margin %48'e veya daha yüksek kaldıraç yönüne
   geçme. SHORT1/central risk/entry unchanged.

Dosyalar:
- research/trace/replay_long1_micro_tp_stage19_v1.py
- research/trace/test_long1_micro_tp_stage19_v1.py
- LONG1_MICRO_TP_103_ASOF_PROFILE_COMPARISON_20261120.json
