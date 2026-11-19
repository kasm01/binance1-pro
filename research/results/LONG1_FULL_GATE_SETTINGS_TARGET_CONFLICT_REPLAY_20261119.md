# LONG1 — tam giriş ayarları, hedef fırsatlar ve çakışma senaryosu

**Dönem:** 11–15 Kasım 2026, yalnız LONG1 / NEARUSDT.
**Durum:** araştırma (shadow), canlı emir izni NO-GO, servisler başlatılmadı.

## Gerçek mevcut LONG1 ayarları

| Aşama | Etkin ayar | Risk ve gözlem |
|---|---|---|
| MODEL | Rolling quantile=0,965; minimum=0,491; lookback=480 | 11 hedef MODEL LONG kendi rolling eşiğinin üzerinde |
| Market Context | Adaptive enable=1; V2 ayrı shadow | V2 0 READY verdiği için canlı veto olarak kullanılamaz |
| Master whale | Contra veto=1; eşik=0,45 | Bazı hedef olaylarda Master karşı-whale olasılığı güçlü |
| SNIPER | 1m mum ilerleme aralığı %5–%60 | İki geç ve bir erken ret |
| ENTRY | kalite >=0,52; body >=0,15; retrace <=0,50; reject >=0,75 | Dört yönlü mum yok ve bir reversal ret |
| PENDING | Contra-Trend guard=1 | Bir yeniden kontrol bekledi |
| Risk | MASTER_MAX_POS=1, scale-in=0 | İki model olayında borsada LONG zaten açıktı |
| Lifecycle | dynamic_stop=1, catastrophic price=%3,5 | Araştırma 1m bariyer simülasyonu gerçek stopu taklit etmez |
| Final Safety | Shared Risk Master LIVE OPEN veto | **Değişmedi; NO-GO** |

## Girişin neden kaçırıldığı

- 44 hedef pencerenin 10 tanesinde 11 bağımsız MODEL LONG vardı;
  11/11 rolling model eşiğini geçti.
- 9 Trade Intent, 0 gerçek Binance açılışı.
- Dokuz niyetin terminal nedenleri: 1m yönlü mum eksikliği 4,
  Sniper erken 1, Sniper geç 2, güçlü 1m ters dönüş 1,
  PENDING recheck wait 1.
- İki MODEL olayı esnasında başka gerçek LONG zaten açıktı.
- 11 MODEL olayı için yakın TOP5 araştırma eşleşmesinde 18 satır var;
  eski MODEL→TOP5 kimlikleri EKSİK, eşleşme zaman + yuvarlanmış
  model skorudur; kesin sebep gibi kullanılmadı.

### Gerçek Master whale fonksiyonunun araştırma çalıştırması

| Whale karşı-yön eşiği | TOP5 test satırı | Veto edilen | Veto edilmeyen |
|---|---:|---:|---:|
| 0.45 | 18 | 10 | 8 |
| 0.55 | 18 | 10 | 8 |
| 0.65 | 18 | 1 | 17 |

0,45→0,55 bu satırlarda fark yaratmıyor. 0,65 yalnız 1 veto
bırakıyor; gerçek 3m/5m trend dönüşü ve 1m teyit olmadan
bu ayar CANLI için güvenli değildir. Bu test yalnız
MasterExecutor whale fonksiyonunun sonucu; diğer risk/giriş
kapılarının tümünü geçtiğini göstermez.

## 11 hedef model olayı üzerinde 1m fiyat yolu replay

- Model gözleminden sonraki ilk tamamen kapanmış 1m mum kapanışı
  varsayımsal LONG giriş fiyatı; devamındaki 1m mumlardan
  sabit TP ilk temas vs %2,99 fiyat SL ilk temas.
- 3x kaldıraç, en fazla 60m bekleme; aynı mum TP ve SL görülürse
  STOP önceliği; bar eksikse CENSORED.
- Gidiş-dönüş notional masraf %0,08 tahmini, 3x ROI maliyeti
  0,24 yüzde puan; spread, slippage, BNB, funding, liquidation,
  gerçek Sniper/Entry Confirmation, native/dynamic stop yok.
- Kullanıcının geriye dönük LONG_TARGET pencerelerinden seçilen
  11 model olayıdır: geleceği bilen etiketle seçim yanlılığı var.

| Shadow çıkış denemesi | 11 tekil olayda TP_FIRST | Tek pozisyonla varsayımsal açılış | Meşgulken atlanan | Net ROI puanı toplamı, hesap getirisi DEĞİL |
|---|---:|---:|---:|---:|
| TP %1,25 / ilk tam mum | 11 | 9 | 2 | +9.09 |
| TP %1,25 / +1 tam mum gecikme | 11 | 9 | 2 | +9.09 |
| TP %1,25 / +2 tam mum gecikme | 11 | 9 | 2 | +9.09 |
| TP %0,60 / ilk tam mum | 11 | 10 | 1 | +3.60 |
| TP %0,95 / ilk tam mum | 11 | 10 | 1 | +7.10 |

Bunlar gerçek piyasa emirlerinin dolumları değildir. %1,25 TP
varsayımsal fiyat temasına göre uygulanmıştır; bu tablodan
aynı kalitede gerçek ENTRY/STOP performansı çıkarılamaz.
Gerçek 10 LONG pozisyonla bu farazi 9 pozisyonu birlikte
taşıyan hesap simülasyonu yapılmadı.

## Tüm 103 model LONG üzerinde seçicilik maliyeti

