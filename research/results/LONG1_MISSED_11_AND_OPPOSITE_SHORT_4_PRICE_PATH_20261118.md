# LONG1 — kaçırılan LONG fırsatları ve 4 karşı yön SHORT senaryosu

## Kapsam

11–15 Kasım 2026 kullanıcının ortak çalışma referansında LONG açılmalı
44 pencere ve LONG açılmamalı 26 pencere bulunuyor. Bu rapor yalnız
geçmiş gözlem ve NEARUSDT karşıolgusal fiyat yoludur. Gerçek SHORT1
INJUSDT stratejisini, SHORT1 model skorunu ya da canlı SHORT emrini
temsil etmez. Kullanıcı pencereleri canlı saat yasakları olarak kullanılmaz.

## Açılmalı LONG neden kaçtı?

- 44 açılmalı pencerede 10 farklı pencerede 11 bağımsız MODEL LONG
  olayı vardı. 11/11 rolling model eşiğinin üstündeydi.
- 9 Trade Intent yalnız üç açılmalı pencerede oluştu;
  bunların hiçbiri borsada pozisyon açmadı.
- 9 niyet: yönlü 1m mum eksikliği 4, Sniper geçmiş 2, Sniper erken 1,
  güçlü 1m ters dönüş 1, PENDING recheck wait 1.
- 11 model sinyali eski bağımsız 60m OHLC araştırmasında 11/11 TP_FIRST;
  bunlar sanal 3x LONG girişleri için ilk temas sonuçlarıdır,
  gerçek 1m giriş sinyali, fill, stop ve ücretli net kâr değildir.
- 11 olaydan 2 tanesinde Binance tarafından doğrulanmış daha önce
  açılmış bir LONG pozisyon zaten aktifti. Ayrı yeni giriş yapmamak
  tek pozisyon koordinasyonu açısından güvenli davranıştır.
- Dört olayda aynı yuvarlanmış skora ve 180 saniyelik ileri pencereye
  sahip TOP5 kayıtlarının tümü SHORT yönlü whale ve %0,45 üzeri
  whale skoruyla uyumludur. Bu mevcut Master whale veto şartıyla
  **UYUMLU**, ancak eski close_id TOP5 içine aktarılmadığı için
  MODEL bazında kesin sebep değildir.
- Diğer yeni MODEL_LONG→TOP5→intent bağlantıları eski kayıtlardan
  kesin kurulamaz. Üretim Stage8 trace meta ileriye dönük kuruldu;
  bu eski olaylara trace_id uydurulmadı.

| MODEL sinyali (TR) | Rolling eşiği geçti | V2 shadow | TOP5 as-of iz | Niyet / gözlem | Sanal 60m |
|---|---|---|---|---|---|
| 11-11 14:57 | Evet | PENDING | 1 tahmini | 4 yakında niyet | TP_FIRST |
| 11-11 16:03 | Evet | PENDING | 4 tahmini | Zaten LONG açık | TP_FIRST |
| 11-11 16:06 | Evet | PENDING | 1 tahmini | Zaten LONG açık | TP_FIRST |
| 11-12 02:21 | Evet | PENDING | 3 tahmini | Whale kontra (olasılık) | TP_FIRST |
| 11-12 17:24 | Evet | VETO_ADVISORY | 3 tahmini | Whale kontra (olasılık) | TP_FIRST |
| 11-13 11:24 | Evet | PENDING | 1 tahmini | 1 yakında niyet | TP_FIRST |
| 11-14 01:18 | Evet | VETO_ADVISORY | 0 tahmini | Kesin upstream neden yok | TP_FIRST |
| 11-14 01:21 | Evet | PENDING | 1 tahmini | Whale kontra (olasılık) | TP_FIRST |
| 11-14 05:30 | Evet | PENDING | 3 tahmini | Whale kontra (olasılık) | TP_FIRST |
| 11-14 07:36 | Evet | PENDING | 1 tahmini | 4 yakında niyet | TP_FIRST |
| 11-15 00:18 | Evet | VETO_ADVISORY | 0 tahmini | Kesin upstream neden yok | TP_FIRST |

Bu tablo içinde eski MODEL/TOP5 ilişkileri yalnız zaman + 6-basamak
skor eşleşmesidir; 112 Trade Intent için önceki çalışmadaki
kesin candidate→top5→intent zinciri ile karıştırılmamalıdır.
V2 kararları geçmişte canlı risk kapısında değildi; V2 PENDING/VETO
etiketini gerçek açılmama nedeni olarak göstermiyoruz.

## Dört LONG_AVOID açılışı aynı fiyatla SHORT olsaydı?

Yöntem: Binance NEARUSDT public Futures 1m OHLC; tarihsel gerçek
LONG BUY fiyatı, farazi SHORT açılış fiyatı; 3x kaldıraç.
İşlem açma/pozisyon taşıma yetkisi yok. Giriş/çıkış dakikalarının
OHLC mumları senaryoya katılmadı; bunlar kesin uygulanabilir
saat ve fiyat emirleri değildir. Önce net P&L ve funding/komisyon
dahil edilmemiş **brüt 3x ROI** üst sınırlarıdır.

