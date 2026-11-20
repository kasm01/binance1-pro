# LONG1 Aşama 22 — Gerçek aggTrade sırasıyla %0,22/%0,35 ARM

20 Kasım 2026. Gözlenen tarih: 11–15 Kasım 2026.
NEARUSDT USDT-M Binance Futures, 3x. Tamamen research.
LONG1/SHORT1, Risk Master, native stop, Redis, servis,
API ve gerçek Binance emri DEĞİŞMEDİ.

## 819.943 Binance aggTrade kaydı

VM'de önceden saklanmış beş günlük aggTrade ZIP
arşivi kontrol edildi: 11 Kasım 166.977; 12 Kasım
132.714; 13 Kasım 178.181; 14 Kasım 197.776;
15 Kasım 144.295 satır. Yeni internet talebi ve
ücretli API kullanılmadı. 16 Kasım aggTrade
arşivi yok, bağımsız tick-level holdout henüz yok.

## Teknik gerçeklik

Stage13'teki 32 research READY girişi değiştirilmedi;
başlangıç fiyatı sonraki 1m OPEN olarak varsayıldı.
Sonra transact_time ve agg_trade_id sırasıyla
her aggTrade incelendi. Borsa stop fiyat-%2,99,
60m maksimum süre, ücret -%0,24 ROI puanı.

ARM 0,22/0,35/0,50/0,70/1,00/1,40.
Geri çekilme 0,10/0,10/0,12/0,14/0,18/0,20.
Kısmi kapatma oranı 10/15/15/20/20/20.
Her kademede orijinal pozisyon dilimi bir kez kapatılır.
Geri çekilmede kalan miktar kapanır. Stop her
trade kaydında ARM'dan önce kontrol edilir.

AggTrade fiyatına sıfır gecikmeyle close ve
partial fill yapılabildiği varsayımı iyimserdir.
Orderbook, bid/ask, latency, queue, reduce-only
onayları, minNotional, lotStep, mark-price stop,
funding ve gerçek Binance emir sonuçları yok.
Bir fiyatın trade basımında görülmesi borsada
mutlaka o fiyata satılabildiği anlamına gelmez.

## Sonuç

| Profil | Sanal pozisyon | Kısmi satış | Net toplam ROI puanı |
|---|---:|---:|---:|
| %0,22/%0,35 altı kademe partial | 20 | 31 | -3,580807 |
| %0,22/%0,35 full runner | 20 | 0 | -4,261490 |
| %0,22/%0,40 eski partial | 20 | 28 | -3,527540 |

Birinci profilde 18 trailing tick çıkışı, bir 60m
timeout, bir tam altı kademe satışı oldu. 20
pozisyonun 5'i net kârlı, 15'i net zararlı.
En kötü TIMEOUT net -3,304699 ROI puanı.
Birçok +0,22 ARM tetiklenmesi, fee sonrası
negatif kapanışla sonuçlanır.

## Ücret/ek yürütme maliyeti duyarlılığı

| İlave ROI puanı / tam işlem | %0,22/0,35 partial net toplam ROI |
|---|---:|
| +0,00 | -3,580807 |
| +0,05 | -4,580807 |
| +0,10 | -5,580807 |
| +0,20 | -7,580807 |

2.000 USDT / 4 bot için bot başı 500 USDT
sabit sermaye payında yalnız bu LONG1 testinin
karşılığı -17,904 USDT.
2.000 USDT / 8 bot için bot başı 250 USDT
sabit sermaye payında -8,952 USDT.
Bu, 4 veya 8 bot portföyünün toplamı değildir.

Önceki 1m close araştırmasında 19 pozisyon/
+4,489056 net ROI puanı görünüyordu. Bu
farklı exit modeli ve 20 pozisyon açılışıyla
doğrudan eş işlemler kıyası değildir. Ama tick
sırasının, kısa geri çekilme gürültüsünün
sonuca maddi etkisini gösteriyor.

## Sonraki adım

Position Lifecycle ve Execution Risk katmanı:
stop/floor maliyet eşiğini, TIMEOUT kayıplarını,
gerçek spread/slippage ve partial reduce-only
emir ACK güvenliğini incele. Eşiği gelişigüzel
gevşetme. 16 Kasım tick holdout olmadan üretim
GO yok. 3m/5m Market Context, MODEL/Intent tam
kaynak kimliği, Sniper ve Risk Master kararı
bu replay'de yeniden doğrulanmadı.

Kaynak:
research/trace/replay_long1_stage22_aggtrade_ordered_scaleout_v1.py
research/trace/test_long1_stage22_aggtrade_ordered_scaleout_v1.py
LONG1_STAGE22_REAL_AGGTRADE_022_035_TIERED_SCALEOUT_20261120.json
