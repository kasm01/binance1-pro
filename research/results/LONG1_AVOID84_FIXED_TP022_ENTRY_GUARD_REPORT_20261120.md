# LONG1: Üç ters giriş + 84 LONG_AVOID sabit %0,22 brüt TP testi

20 Kasım 2026 araştırma. NEARUSDT USDT-M, 3x; sadece SHADOW.
Kaynak: önceki katı LONG_AVOID 84 sanal giriş, 11–15 Kasım
Binance aggTrade ZIP arşivinin 819.943 sıralı işlem basımı.
Giriş NEXT 1m OPEN varsayımsal; 5m maksimum pozisyon.
Sabit TP dokunma limit dolumu ideal varsayımdır.
Stop fiyat -%2,99 kontrol edildi; 5m sonunda son ticaret
basımıyla kapatma proxy. Gerçek emir defteri,
maker/taker değişken ücret, funding, spread ve
gerçek Binance conditional stop/dolum simülasyonu yok.

## Sabit TP: gerçek net kâr mı?

Önceki roundtrip notional ücret %0,08; 3x teminat ROI
karşılığı **-%0,24 puan**. Sabit brüt %0,22 TP =
**-%0,02 net ROI**, ek slippage/funding YOKKEN bile.
500 USDT tam bot teminatında nominal -0,10 USDT
ve 250 USDT tam bot teminatında -0,05 USDT.
Bu tutar TP dolan pozisyon başına örnektir,
bütün 84 pozisyonun toplamı değildir.

| Sabit brüt TP (3x ROI) | TP’ye dokunan | Kazançlı | Zararlı | Toplam net ROI puanı |
|---|---:|---:|---:|---:|
| %0,22 | 43 | 0 | 84 | -60.63134 |
| %0,35 | 35 | 36 | 48 | -64.72902 |
| %0,40 | 33 | 34 | 50 | -65.02754 |
| %0,50 | 27 | 29 | 55 | -67.29241 |
| %0,80 | 15 | 18 | 66 | -76.22465 |
| %1,00 | 11 | 15 | 69 | -80.71295 |

Not: TP ve net sonucu birbirine karıştırmayın.
Bazı 0,35+ profillerinde TP görülmese de 5m sonunda
kapatılan işlemler az miktarda pozitif olabilir.
Bunların hiçbiri gerçek borsa emir dolumu kanıtı değil.

## Üç özel giriş: giriş ANINDA bilinen değerler

| Tarih-saat TRT | Body | Üst retrace | 1m flow | 3m flow | 3m fiyat return % | Önceki 5m return % | Sonraki en yüksek ROI % |
|---|---:|---:|---:|---:|---:|---:|---:|
| 11-14 01:01 | 0.846 | 0.000 | +0.568 | +0.425 | +0.229 | +0.143 | +0.086 |
| 11-14 18:28 | 0.833 | 0.167 | +0.660 | +0.092 | +0.344 | +0.344 | +0.093 |
| 11-14 19:27 | 0.308 | 0.308 | +0.311 | +0.174 | +0.418 | +0.321 | +0.096 |

Üç işlemde önceki kapalı 1m body / retrace ve
katı 1m parametreleri geçiriliyor. Sonraki 5m
MFE 0,086–0,096 ROI aralığında kalmış; sabit 0,22
TP veya ilk 0,22 ARM tetiklenmiyor. Gelecek MFE
girişte bilinemediği için zaman yasağı oluşturamaz.

## Giriş öncesi aday guard karşılaştırması

Gates sadece tamamlanmış 1m verilerinden türedi,
kullanıcının sonradan işaretlediği WANTED/AVOID
saatleri karar girdisi değil. Bu eşikler alternatif
araştırma hipotezleridir, önerilmiş canlı sabit ayarlar
DEĞİLDİR. Koşul eklemek yeni sinyal üretmez,
yalnız var olan araştırma adaylarını azaltır.

| Ön koşul | 3 kötü girişi eler mi? | AVOID 84 içinden reddedilen | Reddedilen eski kârlılar | WANTED 102 içinden reddedilen | 16 Kasım 61 içinden reddedilen |
|---|---|---:|---:|---:|---:|
| 3m flow en az +0,25 | 2/3 | 43 | 2 | 42 | 29 |
| geçmiş 5m return en az +%0,20 | 1/3 | 36 | 4 | 34 | 19 |
| her ikisi birden | 3/3 | 62 | 5 | 60 | 35 |
| 3m fiyat return en fazla +%0,30 | 2/3 | 38 | 2 | 61 | 39 |
| 3m fiyat return en fazla +%0,20 | 3/3 | 59 | 5 | 84 | 51 |

Önemli karşılaştırma: 3m flow >=0,25 yalnız 18:28
ve 19:27 örneklerini eler, 01:01 kalır. Beş dakika
gücü >=%0,20 ve flow>=0,25 birlikte 3/3 kötü örneği
eler ama **WANTED 102 adayın 60 tanesini** de eler.
Bu ciddi fırsat kaybı demektir. Ayrıca eşikler bu
örnekler görüldükten sonra seçildi: overfit riski!
16 Kasım sonuçları aynı 84 girişin holdout performansı
olarak kullanılamaz; orada yalnız mevcut ayrı 61
STRICT araştırma adayına as-of sınıflama yapıldı.

## Karar

- **Sabit brüt %0,22 TP: NO-GO.** Ücret varsayımı
  nedeniyle TP dolsa bile net kayıp üretir.
- İstenen üç yanlış LONG için fiilen üretim ayarı
  değiştirilmemeli: önce Contra-Trend + 3m/5m
  kapanmış bağlam / yeni MODEL→Intent soy ağacı
  ve gerçek Entry Confirmation sinyalinin yeniden
  üretimi şart.
- Bir test filtresi eklendiğinde yanlış AVOID azaltma
  yanında WANTED kârlı fırsat kaybı da ölçülmeli.
- İşlem yapmak için en az net komisyon + kayma
  + güvenlik tamponu karşılayacak hedef gerekir;
  yalnız ücretleri aşmak beklenen kâr garantisi değil.
- Para tahsisi 4 botta 500, 8 botta 250 USDT
  olarak plan; Risk Master aynı coinde tek pozisyon,
  komisyon/maintenance rezervi ve stop güvenliği korunur.
- Üretim ENV/servis/Redis değişmedi, gerçek emir yok.

Kod: research/trace/replay_long1_84_fixed022_early_entry_gate_v1.py
Test: research/trace/test_long1_84_fixed022_early_entry_gate_v1.py
JSON: LONG1_AVOID84_FIXED_TP022_AND_PREENTRY_GATES_20261120.json