| Gerçek LONG açılışı TR | SHORT MFE (ilk 60m) | SHORT lehine dip fiyatı | Dip saati | 60m en aleyhe ROI | LONG kapanışında SHORT ROI |
|---|---:|---:|---|---:|---:|
| 11-12 20:05 | +%3.433 | 3.369 | 20:40 | %-0.704 | %-1.320 |
| 11-13 05:42 | +%8.241 | 3.328 | 06:23 | %-0.789 | %+9.556 |
| 11-13 17:51 | +%9.042 | 3.443 | 18:36 | %-1.183 | %+1.268 |
| 11-14 06:34 | +%5.165 | 3.311 | 07:33 | %-2.404 | %-1.603 |

**Dipten dönüş gözlemi:**

- 11-12 20:05: ilk 60m SHORT tepe +%3.433 ROI; izleyen tam mumlarda dipten sonraki en büyük ters hareket 4.137 ROI puanı. 120m MFE +%3.433, 240m MFE +%3.433.
- 11-13 05:42: ilk 60m SHORT tepe +%8.241 ROI; izleyen tam mumlarda dipten sonraki en büyük ters hareket 5.26 ROI puanı. 120m MFE +%13.150, 240m MFE +%14.202.
- 11-13 17:51: ilk 60m SHORT tepe +%9.042 ROI; izleyen tam mumlarda dipten sonraki en büyük ters hareket 6.423 ROI puanı. 120m MFE +%9.042, 240m MFE +%9.042.
- 11-14 06:34: ilk 60m SHORT tepe +%5.165 ROI; ilk 60m dip sonrası tam 1m mumda dönüş kanıtı henüz yok. 120m MFE +%5.254, 240m MFE +%5.521.

**Önemli:** 14 Kasım 06:34 LONG pozisyonu yalnız ~2 dakika açık
kaldığından SHORT, o gerçek LONG kapanışına göre negatif ROI
gösteriyor; +%5,165 SHORT tepe ancak yaklaşık bir saat
beklenirse geçmiş fiyat yolunda görülebiliyor. Bu, pratikte
o kadar süre zararı ve marjin riskini taşıyabileceğimiz
anlamına gelmez. İki yönde pozisyon açılması da ayrı bir
merkezi risk ve karşıt pozisyon yasağına tabidir.

### %0,60–%2,50 ARM dokunuşları

| SHORT varsayımı (TR) | %0,60 | %0,95 | %1,20 | %1,65 | %2,00 | %2,50 |
|---|---|---|---|---|---|---|
| 11-12 20:05 | Evet | Evet | Evet | Evet | Evet | Evet |
| 11-13 05:42 | Evet | Evet | Evet | Evet | Evet | Evet |
| 11-13 17:51 | Evet | Evet | Evet | Evet | Evet | Evet |
| 11-14 06:34 | Evet | Evet | Evet | Evet | Evet | Evet |

- ARM dokunması, geri çekilme yüzdesine göre gerçekleşmiş
  trailing stop fill’i, kârın kilitlendiğini veya net kazanımı
  **KANITLAMAZ**. Mumun high/low sırası bilinmiyor.
- 3x örnek %0,08 notional gidiş-dönüş maliyet yaklaşık %0,24
  ROI puanına denk gelir; SHORT tarafı spread, slippage, funding
  ve Binance’in fiili BNB komisyonu bu hesapta yok.
- Gerçek SHORT1 INJUSDT olduğundan bu dört NEARUSDT senaryosu
  SHORT1 stratejisi için gerçek backtest diye sunulamaz.

## Teknik karar

1. Missing LONG tarafında aynı skordan tekrar yayılan sinyalleri
   ayrı fırsat saymayıp, ilk MODEL kararından itibaren
   Master whale veto, açık pozisyon, Sniper ve PENDING
   geçişlerini ayrı trace alanlarıyla saymak gerek.
2. Açılmalı pencerelerdeki 11 TP_FIRST sanal sonucu tek başına
   eşikleri gevşetmek için kullanma; yeni farklı dönemlerde
   karşıolgusal net ücretli, 1m Entry Confirmation replay yap.
3. SHORT için yüksek farazi MFE çıktığı için hemen SHORT açmak
   güvenli değil; LONG/SHORT merkezi Risk Master ve
   karşıt pozisyon engeli birlikte test edilmeli.
4. Çakışan 7 pencere geçmişte 0 gerçek fill; araştırma
   senaryosunda kesin NO_TRADE/REJECT korunuyor.
5. Her iki canlı bot kapalı, Stage24 canlı emir NO-GO,
   hiç Binance POST, Redis üretim yazması veya parametre
   değişikliği yapılmadı.

## Yeniden çalıştırma

- research/trace/replay_long1_missed_wanted_and_opposite_short_v1.py
- research/trace/augment_long1_missed_upstream_guards_readonly_v1.py
- research/trace/render_long1_missed_wanted_opposite_short_report_v1.py
- Ayrıntılı fiyat yolu JSON ve iki CSV bu raporla aynı klasörde.
