# LONG1 — 11–15 Kasım hedef pencerelerinde yeşil 1m ve %0,22 ARM taraması

20 Kasım 2026 araştırma raporu. Europe/Istanbul; NEARUSDT Binance Futures.
Bu rapor gerçek emir/giriş/kâr kilidi kanıtı değildir; üretim servisleri kapalı.

## Tanımlar ve sayılar

- Kullanıcının 70 aralığının 44 LONG_WANTED / 26 LONG_AVOID aralığı kullanıldı.
- Bir mum yalnız açılışı ve 1m kapanışı bütünüyle aralık içindeyse sayıldı.
- Yeşil mum: 1m CLOSE > OPEN.
- %0,22 brüt ARM görülmesi: 3x * (HIGH / OPEN - 1) * 100 >= %0,22,
  yani HIGH/OPEN fiyat artışı en az %0,073333...
- Daha katı kapanış metriği: 3x * (CLOSE / OPEN - 1) * 100 >= %0,22.
- Aynı dakika MODEL yok: arşivlenen 103 gerçek MODEL LONG olayından
  aynı 1m kovasında bir tane bile kayıt yok. Başka zamanda
  oluşmuş veya gözlenmemiş bir giriş niyeti dışlanmış sayılmaz.
- Bu sayılar **gerçekte kaçırılmış pozisyon sayısı DEĞİL**;
  yeşil mum sonucunu yalnız mum tamamlandıktan sonra öğrenebiliriz.
- TP tetiklenmesi ve Binance reduce-only emir dolumu için
  gerçek pozisyonun ne zaman açıldığı ve intraminute tick/ACK gerekir.
- Aynı LONG_WANTED ile LONG_AVOID çakışan dilimlerde NO_TRADE.

| Grup | Tam 1m mum | Yeşil mum | Yeşil HIGH >= ARM | Yeşil CLOSE >= ARM | HIGH ARM ama aynı dk MODEL yok | CLOSE ARM ama aynı dk MODEL yok |
|---|---:|---:|---:|---:|---:|---:|
| LONG_WANTED | 1678 | 934 | 849 | 651 | 841 | 644 |
| LONG_AVOID | 2419 | 908 | 818 | 594 | 785 | 566 |

Arşivde MODEL LONG bulunmayan 34 LONG_WANTED zaman aralığında
**604 yeşil 1m HIGH/OPEN >= %0,22 ROI mumu** bulundu.
Bu aralıklarda modelin hiç fırsat üretmediği şeklinde yorum
yapılmamalı; yalnız saklanmış LONG MODEL geçişi bulunmadı.

## 44 LONG_WANTED zaman aralığının tamamı

