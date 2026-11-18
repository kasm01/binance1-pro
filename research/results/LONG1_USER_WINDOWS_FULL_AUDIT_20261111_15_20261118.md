# LONG1 — 11–15 Kasım 2026 ortak saat pencereleri: eksiksiz açılış ve ret denetimi

Bu çalışma Binance Futures salt-okunur gerçekleşme, income ve emir
uç noktalarından, Redis geçmişinden ve kullanıcı referans dosyasından
üretilmiştir. Canlı bot/parametre değişikliği veya emir gönderimi yoktur.

## Tam huni ve tarihsel saat etiketleri

Kullanıcı referansında 44 açılmalı ve 26 açılmamalı zaman penceresi var.
Zıt etiketli 7 çakışma segmenti araştırmada kesin NO_TRADE/REJECT.

| Etiket | SIGNAL Redis olayı | CANDIDATE | TOP5 | Trade Intent | Açılan | Açılmayan |
|---|---:|---:|---:|---:|---:|---:|
| Açılmalı | 91 | 35 | 35 | 9 | 0 | 9 |
| Açılmamalı | 589 | 212 | 207 | 72 | 4 | 68 |
| Çakışma | 6 | 2 | 1 | 0 | 0 | 0 |
| Etiketsiz | 188 | 68 | 67 | 31 | 6 | 25 |
| TOPLAM | 874 | 317 | 310 | 112 | 10 | 102 |

103 bağımsız log MODEL LONG olayı ile 874 yayınlanmış SignalEvent
aynı birim değildir. MODEL LONG referansı: 11 açılmalı, 70 açılmamalı,
21 etiketsiz, 1 çakışma. Eski MODEL→SIGNAL tam trace ID zinciri eksik.
112 Trade Intent ise 112 ayrı yürütme log bloğuyla kesin eşleşiyor;
10 tanesi Binance orderId ve TradeIntent intent_id üzerinden kesin açılmıştır.

Açılmalı olan 44 pencerede açılış sayısı sıfır. 10
pencerede MODEL LONG, 3 pencerede
Trade Intent var. Açılmamalı 26 pencereden dördünde pozisyon açılmış.
İşaretlenmemiş aralıkta altı pozisyon açılmış. Yedi çakışmada sıfır açılış.

## Günlük işlem niyetleri ve gerçekleşmiş açılışlar

| Gün (TR) | İşlem niyeti | Gerçek açılış | Açılmayan |
|---|---:|---:|---:|
| 2026-11-11 | 16 | 1 | 15 |
| 2026-11-12 | 27 | 5 | 22 |
| 2026-11-13 | 28 | 2 | 26 |
| 2026-11-14 | 28 | 1 | 27 |
| 2026-11-15 | 13 | 1 | 12 |

## Açılmayan 102 Trade Intent neden açılmadı?

| Kaydedilmiş yürütme nedeni | Niyet |
|---|---:|
| entry_confirmation_strong_reversal | 40 |
| entry_confirmation_no_directional_span | 22 |
| sniper_window_passed | 16 |
| pending_recheck_wait_no_fresh_entry_decision | 9 |
| entry_confirmation_wait | 7 |
| sniper_window_early | 5 |
| execution_risk_no_available_balance | 2 |
| contra_trend_pending_after_entry_ready | 1 |
| TOPLAM | 102 |

Açılmalı pencerelerin dokuz niyetindeki gerekçeler:
- entry_confirmation_no_directional_span: 4
- sniper_window_passed: 2
- entry_confirmation_strong_reversal: 1
- pending_recheck_wait_no_fresh_entry_decision: 1
- sniper_window_early: 1

## 11 bağımsız MODEL LONG: Açılmalı referansının karşıolgusal sınırı

