# LONG1 — Sıkı giriş eşikleri / sabit brüt %0,35 TP araştırması

20 Kasım 2026, NEARUSDT 3x, SHADOW-ONLY. Geçmiş 11–15
Kasım katı profil LONG_AVOID 84, LONG_WANTED 102 araştırma
girişi ve 16 Kasım bağımsız 61 girişten oluşan sabit havuzlar.

Gelecek MFE/MAE yalnız sonuç değerlendirmesinde kullanıldı.
Sinyal değişkenleri girişten ÖNCE tamamlanmış 1m barların
gövde, üst fitil, 1m/3m para akışı ve geçmiş 5m getirisinden
oluşur. Gerçek MODEL→Intent, Sniper, Whale veya asli 3m/5m
Market Context yeniden oynatılmadı.

## Değiştirilmeyen başlangıç parametreleri

Katı araştırma: body >= 0,22; retrace <=0,35;
1m taker flow >=0,03; 3m flow >0; 3m flow iyileşmesi
>=0,08; son 5 tamamlanmış 1m getiri >0; ayrıca
3m fiyat return>0 ve iyileşmesi>=0,10 puan.
Ek profiller bunların üzerine as-of koşul ekler.
Canlı .env / üretim giriş eşikleri DEĞİŞMEDİ.

| Profil | Body min | Retrace max | 1m flow min | 3m flow min | 3m flow iyileşme min | Son 5x1m fiyat getirisi min |
|---|---:|---:|---:|---:|---:|---:|
| Katı (referans) | 0,22 | 0,35 | 0,03 | pozitif | 0,08 | pozitif |
| Hafif | 0,25 | 0,32 | 0,05 | 0,03 | 0,09 | %0,03 |
| Orta | 0,28 | 0,30 | 0,07 | 0,06 | 0,10 | %0,06 |
| Güçlü | 0,33 | 0,25 | 0,10 | 0,12 | 0,12 | %0,10 |

## AVOID sabit %0,35 TP (aynı orijinal 84 giriş havuzu)

TP dokunuşu ideal gerçekleşmiş kabul edilir.
3x ROI roundtrip taker fee -0,24 ROI puanı.
5. dakikada açık kalan miktar son aggTrade fiyatından
sanal olarak kapatılır. Giriş fiyatı sonraki 1m OPEN
varsayımıdır, gerçek emir değildir.

| Profil | Kalan giriş | Kazanç | Zarar | Toplam net ROI puanı |
|---|---:|---:|---:|---:|
| Katı | 84 | 36 | 48 | -64,729023 |
| Hafif | 74 | 31 | 43 | -60,299400 |
| Orta | 65 | 28 | 37 | -51,475990 |
| Güçlü | 49 | 21 | 28 | -36,802459 |

Düşen toplam zarar daha az işlem yapılması nedeniyle
otomatik küçülür. Bu tablo filtrelenmiş eski kronolojik
giriş havuzudur: reddedilen girişlerin sonrasında
yeniden pozisyon rebooking yapılmadı. Yeni strateji
backtesti veya gerçek risk-master eşleşmesi değildir.

## WANTED kaçırılan fırsatlar

| Profil | WANTED korunan | WANTED elenen | 5m sonunda kârlı olan WANTED elenen |
|---|---:|---:|---:|
| Katı | 102 | 0 | 0 |
| Hafif | 87 | 15 | 11 |
| Orta | 74 | 28 | 21 |
| Güçlü | 52 | 50 | 32 |

WANTED ve bağımsız 16 Kasım kohortlarında çıkış
5. dakikanın CLOSE fiyatıdır; AVOID sabit TP %0,35
ile birebir karşılaştırılabilir kâr sonucu değildir.
Ama filtrelerin zarar kadar iyi adayları da elediğini
gösterir. Bunlar geçmiş referans etiketleridir,
canlı tarih/saat giriş whitelist'i değildir.

## 16 Kasım sabit, daha önce görülmemiş tarih kontrolü

| Profil | Kalan sanal giriş | 5m net ROI puanı |
|---|---:|---:|
| Katı | 61 | -6,041740 |
| Hafif | 53 | -9,290726 |
| Orta | 47 | -4,649556 |
| Güçlü | 39 | -4,536555 |

Bu holdout fiyat kayma/stop/order-fill modelini
eşitlemez; sadece filtre edilen aynı giriş
havuzunun sabit 5m kapanış karşılaştırmasıdır.
Hiçbir profilde pozitif toplam kanıtı yok.
Model kapasitesini ek örneklerle doğrulamadan
kârlı sistem iddiası yok.

## Üç kötü örnek

14 Kas 01:01, 18:28, 19:27:
- Hafif: 0 / 3 engeller
- Orta: 1 / 3 engeller (19:27)
- Güçlü: 2 / 3 engeller (18:28, 19:27)

01:01 girişi güçlü profilde bile kalıyor.
Bu nedenle 'biraz sıkılaştırma' bu üç sorunu
tamamen çözmüyor; tek tek bu saatlere uydurulmuş
eşik koymak da overfit olur.

## Karar

NO-GO üretim. İşlem sayısı ve yanlış girişler
azalıyor ancak kârlı WANTED fırsatlarının çoğu
da kayboluyor; bağımsız tarihte tüm profiller
toplam negatif. Asıl geliştirme CONTA/Market Context,
as-of yeni MODEL/Intent ve gerçek Entry Confirmation
üzerinden yapılmalı. Denetimsiz yeni emir yok.
Ayrıca %0,35 TP net ancak %0,11 ROI bırakıyor;
bu slippage, funding ve pozisyon riski hariç.
Ücret aşılması stratejinin kârlı olduğu anlamına gelmez.

Kaynak:
research/trace/replay_long1_stricter_entry_gates_tp035_v1.py
research/trace/test_long1_stricter_entry_gates_tp035_v1.py
LONG1_STRICT_ENTRY_TIGHTENING_TP035_GATE_COMPARISON_20261120.json
