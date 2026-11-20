# LONG1 — 651 yeşil mum yerine gerçek açılabilir aday araştırması

20 Kasım 2026; 11–15 Kasım geliştirme ve kuralları hiç değiştirilmeden
16 Kasım holdout. NEARUSDT Binance Futures. İŞLEM AÇMA YETKİSİ YOK.

## Önce 651 sayısının anlamı

651: LONG_WANTED etiketli pencerelerde OPEN→CLOSE hareketi
3x kaldıraçla brüt en az %0,22 ROI olan yeşil **1m mum** sayısı.
651 adet gerçek pozisyon, yeni MODEL/Intent ya da aynı coin
tek pozisyon kuralıyla uyumlu 651 fırsat değildir. Bir mumun
kapanışı bilindiğinde o mumun açılışından pozisyon almış
olmak lookahead olur. Önceki taramada çakışan etiketlere ait
mumlar ayrıca hesaba dahil edilebiliyordu.

## Kademeli as-of profiller

STRICT: kapanmış yeşil 1m brüt +%0,22; body>=0,22,
retrace<=0,35, flow1>=0,03, 3m akış>0, 3m return>0,
flow3 iyileşme>=0,08, return3 iyileşme>=0,10 yüzde
puan, geçmiş 5 tamamlanmış 1m return>0.

BULL_CONTEXT_EXTRA (sadece as-of güçlü yükseliş koşuluyla):
geçmiş 5x1m return>=+%0,20, 3x1m return>=+%0,12;
gövde>=0,18, retrace<=0,45, flow1>=0,01,
flow3 iyileşme>=0,05, return3 iyileşme>=0,08;
3m return ve flow yine pozitif. Hiçbir karar kuralı
geçmiş LONG_WANTED/LONG_AVOID saat etiketini kullanmaz.
Her aday kapanmış 1m sonrasında sonraki 1m OPEN ile
sanal giriş, 5m sonu CLOSE ile sanal çıkıştır.
Aynı coin en az 5m tek-pozisyon süreli kronolojik tarama.
Retrospektif iki etiket çakışırsa araştırma NO_TRADE.

## İstenen AVOID değişmezliği testi

| Metrik | STRICT | STRICT + BULL_CONTEXT_EXTRA |
|---|---:|---:|
| Geliştirme: sanal giriş | 305 | 325 |
| Geliştirme: LONG_WANTED giriş | 102 | 110 |
| **Geliştirme: LONG_AVOID giriş** | **84** | **88** |
| Geliştirme 5m net toplam ROI puanı | -113.72364 | -108.7304 |
| 16 Kasım holdout giriş | 61 | 64 |
| **16 Kasım holdout toplam net ROI puanı** | **-6.04174** | **-7.7854** |

LONG_WANTED giriş sayısı +8 artsa da LONG_AVOID +4 artıyor;
dolayısıyla kullanıcının AVOID oranları değişmeden kalması
şartı bu profil için **SAĞLANMADI**. 16 Kasım bağımsız
tarihte net sonuç da daha kötü. Bu profil PRODUCTION NO-GO.

Geliştirme döneminde yalnız ek araştırma adayları:

| Etiket (yalnız raporlama) | Ek kapalı mum aday | Sonraki 5m +%0,22 tepe | 5m sonu net pozitif |
|---|---:|---:|---:|
| LONG_WANTED | 18 | 17 | 10 |
| LONG_AVOID | 8 | 7 | 1 |
| UNLABELLED | 19 | 16 | 7 |

## Yorum ve sonraki adım

Güçlü geçmiş yükseliş bağlamı hem hedef hem de
istenmeyen dönemlerde bulunabilir. Bu nedenle
geriye dönük etiketlere göre iki ayrı canlı parametre
profili seçmek piyasa koşulunu değil tarih bilgisini
öğretir; overfit ve ileriye bakış sorunu oluşturur.
İstenen AVOID değişmezliği, canlı parametre gevşetmesi
ile bu çalışmada korunamadı. Orijinal canlı eşikler
ve LONG_AVOID değerlendirmesi hiç değiştirilmedi.
Geçmişte sadece LONG_WANTED etiketine izin veren
oracle karşılaştırması ayrı yapılabilir; bu hiçbir
şekilde canlı işlem kuralı olamaz.

Gerçek MODEL→SIGNAL→CANDIDATE→INTENT bağlantısı
kanıtlanmadan veya 1m Sniper/Entry, gerçek 5m
Market Context, Whale ve ortak Risk Master olmadan
bu sanal girişler üretim pozisyonuna dönüştürülemez.
5m sonunda sabit sanal çıkış, gerçek ARM/TP kısmi
dolumlarını yeniden üretmez; fee -0,24 ROI puanı,
spread/slippage/funding ve gerçek stop ayrıca eksik.

En güvenli sonraki yön: LONG_AVOID sonuçları
değişmeyen, ileri tarih testinde de iyileşme
gösteren ve yeni gerçek MODEL/Intent üreten
ayrı, fail-closed research sinyal adayı. İzin
vermeden üretim eşikleri değişmemeli.

Kaynaklar:
- research/trace/replay_long1_wanted_targeted_asof_shadow_v1.py
- research/trace/report_long1_wanted_targeted_asof_shadow_v1.py
- LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json