| # | Başlangıç TRT | Bitiş TRT | Yeşil | HIGH ARM >= 0,22 | CLOSE ARM >= 0,22 | HIGH ARM + aynı dk MODEL yok | Kayıtlı MODEL olayları |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | 11-11T12:40 | 11-11T15:00 | 76 | 68 | 58 | 68 | 1 |
| 2 | 11-11T15:36 | 11-11T17:00 | 44 | 44 | 32 | 43 | 2 |
| 3 | 11-11T18:25 | 11-11T18:35 | 8 | 8 | 7 | 8 | 0 |
| 4 | 11-11T19:06 | 11-11T19:30 | 13 | 13 | 12 | 13 | 0 |
| 5 | 11-11T22:40 | 11-11T23:00 | 12 | 12 | 7 | 12 | 0 |
| 6 | 11-12T02:20 | 11-12T02:55 | 22 | 20 | 11 | 19 | 1 |
| 7 | 11-12T03:10 | 11-12T03:45 | 17 | 15 | 13 | 15 | 0 |
| 8 | 11-12T04:51 | 11-12T05:12 | 13 | 12 | 12 | 12 | 0 |
| 9 | 11-12T12:15 | 11-12T13:25 | 36 | 31 | 26 | 31 | 0 |
| 10 | 11-12T17:22 | 11-12T17:42 | 12 | 12 | 8 | 11 | 1 |
| 11 | 11-12T18:33 | 11-12T19:10 | 21 | 20 | 15 | 20 | 0 |
| 12 | 11-12T21:20 | 11-12T22:18 | 32 | 29 | 22 | 29 | 0 |
| 13 | 11-13T00:06 | 11-13T00:33 | 15 | 14 | 11 | 14 | 0 |
| 14 | 11-13T01:18 | 11-13T02:10 | 27 | 19 | 11 | 19 | 0 |
| 15 | 11-13T02:39 | 11-13T03:06 | 11 | 8 | 5 | 8 | 0 |
| 16 | 11-13T03:42 | 11-13T04:27 | 22 | 20 | 15 | 20 | 0 |
| 17 | 11-13T08:00 | 11-13T10:20 | 77 | 75 | 62 | 75 | 0 |
| 18 | 11-13T11:24 | 11-13T11:42 | 11 | 11 | 11 | 10 | 1 |
| 19 | 11-13T12:57 | 11-13T13:06 | 6 | 5 | 5 | 5 | 0 |
| 20 | 11-13T13:33 | 11-13T14:45 | 43 | 42 | 28 | 42 | 0 |
| 21 | 11-13T15:15 | 11-13T15:36 | 12 | 12 | 6 | 12 | 0 |
| 22 | 11-13T16:03 | 11-13T16:42 | 22 | 22 | 17 | 22 | 0 |
| 23 | 11-13T18:36 | 11-13T18:51 | 9 | 8 | 8 | 8 | 1 |
| 24 | 11-13T19:15 | 11-13T19:26 | 6 | 6 | 6 | 6 | 0 |
| 25 | 11-13T20:21 | 11-13T20:45 | 14 | 14 | 11 | 14 | 0 |
| 26 | 11-13T21:18 | 11-13T22:42 | 46 | 38 | 29 | 38 | 0 |
| 27 | 11-14T01:18 | 11-14T01:36 | 10 | 9 | 6 | 7 | 2 |
| 28 | 11-14T02:15 | 11-14T03:06 | 26 | 22 | 16 | 22 | 0 |
| 29 | 11-14T05:30 | 11-14T05:50 | 13 | 13 | 11 | 13 | 1 |
| 30 | 11-14T07:36 | 11-14T09:18 | 53 | 47 | 33 | 46 | 1 |
| 31 | 11-14T10:21 | 11-14T10:33 | 10 | 10 | 7 | 10 | 0 |
| 32 | 11-14T11:36 | 11-14T12:57 | 41 | 36 | 25 | 36 | 0 |
| 33 | 11-14T14:33 | 11-14T15:48 | 42 | 31 | 19 | 31 | 0 |
| 34 | 11-14T16:06 | 11-14T16:45 | 20 | 17 | 11 | 17 | 0 |
| 35 | 11-14T20:21 | 11-14T20:38 | 10 | 9 | 9 | 9 | 0 |
| 36 | 11-15T00:18 | 11-15T00:40 | 13 | 13 | 13 | 12 | 1 |
| 37 | 11-15T01:38 | 11-15T01:43 | 4 | 4 | 3 | 4 | 0 |
| 38 | 11-15T02:12 | 11-15T02:25 | 6 | 6 | 5 | 6 | 0 |
| 39 | 11-15T02:40 | 11-15T03:15 | 23 | 21 | 15 | 21 | 0 |
| 40 | 11-15T05:02 | 11-15T05:12 | 9 | 9 | 9 | 9 | 0 |
| 41 | 11-15T06:42 | 11-15T06:48 | 5 | 5 | 3 | 5 | 0 |
| 42 | 11-15T07:10 | 11-15T07:15 | 4 | 3 | 3 | 3 | 0 |
| 43 | 11-15T08:06 | 11-15T08:22 | 8 | 8 | 7 | 8 | 0 |
| 44 | 11-15T09:15 | 11-15T09:28 | 10 | 8 | 8 | 8 | 0 |

## Her dakika için tam OHLC/flow ve MODEL saatleri

LONG1_70_WINDOWS_GREEN_022_ARM_AND_MISSING_MODEL_20261120.json:
Her pencerenin green_open_to_high_022_details listesi şunları içerir:
1m tam TRT açılış/kapanış saati, OPEN/HIGH/LOW/CLOSE,
OPEN→HIGH ve OPEN→CLOSE brüt 3x ROI, 1m signed
taker imbalance, aynı dakika MODEL olay zamanı/kararı,
LONG_WANTED/LONG_AVOID çakışması ve ARM/ENTRY yetkisinin
kanıtlanmadığı bilgisi. Yeşil ancak eşik altı mumlar da
green_other_details içinde bulunur.

## Maliyet ve yorum

ARM %0,22; geri çekilme %0,10; varsayımsal roundtrip
fee %0,24 ROI puanı olduğunda teorik net taban
%0,22 - %0,10 - %0,24 = **-%0,12 ROI puanı**.
Bu seviye kesin stop/çıkış değildir. Doğrudan düşen
mumlarda ARM hiç tetiklenmez. Bir 1m yeşil mumu bilmek
ancak kapanınca mümkündür; o mumun OPEN fiyatını
geçmişte almış gibi saymak gerçekçi sinyal değildir.

## Sonraki analiz için iki aşamalı sınıflama

1. Bunların hangisi kapanmış 3m/5m piyasa bağlamı
   olumlu iken bir SONRAKİ dakika Sniper/Entry koşullarını
   geçiriyor? (Yeni MODEL/Intent oluşturmadan emir izni yok.)
2. Hangilerinde sonraki 1/3/5 dakika momentum devam ediyor,
   kâr kilidine erişim maliyet+slippage sonrasında mümkün?

Model/Intent eksik soy bağlantısı nedeniyle 841 satır
üzerinden gerçek botun 841 işlem kaçırdığı iddia edilemez.
Üretim ayarı/Redis kayıtları/servisler değiştirilmedi.
