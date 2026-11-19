# LONG1 — Binance arşiviyle 103 MODEL sinyalinde 3 giriş profili ve maliyetli replay

19 Kasım 2026, TRT. NEARUSDT USDⓈ-M, yalnız LONG1.
Çalışma **SHADOW / NO-GO**. Üretim .env, strateji executor veya
ortak Risk Master canlı emir engeli değiştirilmedi. SHORT1 kapsam dışı.

## 1. Veri ve giriş kararının zaman doğruluğu
- 10–15 Kasım UTC Binance resmî arşivi, 12 SHA256 doğrulanmış ZIP,
  8.640 adet 1m kline, 979.324 aggTrades. 103 adet gerçekte
  gözlenmiş MODEL LONG sinyali; 11 LONG_TARGET, 70 LONG_AVOID,
  21 UNLABELLED, 1 CONFLICT.
- Kaynak Binance kline kendi signed taker flow verisi. 95 dakikada
  aggTrades/kline işlem sınırı uyuşmadı; kline kendi hacmi kullanıldı.
- MODEL sinyalinin anında **zaten kapanmış** 1m mumdan bağlam hesaplanır.
  Sonraki 1–5 kapanmış mumda context yeniden kontrol edilir;
  karar verildikten SONRAKİ 1m OPEN, varsayımsal giriş fiyatıdır.
  İşleme giriş için gelecek mum high/low kullanılmaz.
- Sinyalden itibaren as-of 1m pozitif gövde, üst retrace, 1/3/5/15m
  signed taker flow ve 3m/5m fiyat dönüşü kullanıldı.
- Gerçek MasterExecutor whale-veto, gün içi kısmi 1m Sniper/Entry
  Confirmation, 3m/5m çalışan botun önbellek durumu ve birebir
  PENDING yeniden niyet zinciri yeniden üretilmedi. Buradaki READY
  **sadece araştırma giriş şartları** anlamında kullanılır.
- Kullanıcının geçmiş LONG_TARGET/LONG_AVOID etiketleri giriş
  şartlarını seçmez. Etiketler sonuçları gruplamak içindir;
  **çakışma** ise kullanıcı isteği gereği her zaman NO_TRADE.
- 103 MODEL sinyalinden 1'i gerçek rolling score eşiğinin altında;
  bir diğeri CONFLICT origin; ikisi de yeni emir açmaz.

## 2. Karşılaştırılan ayarlar (canlıda YOK)
| Giriş araştırma profili | 1m body/range min | üst retrace max | 1m taker flow min | 3m flow toparlanma | 3m fiyat değişim iyileşmesi | İlave şart |
|---|---:|---:|---:|---:|---:|---|
| Strict recovery | 0,22 | 0,35 | +0,03 | +0,08 | +0,10 yüzde puan | 3m fiyat ve 3m flow pozitif |
| Balanced pending | 0,15 | 0,50 | −0,03 | +0,04 | +0,05 yüzde puan | 3m pozitif zorunlu değil |
| Cautious relaxation (esnek) | 0,10 | 0,60 | −0,15 | −0,03 | −0,05 yüzde puan | Daha az veto |

Her profilde **en fazla 5 tamamlanmış 1m PENDING yeniden kontrolü**.
3m flow/fiyat iyileşmesi, model anındaki kapanmış mum verisiyle
kıyaslanır; ileri tarihli karar verisi ile başlangıç koşulu üretilmez.
Gerçek LONG1 ayarları ile eşdeğer bir replay değildir.

## 3. 103 sinyal → karar → tek pozisyon portföyü
Ortak varsayımlar: 3x kaldıraç, TP +%1,25 brüt ROI, fiyat SL
−%2,99 (yaklaşık −%8,97 brüt 3x ROI), maksimum 60m,
aynı mum TP+SL varsa STOP önce, round-trip %0,08 notional ücret
(~0,24 ROI puanı). Funding, spread, slippage, likidasyon,
native stop ve gerçek dynamic profit-lock bu replayde yok.

| Profil | Araştırma READY | Tek pozisyonla simüle açılış | TP_FIRST | SL_FIRST | 60m TIMEOUT | Net ROI puanı toplamı |
|---|---:|---:|---:|---:|---:|---:|
| Strict recovery | 32 | **20** | 12 | 1 | 7 | **−21,954** |
| Balanced pending | 59 | **36** | 23 | 2 | 11 | **−31,533** |
| Cautious relaxation | 81 | **43** | 30 | 4 | 9 | **−44,475** |

Toplam ROI puanı bir araya toplanan hipotetik işlem ROI'leridir;
gerçek sermaye büyümesi, USDT P&L veya kesin net borsa sonucu DEĞİLDİR.
Bu örneklemde hiçbir profil net pozitif değil.