| Sonradan verilmiş etiket | Model sayısı | 60m TP_FIRST | 60m SL_FIRST | NEITHER |
|---|---:|---:|---:|---:|
| LONG_TARGET | 11 | 11 | 0 | 0 |
| LONG_AVOID | 70 | 43 | 6 | 21 |
| UNLABELLED | 21 | 18 | 0 | 3 |
| CONFLICT_NO_TRADE | 1 | 1 | 0 | 0 |

LONG_AVOID 70 model olayında 43 sanal hedef, 6 sanal stop,
21 zaman içinde hedefsiz durum var. SL bariyeri 3x brüt
~-%8,97 ROI iken TP +%1,25. Kazanan oranını tek başına
optimize etmek, ödeme ve kuyruk riskini gözden kaçırır.
LONG_TARGET kullanıcı etiketi bir canlı alım izni DEĞİLDİR.

## Çakışan yedi saat — tek MODEL için varsayımsal LONG kâr/zarar

- Yedi çakışma aralığının altısında MODEL LONG yok.
- 13 Kasım 18:36:13 TRT model skoru rolling eşiğinin üzerinde,
  fakat zaten 13 Kasım 17:51 açılmış gerçek LONG hâlâ açık.
- Çakışmadaki bağımsız FARAZİ giriş: 2026-11-13T18:36:59+03:00,
  fiyat 3.447 NEARUSDT.
- %1,25 brüt TP ilk temas: 2026-11-13T18:45:59+03:00.
- Masraf varsayımı sonrası teorik **+%1.01 ROI**.
- Gerçek borsa emri YOK, portföyde ek LONG sayısı **0**.
- Çakışma veto kuralı ve tek pozisyon limiti korundu;
  varsayımsal kâr gerekçesiyle çakışmaya izin verilmedi.

## Gerçek açılmış 10 LONG pozisyonun tek tek sonuçları

| Gerçek açılış TR | Kullanıcı etiketi | Gerçekleşmiş fiyat P&L USDT | Tahmini komisyon/funding sonrası USDT | 1m en iyi brüt 3x ROI |
|---|---|---:|---:|---:|
| 11-11 15:17 | UNLABELLED | +0.032 | +0.005 | %1.678 |
| 11-12 03:06 | UNLABELLED | +0.112 | +0.086 | %1.506 |
| 11-12 04:12 | UNLABELLED | +0.128 | +0.102 | %0.668 |
| 11-12 17:13 | UNLABELLED | +0.144 | +0.117 | N/A |
| 11-12 17:45 | UNLABELLED | +0.120 | +0.096 | %1.149 |
| 11-12 20:05 | LONG_AVOID | +0.120 | +0.095 | %1.32 |
| 11-13 05:42 | LONG_AVOID | -0.872 | -0.896 | %0.789 |
| 11-13 17:51 | LONG_AVOID | -0.120 | -0.148 | %1.183 |
| 11-14 06:34 | LONG_AVOID | +0.144 | +0.120 | %0.534 |
| 11-15 01:14 | UNLABELLED | +0.140 | +0.113 | N/A |

- Binance 27 fill, 20 market order, 10 LONG açılış/10 kapanış;
  8 pozitif fiyat P&L, 2 negatif fiyat P&L.
- Gerçekleşmiş fiyat P&L -0.052 USDT;
  funding -0.00280688 USDT;
  yaklaşık BNB komisyonu 0.255806 USDT;
  tahmini net -0.311 USDT.
- 4 gerçek LONG açılışı LONG_AVOID penceresine denk geliyor;
  ikisi zarar etti. Etiketsiz pencerede 6 gerçek açılış var.

## Yalnız araştırmada değiştirilen ayarlar

- research/staging/long1_research_only_settings_v1.json
  mevcut konfigürasyonun ve shadow adayın ayrı sürümünü tutuyor.
- Araştırma adayı: whale eşiği 0,55; Sniper maksimum mum
  ilerlemesi 0,60→0,75; Entry quality 0,52→0,48;
  retrace max 0,50→0,60; reject retrace 0,75 değişmeden.
- Bu 4 parametrenin gerçek Entry/Order sonuçları, geçmişte
  tam kaynak 1m kalite telemetrisi eksik olduğu için BU replayde
  doğrulanmadı. Whale 0,55 ayrı testte etkisiz.
- 0,65 whale yalnız agresif shadow araştırma adayıdır, otomatik
  canlı ayar değildir. Zıt whale veto, Contra-Trend, Stop,
  Risk Master, single-position ve exchange stop yetkileri korunmalı.
- Gerçek üretim .env ve işlem kodlarına DOKUNULMADI.

## Sonraki araştırma

1. LONG1 1m quality/body/retrace ve Sniper candle progress
   özelliklerini PENDING attempt ile giriş öncesi eksiksiz kaydet.
2. Bu özellikleri as-of mumlardan eski örneklemde yeniden kur;
   parametre sweep ile hem hedef, hem kaçın ve farklı
   out-of-sample günlerini aynı replay altında değerlendir.
3. Gerçek net maliyet, kâr kilidi ve 30 saniye dynamic stop
   sırasına yaklaşan konservatif yürütme modeli olmadan
   LONG açma kapılarını productionda gevşetme.
4. Çakışan niyetler için gerçek merkezi coordination fail-closed
   kuralını ayrıca test et. Araştırma kullanıcı saatlerini
   kalıcı canlı saat filtresine çevirmek yok.

## Kanıt dosyaları
- LONG1_TARGET_CONFLICT_SHADOW_PROFILE_SWEEP_20261119.json
- LONG1_WHALE_THRESHOLD_045_055_065_STAGE_SHADOW_20261119.json
- LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json
- research/staging/long1_research_only_settings_v1.json
