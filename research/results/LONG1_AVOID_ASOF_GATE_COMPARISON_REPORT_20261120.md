# LONG1 — LONG_AVOID saatlerinde kısa yükseliş / filtre kaçırma incelemesi

20 Kasım 2026. 11–15 Kasım, Europe/Istanbul. Binance NEARUSDT 1m
kapalı fiyat/flow mumları, önceki Stage13 MODEL kayıtları.
NO LIVE ORDER. Üretim servisleri kapalı. Bu simülasyon, gerçek
Sniper/Entry/Whale veya kaynak kimliği doğrulanmış işlem değildir.

## 1. Gerçek LONG1 eşikleri ve tarihsel MODEL kararları

VM whitelist üretim ayarı: rolling model gate quantile 0,965;
min 0,491, max 0,525; Entry body >=0,15, max retrace <=0,50,
Entry quality >=0,52; Sniper candle progress 0,05–0,60;
Contra Guard enabled; en fazla 1 pozisyon; scale-in disabled.
Bunlar çalışan servislerden alınmış yeni anlık sinyal değil,
VM içindeki mevcut konfigürasyon dosyasının salt-okunur kopyasıdır.

Önceki tam-kapalı 1m araştırma filtreleri bundan farklıdır:
body>=0,22, retrace<=0,35, flow1>=0,03, 3m flow pozitif,
3m fiyat return pozitif, 3m flow delta>=0,08 ve
3m fiyat delta>=0,10 yüzde puan. Ayrıca destek için
son 5 kapanmış 1m üzerinden 5m return >0 araştırma
filtresi eklendi: bu, borsanın gerçek LIVE 5m context gate
fonksiyonunun yeniden çalıştırıldığı anlamına gelmez.

LONG_AVOID aralıklarına düşen 70 arşiv MODEL olayı:

| Stage13 sonucu | Model olayları | Sonraki 5m brüt +0,22 MFE gördü | +0,35 MFE gördü | +0,80 MFE gördü | 5m sonu ücret sonrası pozitif |
|---|---:|---:|---:|---:|---:|
| MODEL_GATE | 1 | 1 | 0 | 0 | 0 |
| CONTRA_WAIT_30M | 28 | 22 | 22 | 13 | 9 |
| ENTRY_PENDING_EXPIRED | 23 | 20 | 19 | 13 | 11 |
| RESEARCH_READY_NO_REAL_INTENT | 18 | 17 | 15 | 9 | 7 |

Görüldüğü gibi Contra/PENDING tarafından reddedilen olaylarda
kısa yükselişler görülebiliyor. Ancak MFE en yüksek gelecek
fiyatı olduğu için bu tablo kârlı giriş/çıkış olacağını kanıtlamaz.
Bazı olaylar aynı fiyat yükselişine denk gelebilir.

## 2. MODEL sinyalinden BAĞIMSIZ tüm dakika adayları

1m CLOSE yeşil ve OPEN→CLOSE 3x ROI en az +%0,22 ise,
yalnızca SONRAKİ 1m OPEN için araştırma adayı tanımlandı.
Gelecekteki HIGH veya LOW ile aday seçilmedi.
Aynı anda LONG_WANTED ve LONG_AVOID etiketi olan 13
çakışan mum araştırma giriş adayı olarak dışlandı.

| Ölçüm | LONG_AVOID | LONG_WANTED |
|---|---:|---:|
| Kapanmış yeşil +%0,22 aday mum | 581 | 638 |
| 1m canlı body>=0,15 ve retrace<=0,50 basit görünüm (Entry quality, Sniper hariç) | 550 | 598 |
| Katı 1m araştırma filtresi tam geçiş | 128 | 158 |
| Katı 1m + son 5 kapalı 1m return pozitif | 95 | 143 |
| Sonraki 5m fiyatın brüt +%0,22 ROI tepesini görmesi | 402 | 575 |
| Sonraki 5m CLOSE ücret sonrası net artı | 106 | 372 |

Kapanmış mumla seçilen %0,22 adaylar ilk hareketin
artık gerçekleştiği noktalardır; sonraki 5 dakika yukarı
hareketin süreceğini garanti etmez. Aday mumun kendi
OPEN→HIGH farkı gelecekteki işlem kârı sayılamaz.

## 3. Hangi katmanda eleniyor? (Aşamalı İLK başarısız eşik)

| Kontrol sırası | İlk kez elenen aday (LONG_AVOID) |
|---|---:|
| body_research_min_0p22 | 6 |
| retrace_research_max_0p35 | 98 |
| flow1_research_min_0p03 | 112 |
| flow3_research_positive | 132 |
| r3_research_positive | 31 |
| flow3_research_delta_0p08 | 53 |
| r3_research_delta_0p10pp | 21 |
| r5_closed_proxy_positive | 33 |
| **Tüm kontrolleri geçen** | **95** |

Bu tablo eşikleri sırayla uygular. Her eşik bağımsız
bir neden değildir: farklı sıralamayla ilk elenme
dağılımı değişir. Tam canlı Market Context, Whale,
Sniper ve gerçek rolling MODEL skor bilgisi bu
yapay yeni adaylarda mevcut değildir.

## 4. Gerçekçi aday sayısını daraltma ve 5m hareket

- 95 kapalı-1m+5m as-of tarama geçişinden
- mevcut gerçek broker LONG zamanlarını dışlayınca
  89 adet kaldı.
- Aynı coin için tek pozisyon, en az 5m aralıkla
  sırayla seçilince 78 araştırma adayı kaldı.