Açılmalı saatlerindeki 11 bağımsız MODEL LONG olayının tamamında
eski Market Context 60m first-hit araştırması TP_FIRST gösteriyor.
Bu bir gerçekleşmiş emir/nihai net kâr değildir: gerçek 1m giriş
onayı, giriş fiyatı, intrabar sıra, native stop ve maliyetler dışarıda.
Çakışma penceresindeki bir MODEL LONG olayı da TP_FIRST gösterse
bile çakışma emri kesin REJECT olarak ele alınır.

## Binance tarafından doğrulanan on LONG açılışı / kapanışı

| Açılış TR | Referans | Kapanış TR | Gerçekleşmiş fiyat P&L USDT | Yaklaşık masraf sonrası USDT | 1m en yüksek brüt 3x ROI |
|---|---|---|---:|---:|---:|
| 11-11 15:17 | Etiketsiz | 11-11 16:14 | +0.032 | +0.005 | %1.678 |
| 11-12 03:06 | Etiketsiz | 11-12 03:23 | +0.112 | +0.086 | %1.506 |
| 11-12 04:12 | Etiketsiz | 11-12 05:06 | +0.128 | +0.102 | %0.668 |
| 11-12 17:13 | Etiketsiz | 11-12 17:14 | +0.144 | +0.117 | Yok |
| 11-12 17:45 | Etiketsiz | 11-12 17:51 | +0.120 | +0.096 | %1.149 |
| 11-12 20:05 | Açılmamalı | 11-12 21:33 | +0.120 | +0.095 | %1.320 |
| 11-13 05:42 | Açılmamalı | 11-13 06:52 | -0.872 | -0.896 | %0.789 |
| 11-13 17:51 | Açılmamalı | 11-13 22:28 | -0.120 | -0.148 | %1.183 |
| 11-14 06:34 | Açılmamalı | 11-14 06:36 | +0.144 | +0.120 | %0.534 |
| 11-15 01:14 | Etiketsiz | 11-15 01:14 | +0.140 | +0.113 | Yok |

Sekiz kârlı fiyat kapanışı toplam +0,940 USDT; iki zararlı fiyat
kapanışı toplam −0,992 USDT. Gerçekleşmiş fiyat P&L **−0,052 USDT**.
Binance funding **-0.00280688 USDT**.
BNB komisyonu **0.00039586 BNB**.
Tarihi BNBUSDT perpetual 1h kapanışıyla yaklaşık komisyon
**0.255806 USDT**.
Masraflardan sonra yaklaşık **-0.310613 USDT**.
Komisyon dönüşümü yaklaşık olduğundan bu bir hesap özsermaye getiri
raporu veya borsanın kesin USDT-net komisyon kaydı değildir.

## Kaybeden iki işlem ve kâr kilidi için gözlem

### 2026-11-13T05:42:22+03:00
- Açılış LONG_AVOID saatinde, borsa fiyat P&L **-0.872 USDT**,
  yaklaşık masraf sonrası **-0.896 USDT**.
- Giriş sırasında m3 upfrac=0.333, 3m ortalama return=-0.001361;
  tamamlanmış flow15=-0.0170, flow60=-0.0889.
- Giriş ve çıkış dakikaları hariç tam 1m mumlarda en lehe brüt ROI
  **%0.789**, en aleyhe
  **%-11.485**.
- ARM ilk-temas seviyeleri: %0.6.
- Kapanış nedeni telemetrisi: dynamic_stop_confirmed.

### 2026-11-13T17:51:30+03:00
- Açılış LONG_AVOID saatinde, borsa fiyat P&L **-0.120 USDT**,
  yaklaşık masraf sonrası **-0.148 USDT**.
- Giriş sırasında m3 upfrac=0.000, 3m ortalama return=-0.003645;
  tamamlanmış flow15=-0.1556, flow60=-0.1149.
- Giriş ve çıkış dakikaları hariç tam 1m mumlarda en lehe brüt ROI
  **%1.183**, en aleyhe
  **%-9.042**.
