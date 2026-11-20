# LONG1: 2000 USDT sabit 4/8 bot tahsisi ve altı aşamalı kâr kilidi

20 Kasım 2026. Araştırma amaçlı. NEARUSDT Futures LONG1.
Canlı ayarlar, hizmetler, SHORT1, Risk Master ve emir yetkisi değişmedi.

## Sabit paylaştırma

| | İlk 4 bot | Sonraki 8 bot |
|---|---:|---:|
| Hesap bakiyesi | 2000 USDT | 2000 USDT |
| Bot başına sabit pay | 500 USDT | 250 USDT |
| Hesap yüzdesi | %25 | %12,5 |
| 3x nominal pozisyon üst payı | 1500 USDT | 750 USDT |
| Toplam nominal tahsis tavanı | 6000 USDT | 6000 USDT |
| Tahmini roundtrip ücret / tam pozisyon | 1,20 USDT | 0,60 USDT |
| Sert %0,80 ROI TP ideal net kâr | +2,80 USDT | +1,40 USDT |
| Fiyatta -%2,99 STOP ideal net zarar | -46,05 USDT | -23,025 USDT |
| Tek STOP / 2000 USDT hesap | %2,3025 | %1,15125 |

2.000 USDT'nin bütünü botlara sabit üst limit olarak ayrıldı;
aynı anda tamamı margine girerse ücret, funding ve maintenance
için serbest bakiye kalmaz. Canlıda merkezi rezerv şart.
NEARUSDT aynı coin tek pozisyon kuralı korunur; 4/8 botun
toplam backtest getirisi bu verilerden hesaplanamaz.
Yalnız LONG1 girişleri 500 veya 250 margin ile fiyatlandı.

## İstenen altı aşama: 3x ROI yüzde puanı

| Kademe | ARM | Geri çekilme | Brüt teorik taban | Fee sonrası teorik taban |
|---|---:|---:|---:|---:|
| 1 | +%0,22 | %0,10 | +%0,12 | -%0,12 |
| 2 | +%0,40 | %0,10 | +%0,30 | +%0,06 |
| 3 | +%0,60 | %0,12 | +%0,48 | +%0,24 |
| 4 | +%0,80 | %0,15 | +%0,65 | +%0,41 |
| 5 | +%1,10 | %0,18 | +%0,92 | +%0,68 |
| 6 | +%1,50 | %0,20 | +%1,30 | +%1,06 |

Kademeler 2–6 araştırma hipotezidir, kullanıcı yalnız
ilk kademeyi sabitlemiştir. Önceki roundtrip fee varsayımı
3x ROI -0,24 puandır. İlk kademe +0,22 ARM -0,10
giveback ile brüt +0,12 taban yaratır: ücret sonrası
net -0,12 ROI olur, bu gerçek bir kâr kilidi değildir.
500 USDT margin için teorik -0,60, 250 USDT için
-0,30 USDT. Pozitif ilk net floor için ARM en az
0,24 fee + 0,10 giveback = %0,34 ROI olmalıdır;
slippage ve funding için daha yüksek tampon gerekir.

Bu floor garanti değildir: simülasyon full 1m CLOSE
ile ARM tetikler, sonraki 1m OPEN ile farazi çıkar.
Mum içi fiyat sırası ve emir dolumları bilinmiyor.

## Sert TP ile altı aşamanın uyumsuzluğu

İlk +%0,80 TP sert emir ise fiyat oraya dokununca
pozisyon kapanır; %1,10 veya %1,50 ARM kademelerine
normalde erişilmez. Alternatifleri birbirinden ayırdık:
- Sert %0,80 TP + altı kademeli trailing.
- +%0,80 başlangıç sert TP; önceki tam 1m bar kapanışı
  yeni ARM doğruladığında sıradaki barın TP hedefini
  0,80/1,00/1,20/1,50/1,80/2,30 ROI'ye yükseltme.
  Cancel/replace işleminin gecikmesiz başarı varsayımı
  gerçekçi fill iddiası değildir.
- +%0,80 yalnız SOFT milestone, altı kademeli runner:
  %0,80'e dokunmak otomatik pozisyon kapatmaz.
- Ücretlere göre ilk ARM %0,45 yükseltilmiş runner
  ayrı araştırma karşılaştırması.

## Aynı 32 Stage13 research READY adayı; 11–15 Kasım 2026

3x, 60m maksimum süre, fiyat stop -%2,99,
yaklaşık 0,24 ROI puan ücret. Tam bar stop-first,
TP touch fill iyimser, trailing yalnız 1m CLOSE
sonrası bir sonraki 1m OPEN ile hesaplandı.

| Çıkış profili | Tek-coin sanal açılış | Toplam net ROI puanı | 4-bot tahsisinde tek LONG1 PnL USDT | 8-bot tahsisinde tek LONG1 PnL USDT |
|---|---:|---:|---:|---:|
| Sabit sert +%0,80 TP, trailing yok | 19 | +0,29285 | +1,46425 | +0,73213 |
| İstenen %0,22 ARM, altı kademe, sert %0,80 TP | 19 | -1,69099 | -8,45495 | -4,22748 |
| Altı kademe, önceki mumla TP yükseltme | 19 | -1,69099 | -8,45495 | -4,22748 |
| Altı kademe %0,22 ARM, %0,80 SOFT milestone runner | 19 | +6,64643 | +33,23215 | +16,61607 |
| Altı kademe %0,45 ARM, %0,80 SOFT milestone runner | 18 | +6,77338 | +33,86690 | +16,93345 |
| Dinamik TP, ücret-temelli %0,45 ilk ARM | 19 | -0,06558 | -0,32790 | -0,16395 |

Bunlar aynı geliştirme döneminden farazi LONG1 işlemleri,
sabit margin ile işlem ROI toplamı: dört/sekiz botun
birlikte beklenen getirisi DEĞİL. İlgili tarihsel model
ve giriş parametreleri aynı veri üzerinde incelenmiştir:
overfit ihtimali vardır. 32 research READY adayının tam
MODEL -> Intent, 1m partial Sniper, Whale, Risk Master,
native stop ve gerçek broker fill kanıtı bulunmuyor.
Funding, spread/slippage, piyasa kuyruğu dahil değil.
Pozitif runner sonucu gelecek kârlılığı kanıtlamaz.

## Sonuç ve güvenli sonraki aşama

Sabit 4x500 ve sonra 8x250 USDT sermaye PAYI
tasarımı korunabilir; ancak 2.000'in hepsi marginde
kullanılırsa rezerv yok. Merkez Risk Master bir coin
tek pozisyon ve stratejiler arası toplam rezerv şartlarını
uygulamalı. İstenen %0,22 ARM maliyetten düşük net floor
ürettiğinden bu seviyeyi yalnız testte kullan.
Net kâr hedefi gerekiyorsa %0,45 ARM/%0,10 giveback
alternatifini bağımsız dönemde ve gerçek intrabar fill
güvenceleriyle incele. %0,80 HARD TP ile altı
yükselen kademeyi eşzamanlı istemek mantıksal çelişkidir.

Kod: research/trace/replay_long1_four_eight_six_step_capital_v1.py
Test: research/trace/test_long1_four_eight_six_step_capital_v1.py
JSON: LONG1_2000USDT_4BOT_8BOT_6STAGE_SIM_20261120.json

Canlı bot parametreleri değiştirilmedi; exchange order veya
production Redis yazması yapılmadı, servisler OFF.
