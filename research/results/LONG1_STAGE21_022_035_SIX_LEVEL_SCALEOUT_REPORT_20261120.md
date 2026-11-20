# LONG1: Erken ARM %0,22 / %0,35 ve altı kademede kısmi kâr alma

Araştırma tarihi 20 Kasım 2026; veri 11–15 Kasım 2026.
NEARUSDT Binance Futures, 3x, 2000 USDT başlangıç toplam
teminat tahsisi. Botlar OFF. Bu bir backtest/proxy araştırması,
canlı LONG1 performansı değildir. Gerçek emir sayısı 0.

## Kullanıcı isteği ve uygulanabilir mimari

İlk iki kademe aynen:
1. ARM +%0,22 ROI; geri çekilme %0,10 ROI puanı.
2. ARM +%0,35 ROI; geri çekilme %0,10 ROI puanı.

Üçten altıya araştırma tasarımı (kesin üretim ayarı değil):
3. ARM +%0,50; geri çekilme %0,12.
4. ARM +%0,70; geri çekilme %0,14.
5. ARM +%1,00; geri çekilme %0,18.
6. ARM +%1,40; geri çekilme %0,20.

İki farklı kâr alma yorumunu ayrı simüle ettik:
- RUNNER: Her kademede korunacak ROI floor yükselir,
  *pozisyon miktarı azalmaz*. Sinyal/stop gelene dek
  pozisyon taşınır.
- SCALE-OUT: Kademe geçmişi ilk defa gerçekten tamamlanmış
  1m candle CLOSE'ta görüldüğünde, sonraki 1m OPEN
  fiyatından orijinal pozisyonun sabit dilimi kapatılır.
  Kalan miktar sonraki kademe veya stop/timeout/trailing
  kapanışına devam eder. Bu gerçek borsa TP emri değil;
  fill için iyimser uygulama varsayımıdır.

## Kademeli realize planı

| Kademe | ARM | Geri çekilme | Orijinal pozisyondan kapat | Kalan pay (her kademe dolduğunda) | Teorik net ROI koruma tabanı |
|---|---:|---:|---:|---:|---:|
| 1 | +%0,22 | %0,10 | %10 | %90 | **-%0,12** |
| 2 | +%0,35 | %0,10 | %15 | %75 | **+%0,01** |
| 3 | +%0,50 | %0,12 | %15 | %60 | +%0,14 |
| 4 | +%0,70 | %0,14 | %20 | %40 | +%0,32 |
| 5 | +%1,00 | %0,18 | %20 | %20 | +%0,58 |
| 6 | +%1,40 | %0,20 | %20 | %0 | +%0,96 |

Her kademe ve satış oranı kuralı değişmez; yeniden
işlem büyüklüğü yeni bakiyeye göre artmaz.
Bu sınırlar 3x ROI yüzdesidir, fiyat yüzdesi DEĞİL.
Teorik floor = ARM - geri çekilme - 0,24 ROI puanı
komisyon. Slippage, funding ve maker/taker farkları
hariçtir; koruma tabanı gerçek elde edilen kâr garantisi
değildir. ARM seviyesi fiyatın oraya kısa süre dokunması
değil, 1m CLOSE ile doğrulanır.

Örnek: %10 ilk dilim, 4 bot düzeninde tam 500 USDT margin
açılmışsa 50 USDT margin / 150 USDT notional pozisyon
kapanması demektir. Tam +%0,22 ROI noktasında
net beklenen kâr: 50*(0,22-0,24)/100 =
**-0,01 USDT**. 8 bot düzeninde 25 USDT margin
dilimi için **-0,005 USDT**. Küçük zararı
sınırlar ama kendi başına ilk net kârı garantilemez.
İkinci dilim tam +%0,35 ROI'de kapanırsa
ilk 4-bot payının %15'i 75 USDT margin:
75*(0,35-0,24)/100 = +0,0825 USDT.
Bu miktarlar NEXT OPEN fiyatıyla fiilen değişebilir.

## 103 MODEL LONG zamanı, Stage13'ten 32 sabit research aday

Giriş parametreleri DEĞİŞMEDİ. Dondurulmuş Stage13 3m/5m
contra proxy ve tamamlanmış 1m araştırma filtresi.
En fazla 60m pozisyon; gerçek PENDING/Model Intent
soy zinciri, partial 1m Sniper ve Whale geri oynatılamadı.
SL fiyat-%2,99; 3x ROI -8,97, varsayılan fee -0,24.
Her tranche ücret orijinal pozisyon dilimi oranına
göre ayrıldı. Mark price, funding, lot min, tick size,
slippage ve emir onay zamanlaması modellenmedi.