- ARM ilk-temas seviyeleri: %0.6, %0.95.
- Kapanış nedeni telemetrisi: MISSING_SHADOW_OUTCOME_UNKNOWN_EXIT_REASON.

Her iki zararlı işlemde de pozisyon açılışında negatif 3m bağlamıyla
negatif flow15 ve flow60 aynı anda bulunuyor. Geçmiş on işlemde
bu bileşik R1-benzeri hipotetik filtre iki zararı, sıfır kârı işaretledi.
Bu yalnız geriye dönük hipotezdir; canlı filtremiz değiştirilmedi.
1m OHLC sıra/tick verisi olmadığından %0,60 ARM görülmesi
gerçek trailing çıkış ve net kâr garantisi değildir.

## Çakışan saatler: araştırma için kesin REJECT

| Tarih-saat (TR) | MODEL LONG | Trade Intent | Gerçek OPEN |
|---|---:|---:|---:|
| 11-12 12:15 – 11-12 12:18 | 0 | 0 | 0 |
| 11-13 18:36 – 11-13 18:38 | 1 | 0 | 0 |
| 11-13 22:40 – 11-13 22:42 | 0 | 0 | 0 |
| 11-15 01:38 – 11-15 01:43 | 0 | 0 | 0 |
| 11-15 06:42 – 11-15 06:48 | 0 | 0 | 0 |
| 11-15 07:10 – 11-15 07:15 | 0 | 0 | 0 |
| 11-15 09:26 – 11-15 09:28 | 0 | 0 | 0 |

Çakışmada 6 SignalEvent, 2 Candidate ve 1 TOP5 var, ancak
sıfır Trade Intent ve sıfır gerçek pozisyon. Geçmiş tarihli kullanıcı
etiketleri canlı bir saat-yasağına dönüştürülmedi. Yeni aktif izin
pencereleri çakışırsa merkezi koordinasyon katmanı NO_TRADE veto
vermeli; bu kuralın ileriye dönük güvenli entegrasyonu ayrı çalışmadır.

## Veri kalitesi ve sınırlar

- Gerçek Binance: signed GET userTrades 27 fill; allOrders 20 FILLED MARKET;
  income 45 kayıt; fiyat bazlı 10 tam LONG roundtrip.
- Redis shadow 10 pozisyon açılışı, ancak 9 sonuç; eksik
  13 Kasım 17:51 açılışının 22:28 SELL ile zararda kapandığı
  Binance ile doğrulandı. Gerçek çıkış nedeni yine BELİRSİZ.
- 112 intent log nedeni kesin dispatch bloğundan ve 10 açılış
  Binance exchange orderId eşleşmesiyle raporlandı. 103 MODEL uzun
  olayının 112 intent ile birer birer eşleştirilmesi yapılamıyor.
- Pozisyon içindeki en yüksek/düşük fiyat yalnız tam 1m barların OHLC
  değeridir; giriş/çıkış dakika high-low değerleri dışarıda ve
  intrabar high/low sırası bilinmiyor.
- Binance BNB komisyonunun gerçek vergi/maliyet dönüşümü USDT değil
  BNB; USDT dönüşümü saatlik BNB perpetual kapanışından tahmindir.
- Model eşikleri, Contra-Trend, Native Stop, merkezi Risk Master
  ve canlı servisler değiştirilmedi, gerçek emir gönderilmedi.

## Veri dosyaları
- 10_BROKER_TRADES CSV: tek tek tüm gerçek işlemler, finans ve 1m yol.
- 112_INTENT_REASONS_ANON CSV: eksik/açılmama gerekçeleri, UUID yerine hash.
- 70_USER_WINDOWS CSV: işaretlenen tüm saatlerin olay sayısı.
- 7_CONFLICT_WINDOWS CSV: çakışma aralıkları ve offline REJECT sonucu.
- Ayrıntılı JSON: kullanıcı pencereleri, bütün 112 niyet, maliyet,
  strateji huni istatistikleri ve test metadata.
