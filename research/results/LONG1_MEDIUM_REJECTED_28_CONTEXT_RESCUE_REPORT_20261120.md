# LONG1 Orta Eşik 28 WANTED Red — Market Context / Entry ayrıştırma

Tarih 20 Kasım 2026. NEARUSDT 3x. Tamamen SHADOW araştırma.
Kaynak: önceden donmuş STRlCT 11–15 Kasım original 84 AVOID,
102 WANTED + 16 Kasım 61 independent entry adayı. Bütün girdiler
kapanmış 1m barlardan. Bu yeni gerçek MODEL sinyalleri değildir.
Kullanıcı WANTED/AVOID etiketleri **raporlama için** kullanıldı,
canlı işlemlerde takvime bağlı açma/engelleme kuralı DEĞİLDİR.

## 28 reddedilmiş LONG_WANTED girişin teşhisi

Orta eşik 102 adaydan 28'ini elemiş.
21 tanesi geçmiş sabit 5m CLOSE çıkışında ücret sonrası artıda,
7 tanesi negatifti. 25 tanesinin girişten SONRAKİ 5m
en yüksek fiyatı brüt +%0,35 ROI veya üzerindeydi.
Bu tepeyi gördüğümüz için gerçek TP limit emrinin mutlaka
dolduğunu iddia etmiyoruz. WANTED'de sabit TP35 burada
yeniden test edilmedi; WANTED ve Nov16 ROI sonuçları,
eski varsayımsal 5m sabit kapanış sonuçlarıdır.

| İlk elenen kontrol (sıra sabit) | Giriş |
|---|---:|
| 1m retrace <=0,30 | 11 |
| Önceki 5 kapanmış 1m return >%0,06 | 7 |
| 3m flow iyileşmesi >=0,10 | 4 |
| 1m flow >=0,07 | 3 |
| 3m flow >0,06 | 3 |
| TOPLAM | 28 |

Birden fazla koşula takılan giriş de olabilir.
Bu tablo ilk başarısız kapıyı sayıyor.

## Research: orta profil + güçlü bağlamda hafif teyit

Temel MEDIUM: body>=0,28, retrace<=0,30,
flow1>=0,07, flow3>0,06, flow3 improvement>=0,10,
geçmiş 5x1m return>%0,06.

RESEARCH RESCUE (saatten bağımsız): orta profili
geçemese bile MILD koşullarının tamamını sağlıyorsa
ve geçmiş 5x1m fiyat hareketi >=%0,20 ve 3m
taker flow >=0,25 ise *yalnız sanal aday*.
Ana STRICT as-of model score, full Market Context,
Sniper, Entry, Risk Master önkoşulları canlıda
kaldırılamaz; bu replay bunları yeniden doğrulamadı.

| Orijinal kohort | Orta kabul | Orta + rescue kabul | Kıyaslanan çıkış |
|---|---:|---:|---|
| LONG_AVOID | 65 | 65 | sabit %0,35 TP aggTrade fill proxy |
| LONG_WANTED | 74 | 78 | eski 5. dakikanın CLOSE fiyatı |
| 16 Kasım | 47 | 47 | eski 5. dakikanın CLOSE fiyatı |

Geri kazanılan dört WANTED girişin kapanış sonuçları:

| Giriş saati TR | 5m net ROI puanı | 5m MFE brüt ROI |
|---|---:|---:|
| 11 Kasım 15:00 | -0,7151 | +2,0586 |
| 12 Kasım 18:52 | -1,0346 | +0,2649 |
| 13 Kasım 10:16 | +0,2670 | +1,1831 |
| 13 Kasım 19:25 | +0,5303 | +2,3966 |

Orta profile kıyasla WANTED 5m net ROI toplamı
+19,207293'ten +18,255019'a DÜŞÜYOR.
Kaçan fiyat tepeleri sabit 5m kapanışta
net kâr sağlamayabilir; ayrı aggTrade TP35 replay
gereklidir. AVOID ve 16 Kasım adayları bu
donmuş kohortta değişmedi ama bu tek başına
stratejinin iyileştiği anlamına gelmez.

## Kesin karar

**NO-GO** üretim. Rescue çalışma hipotezi geçmiş
araştırmadan sonra seçildi; 16 Kasım daha önce
pek çok profille incelendiği için artık temiz
holdout değildir. Yeni, dokunulmamış tarih ile
MODEL→SIGNAL→MARKET CONTEXT→SCORE GATE→SNIPER→
ENTRY CONFIRMATION→RISK MASTER→FINAL SAFETY
uçtan uca doğrulaması olmadan canlı ayar yok.

Bu ölçümde filtre reddedildikten sonra pozisyonları
yeniden yerleştirmedik, REAL broker occupancy
ve exchange fill sıra/latency simüle edilmedi.
Bunlar araştırma başarısını abartabilir.
İleride sahte BUY bağlamını azaltmak için
kapanmış 3m/5m flow-price divergence ve
1m retrace sonuçları birlikte incelenmeli.

Kaynaklar:
research/trace/audit_long1_medium_rejected_28_context_v1.py
research/trace/test_long1_medium_rejected_28_context_v1.py
LONG1_MEDIUM_REJECTED_28_CONTEXT_RESCUE_AUDIT_20261120.json