| Model | 19 farazi tek-LONG açılışı toplam net ROI puanı | 4 bot tahsisiyle yalnız LONG1 USDT | 8 bot tahsisiyle yalnız LONG1 USDT |
|---|---:|---:|---:|
| Önceki %0,22 / %0,40 başlangıç, RUNNER | +6,64644 | +33,23 | +16,62 |
| Önceki başlangıç, altı kademede kısmi satış | +4,30426 | +21,52 | +10,76 |
| Yeni %0,22 / **%0,35**, RUNNER | +6,64644 | +33,23 | +16,62 |
| Yeni %0,22 / **%0,35**, altı kademede kısmi satış | **+4,48906** | **+22,45** | **+11,22** |

Yeni 6-kademe kısmi satışta 19 sanal pozisyonda
toplam **73 kısmi çıkış dilimi** ve tüm pozisyonlar
için orijinal miktarın %100'ünü kapatan son
stop/trailing/timeout/all-slices çıkışları vardır.
Gelecek fiyatı bilinerek giriş seçilmedi.

Önceden açık gerçek broker LONG saatleri dışlanınca
yeni altı kademe kısmi satış:
17 sanal pozisyon, +3,512943 toplam ROI puanı.
Bu gerçek broker eşzamanlı LONG PnL'sini dahil etmez.

İşlem başına ilave 0,10 ROI puanı maliyet varsayılırsa
yeni altı-kademe kısmi satış toplamı:
+4,489056 - 19*0,10 = +2,589056 ROI puanı.
Ancak küçücük kârlar, çoklu emir/kapanış maliyetleri,
spread/slippage ve stop gap sonucu gerçekçi
olarak değişebilir. Aynı 11–15 Kasım veri setinde
tasarım denendiği için sonuç bağımsız holdout değildir.

## 4/8 bot sabit pay ve ortak Risk Master

| | 4 bot | 8 bot |
|---|---:|---:|
| Toplam sermaye tahsisi | 2000 USDT | 2000 USDT |
| Bot başı sabit tahsis tavanı | 500 USDT | 250 USDT |
| 3x nominal üst tavan/bot | 1500 USDT | 750 USDT |
| Fiyat-%2,99 stop, fee dahil bir tam pozisyon | -46,05 USDT | -23,025 USDT |

Bu toplam 4/8 bot portföy simülasyonu değil,
yalnız LONG1'i iki farklı sabit margin planına
ölçeklemedir. Tam 2.000 USDT'nin eşzamanlı
margine ayrılması nakit/ücret tamponu bırakmaz;
merkezi Risk Master rezerv sınırına uymak gerekir.
Bir NEARUSDT pozisyonunu farklı LONG/SHORT motorları
eşzamanlı açamaz. Açık pozisyon aynı kaynağa
aitmiş gibi iki kez realize edilemez.

## Asıl risk ayrımı

ARM 0,22, yalnız pozisyon daha önce o kârı gördükten
sonra izlemeye başlar. İlk saniyede fiyat aşağı
giderse, ARM tetiklenmez; tüm pozisyon
önceki katastrofik stopa kadar zarar edebilir.
İlk kademeyi %10 satmak, geri kalan %90'ın
sistemik riskini sıfırlamaz.
Birinci net floor yaklaşık -%0,12,
ikinci net floor yaklaşık +%0,01: bu değerler
gecikme/yürütme kaymasına hassastır.

Yüksek kademelere izin vermek için %0,80
sert TP bu testte yoktur; soft milestone vardır.
Aksi hâlde 5/6. kademe gerçek işlemlerde erişilemez.

## Uygulama kararı

SHADOW / RESEARCH PASS; PRODUCTION NO-GO.
Uygun ilerleme: gerçek kline yerine as-of trade/tick
verileriyle intrabar activation, trailing, partial
reduce-only, quantity min/step, ACK, borsa stop ve
Risk Master rezerv tutarlılığı test edilmeli.
Daha sonra bağımsız tarih holdout ve
Stop/TimeOut zarar dağılımı doğrulanmalı.
Live env, executor, Redis state ve servislerde
hiçbir değişiklik yapılmadı.

Kaynaklar:
- research/trace/replay_long1_stage21_two_early_arms_scaleout_v1.py
- research/trace/test_long1_stage21_two_early_arms_scaleout_v1.py
- LONG1_2000USDT_4_8BOT_022_035_SIX_STAGE_PARTIAL_REPLAY_20261120.json
