# LONG1 — Kullanıcının verdiği 70 tarih/saat penceresinde as-of simülasyon

20 Kasım 2026; analiz dönemi 11–15 Kasım 2026, Europe/Istanbul.
NEARUSDT Binance USDT-M Futures, LONG1. Research-only, tüm servisler
kapalı, gerçek ORDER yetkisi NO-GO. SHORT1 değişmedi.

## Sabit metodoloji
- Kullanıcının orijinal 70 saat aralığı birebir korundu:
  44 LONG_WANTED, 26 LONG_AVOID. Çakışan saatlerde NO_TRADE.
- 103 gerçek MODEL LONG olayı ve 8640 resmi, SHA256 doğrulanmış
  1m Binance barı. Tam kapanmış 3m/5m araştırma Contra proxy
  ve dondurulmuş katı 1m giriş kuralları. Entry yalnızca
  tamamlanmış 1m barından SONRA sonraki 1m OPEN.
- En fazla 30m Contra recovery, 5 tamamlanmış 1m yeniden
  kontrol. Gerçek eski PENDING'in o kadar yaşadığı veya
  yeni MODEL/Intent ürettiği iddia edilmez.
- 3x ROI; fiyat stop %2,99; TP brüt ROI +1,25 puan;
  maksimum 60m; gidiş-dönüş nominal fee %0,08 =
  3x ile 0,24 ROI puanı. Hibrit altı kademeli kilit
  önceki dondurulmuş research kuralı.
- Slippage, order book, funding, native STOP fill ve
  gerçek partial-1m Sniper/Entry tam modellenmedi.
- LONG_WANTED/LONG_AVOID kullanıcının SONRADAN
  belirttiği etiketlerdir; canlı giriş filtreleri
  veya eğitim hedefi yapılmadı.
- 70 pencere örtüşebildiği için pencere içi MODEL
  sayımlarının toplamları benzersiz 103 MODEL sayısıyla
  eşit olmak zorunda değil. İsimlendirilmiş
  pencereler dışında da olay bulunuyor.

## 70 zaman penceresi kapsamı

| Referans | Zaman penceresi | MODEL LONG bulunan | MODEL LONG bulunmayan |
|---|---:|---:|---:|
| LONG_WANTED | 44 | 10 | **34** |
| LONG_AVOID | 26 | 16 | **10** |

34 LONG_WANTED penceresinde arşivde MODEL LONG olayı yok,
ancak bu aralıklarda kârlı fiyat hareketi bulunmadığı
anlamına gelmez. Bu ayrı fırsat-kaçırma araştırması gerektirir.

## 103 MODEL olayının birleşik simülasyon sonucu

| Tek sanal pozisyon yolu | Fixed TP | Hibrit + TP |
|---|---:|---:|
| Giriş kalitesi research READY | 32 | 32 |
| Sıralı sanal açılış | 18 | 18 |
| LONG_TARGET açılış | 2 | 2 |
| LONG_AVOID açılış | 11 | 11 |
| UNLABELLED açılış | 5 | 5 |
| TP | 13 | 11 |
| Trailing sonraki 1m OPEN | 0 | 2 |
| TIMEOUT | 5 | 5 |
| SL | 0 | 0 |
| Net ROI puanı toplamı | **+2,5265** | **+0,7370** |

Gerçek geçmiş broker LONG açıkken ayrı simülasyon girişi
yasağı konunca: fixed 16 açılış/+1,7565 ROI puanı;
hibrit 16 açılış/-0,0330 ROI puanı.

Pencere origin LONG_WANTED kökenli iki sanal fixed
açılışın toplamı +2,02 ROI puanı; LONG_AVOID kökenli
11 açılış +1,0212 ROI puanı. Kalan UNLABELLED
beş açılış -0,5147 ROI puanı. Bunlar toplam sanal
işlem ROI puanlarıdır; USDT cüzdan getirisi değildir.
Her 0,15 ilave ROI puanı/işlem maliyet fixed toplama
-0,1735 puan verir (pozitif avantaj silinir).

## Özel olarak sorulmuş dört saat

| TRT model olayı | Stage13 kararı | 15m azami brüt LONG ROI | 15m asgari brüt LONG ROI |
|---|---|---:|---:|
| 12 Kas 01:36:16 | ENTRY_PENDING_EXPIRED | +0,1650 | -3,7119 |
| 14 Kas 17:06:14 | CONTRA_WAIT_30M | +0,4561 | -4,1046 |
| 14 Kas 19:06:12 | CONTRA_WAIT_30M | +0,0000 | -6,4313 |
| 14 Kas 23:57:09 | CONTRA_WAIT_30M | +0,6046 | -5,8448 |

Dört senaryoda da Stage13 kombinasyonuyla sanal OPEN yok.
ROI uçları: her MODEL olayının geldiği dakikanın
SONRASINDAKI 1m OPEN'dan, sonraki 15 tam 1m barın
HIGH/LOW sınırlarıyla 3x brüt ROI olarak hesaplandı.
Bunlar gerçek veya aynı anda erişilebilir TP/SL dolumu
DEĞİL; mum içi high/low sırası bilinmiyor.
Fee sonrası mükemmel tepe satış teorik tavanı için
0,24 ROI puanı daha düşülmeli. Bunlar retrospektif
hareket ölçümleridir, eski MODEL anındaki emir izni değil.
Önceki tarihsel konuşmada anılan aynı saatlerin
tüm anlık order book bilgileri elimizde mevcut değil.

## Eksik kanıtların ayrımı
- Aşama14: 32 research READY içinden hiçbiri tam gerçek
  yeni MODEL→Intent parent kimliğiyle OPEN için doğrulanmadı.
- Aşama17: saklı 285 LONG Intent'te üst seviye tam
  source candidate id bulunmadı; zamanla parent uydurulmadı.
- Aşama18: yeni forward-only cursor kuruldu; servisler
  kapalı olduğundan ilk gözlem 0 yeni Intent.
- Bu araştırma canlı kâr, gerçek Binance emri ve
  yeniden açılması gereken 18 işlem iddiasında bulunmaz.

## Dosyalar ve tekrar üretim
- research/trace/replay_long1_stage13_joined_asof_103_v1.py
- research/trace/report_long1_user_70_windows_simulation_v1.py
- research/trace/report_long1_4_reversal_price_excursions_v1.py
- research/trace/test_long1_70_windows_asof_report_v1.py
- LONG1_70_USER_WINDOWS_ASOF_SIMULATION_20261120.json:
  Her pencere başlangıç/bitiş, MODEL adetleri, hazır/ret sebepleri,
  sanal giriş saati, çift ROI ve doğru kaynak-kanıtı bayrakları.
- LONG1_FOUR_FAST_REVERSAL_1M_60M_EXCURSIONS_20261120.json:
  dört saat için 1/3/5/15/30/60 dakika high/low ROI sınırları.

Sıradaki mantıklı araştırma:
34 LONG_WANTED ama MODEL LONG olmayan pencerenin tamamında
as-of dakika kapanışlarında gerçek fiyat fırsatını
tarayıp modelin kaçırdığı dönüşleri hesaplamak.
Bu ayrıca yalnız geçmiş fiyatla koşullu research
olacak, fiyatın gelecekteki tepe/dibine göre
geriye dönük emir seçimi yapılmayacak.
