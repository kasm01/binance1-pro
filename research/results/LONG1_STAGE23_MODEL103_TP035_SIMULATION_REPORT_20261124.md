# LONG1 — Bulunduğumuz mimarinin simülasyon testi (Aşama 23)

24 Kasım 2026. NEARUSDT USD-M, 3x, 11–15 Kasım
arşivindeki 103 gerçek MODEL olayı üzerinden offline test.

## Mimari / kanıt zinciri

MODEL (103) → Stage13 research closed 1m + score,
contra, pending recheck (32 research READY) →
Stage20 origin sonrası kapanmış 3m/5m as-of fiyat
şartı (20) → Stage21 3m/5m/15m/60m flow şartı (0)
→ Stage18/19/22 gerçek MODEL→SIGNAL→CANDIDATE→INTENT,
partial 1m Sniper/Entry ve merkezi Risk Master
kanıtı (0 gerçek OPEN authority).

Bu tarihsel araştırma zinciri gerçek canlı MODEL/Intent
veya emir fill doğrulaması değildir. Stage13'teki
32 research READY, gerçek yeni Intent soyunu kanıtlamaz.
Özellikle 15m/60m negatif flow filtresi geçmiş
veriye bakılarak tasarlandığı için dokunulmamış
out-of-sample doğrulama değildir.

## Simülasyon varsayımları

- Kaynak: önceden saklanmış 819943 gerçek Binance
  aggTrade timestamp + unique ID sıralı gerçekleşen
  fiyat kayıtları (11–15 Kasım).
- Kaynak: arşivlenmiş 8640 kapanmış 1m mum, giriş
  seçimi gelecekteki bilgiyi kullanmıyor.
- Bir araştırma sinyali sonrası sonraki tam 1m OPEN
  fiyatından varsayımsal LONG giriş; **gerçek fill yok**.
- Sabit hedef 3x brüt ROI +%0,35, resting TP ideal
  limit dolumu yalnız fiyat eşiği dokununca varsayılır.
- 3x kaldıraç; roundtrip komisyon 0,24 ROI puanı;
  ekstra +0,10 ROI puanı maliyet duyarlılığı.
- Stop fiyatta -%2,99: yaklaşık -%8,97 brüt ROI.
  Stop fiyatı gerçekleşirse aggTrade ile ilk dokunuş;
  tek tick içindeki karşılaşmada stop önce.
- Maksimum bekleme 5 dakika ve 60 dakika ayrı
  değerlendirilir; süre dolarsa son aggTrade fiyattan
  çıkar. Gerçek likidite, spread, slippage, funding,
  latency, order placement, native stop emir doğrulaması,
  birden çok bot ve gerçek equity compounding yok.
- Bir pozisyon açıkken yeni pozisyon açılmaz, eski
  pozisyon kapandıktan sonra sıradaki aynı input
  aday yeniden değerlendirilir; filtre reddettiği
  olaylardan yeni MODEL üretilmez.
- Broker occupied-at-entry flag ile ikinci
  duyarlılık var; bu gerçek position lock değildir.
- 500 USDT / 250 USDT teminat kazançları, sabit
  margin bazında *işlem ROI puanları toplamı*ndan
  hesaplanır; 2.000 USDT portföy kârı değildir.

## Sabit TP +%0,35, temel %0,24 ROI maliyeti

| Profil | 5m işlem | Kâr / Zarar | 5m net ROI puanı toplamı | 60m işlem | Kâr / Zarar | 60m net ROI puanı toplamı |
|---|---:|---|---:|---:|---|---:|
| Stage13 1m araştırma READY | 20 | 14 / 6 | -3,460451 | 19 | 17 / 2 | -4,191478 |
| Stage20 yeni kapanmış 3m/5m | 13 | 8 / 5 | -3,628773 | 13 | 11 / 2 | -3,510511 |
| Stage21 tüm fiyat ve para akışları olumlu | 0 | 0 / 0 | 0 | 0 | 0 / 0 | 0 |
| Tam gerçek kaynak ve ortak Risk Master GO kanıtı | 0 | 0 / 0 | 0 | 0 | 0 / 0 | 0 |

0 işlem yapan durum **kazançlı strateji** anlamına
gelmez. Tüm fırsatları kaybetmek mümkün. İlgili
gerçek stage21 flow filtresi canlıda aktif değildir.

## Maliyet ve sabit teminat duyarlılığı

| Durum | 5m net ROI puanı | 500 USDT sabit teminatla PnL USDT |
|---|---:|---:|
| Stage13, yalnız 0,24 ROI maliyet | -3,460451 | -17,3023 |
| Stage13, ilave +0,10 ROI maliyet | -5,460451 | -27,3023 |
| Stage20, yalnız 0,24 ROI maliyet | -3,628773 | -18,1439 |
| Stage20, ilave +0,10 ROI maliyet | -4,928773 | -24,6439 |

Tek +%0,35 TP dokunuşu tahmini +%0,11 net
ROI üretir; ilave 0,10 puan maliyette +%0,01
net ROI'ye düşer. 5m Stage13 kitapta 14 TP
dokunuşu ve 6 timeout net zarar vardır.
Elde edilen toplam net ROI -3,460451 puandır.
Stop 2,99% PRICE olduğu için stop gerçekleşirse
tek başına çok daha fazla kârın silinmesi mümkündür;
bu örnekte 5m ve 60m tek pozisyon kitaplarında
STOP_TICK gözlenmedi. Zararlar çoğunlukla hedefe
ulaşamayan timeout çıkışlarından geliyor.

Giriş anında mevcut broker LONG varmışsa bu
adayları eleyen duyarlılık: Stage13 5m 18
işlem 12 kazanç 6 zarar, net -3,680451
puan; Stage20 5m 12 işlem 7 kazanç 5
zarar, net -3,738773 puan. Bu ikinci
hesap gerçek merkezi Risk Master kilidi değildir.

## Karar / sınırlamalar

**NO-GO** canlı threshold/TP değişikliği.
Bu örnekte daha sıkı Stage20 giriş koşulu
pozitif net getiri göstermedi, Stage21 ise
bütün araştırma adaylarını eledi.
60m bekleme oranı yüksek kâr adediyle beraber
net toplam zararı çözmedi. Komisyon ve
TP asimetrisi kritik. Bir sonraki kontrollü
hipotez: 5m exit timeout zararlarını sınırlayan
daha erken regime-dependent lifecycle ile
fiyat/akış ayrışmasını yumuşak PENDING yapısını
koruyarak out-of-sample test etmek.

Ayrıca LONG1 ve SHORT1 için **tek merkezi Risk Master**
fail-closed emir güvenliği, tek coin eşzamanlı
pozisyon koordinasyonu ve Stage22 origin/fresh
Intent zinciri korunmalı. Canlı bot, Redis state,
servis ve exchange order yolu değiştirilmedi.
Bu sonuç geçmiş 5 günlük dönemi kullandığından
ileri performans taahhüdü vermez.

Kaynak:
- research/trace/replay_long1_stage23_model103_tp035_execution_proxy_v1.py
- research/trace/test_long1_stage23_model103_tp035_execution_proxy_v1.py
- research/results/LONG1_STAGE23_MODEL103_TP035_EXECUTION_PROXY_SIM_20261124.json