| Profil | LONG_TARGET 11'den READY | LONG_TARGET açılan | LONG_AVOID 70'ten açılan | Etiketsiz açılan | Çakışmada açılan |
|---|---:|---:|---:|---:|---:|
| Strict | 6 | 4 | 11 | 5 | **0** |
| Balanced | 9 | 4 | 24 | 8 | **0** |
| Esnek | 9 | 2 | 29 | 12 | **0** |

Esnek profilde açılabilir hedef sinyali artsa da tek pozisyon
çakışması ve daha uzun taşıma yüzünden açılan LONG_TARGET sayısı
**2'ye düşüyor**. Yalnız sinyal sayısını artırmak hedef
fırsatları yakaladığımızı göstermez.

## 4. Zarar ve stop duyarlılığı
Gerçekçi zarar büyüklüğü sonucu belirlediği için araştırma
stop fiyat mesafelerini de değiştirdik. Aşağıdaki bütün
değerler yine **sanal net ROI puanı toplamıdır**.

| Profil | Stop %0,65 fiyat | Stop %1,00 fiyat | Stop %1,50 fiyat | Stop %2,99 fiyat |
|---|---:|---:|---:|---:|
| Strict | −25,110 (29 işlem) | −27,497 (27 işlem) | −31,517 (25 işlem) | −21,954 (20 işlem) |
| Balanced | −28,490 (51) | −36,892 (49) | −41,622 (44) | −31,533 (36) |
| Esnek | −29,170 (63) | −31,042 (59) | −53,093 (53) | −44,475 (43) |

Daha dar stop ile daha çok işlem açılabilir; ama sık stop olduğu
için toplam net sonuç burada pozitif olmuyor. Tek model
setinin 12 varyasyonla denenmesi sonuçları doğrulamaz;
**başka tarih** ile out-of-sample gerekli.

## 5. Gerçek tarihsel açık LONG pozisyonlarıyla çakışma
10 mevcut Binance-broker doğrulanmış LONG açılışının zaman
aralıkları **ayrı duyarlılık analizi** olarak risk kapısına
yerleştirildi (orijinal portföyün yeni simülasyonla gerçek
birleşimi değildir). Stop %2,99 iken:
- Strict: 20 → **17** farazi yeni LONG; ROI puanı toplamı −5,876.
- Balanced: 36 → **30**; −29,480.
- Esnek: 43 → **36**; −37,123.
Bu karşılaştırma hem geçmiş gerçek pozisyonu hem potansiyel yeni
pozisyonu ayrı kök nedenlerle sayar; gerçek backtest sonucu değildir.
Gerçek 10 LONG'un gerçekleşmiş fiyat P&L −0,052 USDT;
funding ve yaklaşık BNB komisyonuyla −0,311 USDT ayrı kanıttır.

## 6. Çakışan saat kuralı
Ortak referansın 7 çakışma segmentinde gerçekte 0 Binance
LONG açılışı vardı. Bu simülasyonda çakışma içindeki tek
MODEL LONG sinyali de **REJECT_CONFLICT_ORIGIN** alıyor.
Gelecek zaman etiketlerini “izin verilen saatler” olarak
otomatik trading sistemine eklemedik. Tek pozisyon kuralı korunuyor.

## 7. Ayar kararları
- Üretim LONG1 model, Master whale=0,45, Sniper, Entry
  Confirmation, Contra-Trend, PENDING, Risk Master, Native Stop,
  .env veya servislerde değişiklik YOK.
- Yeni **research/staging/long1_research_only_settings_v2.json**
  Strict Recovery profilini, 5 kapanmış mum revalidation,
  tek pozisyon, çakışma veto, %1,25 brüt TP ve fiyat stop
  %2,99 referans deney şartlarını tutar.
- Bu profil **kârlı bulunduğu için seçilmedi**; üçü de
  zarar ettiği için güvenli varsayımları bozmadan yeni dönem
  üzerinde karşılaştırma yapmaya başlangıç olacak en katı profil.
- Bu profilin gerçek emir yetkisi YOK. Üretim ayarlarını
  gevşetmek için şart: bağımsız gelecek dönem, as-of tam
  1m Sniper/Entry, whale/3m/5m context, stop/lock,
  funding/slippage ve gerçek 8-bot Risk Master kontrolleri.

## Tekrar çalıştırılabilir dosyalar
- research/trace/replay_long1_103_asof_three_profiles_v1.py
- research/trace/long1_103_stop_and_real_occupancy_sensitivity_v1.py
- research/trace/test_long1_103_archive_replay_safety_v1.py
- research/results/LONG1_NEW_BINANCE_103_ASOF_3PROFILE_REPLAY_20261119.json
- research/results/LONG1_NEW_BINANCE_103_STOP_SENSITIVITY_20261119.json

Ham veri yerel cache'de, GitHub'a yüklenmedi. Emir POST yok,
üretim Redis yazması yok, bot servisi açılmadı.