Bu seçim her adayın gelecekte nasıl sonuçlanacağını
kullanmıyor, yalnız kronolojik olarak ilerliyor.
- Sonraki 5m içinde brüt +%0,22 ROI yüksek fiyatı görülen: 41.
- Brüt +%0,35 görülen: 34.
- Brüt +%0,80 görülen: 15.
- 5m sonunda %0,24 ROI komisyon sonrası net pozitif: 6.
- 5m sonundaki farazi tüm çıkışların toplam ROI puanı:
  -85.82531.
Bu toplam beklenen strateji performansı değildir: stop
yönetimi, gerçek TP, giriş emirleri, minQty, slippage
ve interval geçişlerindeki başka pozisyonlar test edilmedi.
Stop/TP high ve low sırası 1m OHLC ile kesin bilinmiyor.
Mevcut 2.000 USDT hesabın dört bota dağıtılmasını
pozisyon açma kanıtı olarak yorumlamayın.

## 5. 26 LONG_AVOID aralığı için saat bazında gözlem

| Başlangıç TRT | Bitiş TRT | Kapalı yeşil +%0,22 | Katı 1m+5m geçti | Sonraki 5m HIGH +%0,22 | Sonraki 5m CLOSE ücret sonrası pozitif | Aynı dakikada MODEL |
|---|---|---:|---:|---:|---:|---:|
| 11-12T00:15 | 11-12T02:20 | 30 | 4 | 21 | 8 | 2 |
| 11-12T05:18 | 11-12T07:33 | 31 | 9 | 24 | 3 | 0 |
| 11-12T07:54 | 11-12T09:15 | 20 | 5 | 13 | 3 | 0 |
| 11-12T10:33 | 11-12T12:18 | 10 | 3 | 6 | 1 | 0 |
| 11-12T13:27 | 11-12T14:54 | 16 | 0 | 11 | 5 | 0 |
| 11-12T15:15 | 11-12T16:12 | 11 | 1 | 7 | 3 | 0 |
| 11-12T19:10 | 11-12T20:18 | 18 | 2 | 11 | 2 | 0 |
| 11-13T00:33 | 11-13T01:18 | 10 | 3 | 5 | 1 | 0 |
| 11-13T03:06 | 11-13T03:42 | 7 | 1 | 4 | 1 | 0 |
| 11-13T05:00 | 11-13T08:00 | 51 | 6 | 38 | 12 | 8 |
| 11-13T11:50 | 11-13T12:54 | 15 | 3 | 12 | 3 | 0 |
| 11-13T13:06 | 11-13T13:33 | 4 | 2 | 4 | 1 | 0 |
| 11-13T16:42 | 11-13T18:38 | 28 | 5 | 23 | 7 | 4 |
| 11-13T22:40 | 11-14T01:16 | 38 | 8 | 25 | 3 | 1 |
| 11-14T03:06 | 11-14T04:27 | 20 | 1 | 14 | 3 | 0 |
| 11-14T04:45 | 11-14T05:27 | 11 | 1 | 3 | 0 | 1 |
| 11-14T05:51 | 11-14T07:09 | 21 | 2 | 14 | 4 | 1 |
| 11-14T09:18 | 11-14T10:20 | 10 | 2 | 7 | 2 | 0 |
| 11-14T16:48 | 11-14T20:21 | 70 | 13 | 51 | 16 | 6 |
| 11-14T20:39 | 11-14T22:24 | 30 | 4 | 23 | 12 | 2 |
| 11-14T23:00 | 11-15T00:15 | 20 | 1 | 16 | 3 | 3 |
| 11-15T01:20 | 11-15T02:10 | 12 | 1 | 6 | 0 | 0 |
| 11-15T03:40 | 11-15T04:55 | 24 | 4 | 18 | 4 | 0 |
| 11-15T06:10 | 11-15T08:00 | 23 | 4 | 17 | 4 | 0 |
| 11-15T09:26 | 11-15T11:20 | 26 | 4 | 14 | 3 | 0 |
| 11-15T15:30 | 11-15T17:42 | 25 | 6 | 15 | 2 | 0 |

## 6. Kanıt sınırı ve önerilen doğrulama

- Sinyal yok görünen dakikalarda yeni MODEL hesaplanmadığı
  ispatlanmaz; sadece 103 arşivlenmiş MODEL LONG olayı
  arasında aynı dakika kaydı yok.
- LONG_AVOID tarihleri geriye dönük etiketler; canlı
  trade whitelist/veto işlevi kazandırılmamalı.
- Katı filtreyi düşürmeden önce ters trend + pozitif
  kapanmış 3m/5m + yeni gerçek MODEL/Intent + taze
  1m Sniper/Entry koşulunu ölçen forward-only shadow
  gerekir. Merkezi Risk Master/global coin lock korunur.
- Özellikle kısa tepki hareketlerinin 5m bitişte sönmesi
  nedeniyle yalnız +%0,22 ARM görme kuralı bir strateji
  avantajı olarak kabul edilmemeli: ilk floor -%0,12
  ROI (%0,10 geri çekilme + %0,24 fee).
- Bir sonraki test: gerçek trade/aggTrade tick ile
  girişten SONRA peak/drawdown sırası, fill ve
  6 basamaklı kısmi TP maliyet hassasiyeti.
- Servisler kapalı, real orders/Redis write=0.

Kaynaklar:
- research/trace/audit_long1_avoid_context_entry_bottlenecks_v1.py
- research/trace/test_long1_avoid_context_entry_bottlenecks_v1.py
- LONG1_AVOID_ASOF_GATE_COMPARISON_20261120.json
