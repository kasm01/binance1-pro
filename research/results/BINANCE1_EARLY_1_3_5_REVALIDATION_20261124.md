# BINANCE1 — Erken Telegram sinyallerinde 1/3/5m yeniden doğrulama (gölge analiz)

Tarih: 24 Kasım 2026. Tek ortak 40 coin veri akışı korunur.
Telegram mesajları aynı şekilde gönderilir; yeniden doğrulama **yalnız araştırma kaydıdır**.
READY ve otomatik Binance emirleri kapalıdır.

## Yöntem

- Kullanıcının Telegram'a iletilmiş ilk dört erken sinyali, gerçek
  gönderimden hemen önceki kapanmış 1m fiyat referansıyla alındı.
- 1., 3. ve 5. dakikanın sonundaki **yalnız o ana kadar tamamlanmış**
  1m OHLC ve Binance taker alış hacmiyle analize devam edildi.
- Gelecek 5m bilgisi 1m kararına karışmaz; kaynak boşluğu,
  yinelenen veya kapanmamış mum **REVALIDATION_UNVERIFIED**.
- Gölge sınıflar:
  - CONTINUE_OBSERVE: yönlü kapanış >=+0.20%, adverse fiyat hareketi
    > -0.50% ve taker akışı FLOW_SUPPORTIVE.
  - INVALIDATE_RESEARCH: yönlü kapanış <=-0.40% ve adverse <=-0.50%
    veya taker akışı FLOW_OPPOSING ve kapanış <=-0.15%.
  - PENDING_RECHECK: diğerleri veya taker veri doğrulanamaması.
- Bu eşikler araştırma hipotezidir, kalibre edilmiş
  gerçekleşme olasılığı ya da işlem önerisi değildir.
- Her durumda ready=false, telegram_ready=false, order_authorized=false.
  Tüm kararlar ayrı telemetri olarak kaydedilir; hiçbir Telegram
  takip mesajı, gerçek emir ya da pozisyon lifecycle değişikliği yoktur.
- Her sinyal için ilk 1, 3, 5 dakika noktaları ayrı saklanır.
  Kaynak 65 kapalı dakika geçmişi yeterli değilse fail-closed
  olarak işaretlenir.

## Gerçek gönderilmiş dört erken Telegram sinyaline geçmişe dönük uygulama

| Saat (TR) | Sinyal | 1. dk | 3. dk | 5. dk |
|---|---|---|---|---|
| 21:11 | PIEVERSEUSDT LONG | PENDING_RECHECK | PENDING_RECHECK | PENDING_RECHECK |
| 21:15 | SAHARAUSDT LONG | PENDING_RECHECK | PENDING_RECHECK | INVALIDATE_RESEARCH |
| 21:19 | MONUSDT SHORT | CONTINUE_OBSERVE | PENDING_RECHECK | PENDING_RECHECK |
| 21:23 | GUAUSDT LONG | PENDING_RECHECK | PENDING_RECHECK | PENDING_RECHECK |

- PIEVERSE: 1m +0.0758%, 3m +0.2834%, 5m +0.2439%.
  3m/5m taker sınıfı tükenme uyarısı veriyor; 15m -0.4185%
  kapanış ayrıca daha önceki sonuç raporunda görülmüştü.
- SAHARA: 5m -0.3860% kapanış; FLOW_OPPOSING, 5m
  MAE -0.4561%. Araştırma hipotezi adayı 5m'de iptal ediyor.
- MON: ilk dakikada +0.8138% ve FLOW_SUPPORTIVE; 3m/5m'de
  taker desteği FLOW_MIXED / FLOW_EXHAUSTION_CAUTION'a dönüyor.
- GUA: ilk dakika +1.1841% yönlü kapanış, ancak aynı
  dakikayı içeren high/low yolunda -0.5921% ters hareket var.
  Bu yüzden yön iyi görünse de CONTINUE_OBSERVE verilmedi.

*Önemli*: 1m/3m/5m MFE-MAE fiyat yolu OHLC high/low'dan
hesaplanır; aynı mum içinde high ve low sırası bilinmez,
uygulanabilir emir dolumu, stop veya kâr kilidi çıkarılamaz.
Dört örnek, hipotezi doğrulamaya yetecek bağımsız örneklem değildir.

## Canlı entegrasyon

- scanner/early_revalidation_shadow_v1.py:
  kapalı veriden saf ve fail-closed kontrol; dış API/emir/Telegram yok.
- scanner/watch_outcomes_v1.py:
  1/3/5m revalidation_checkpoints ayrı kalıcı JSON anahtarında
  eski 5/15/30/60m MFE/MAE sonuçları korunarak kayıt.
- scanner/manual_watch_runner_v1.py:
  yalnız erken outcome defterine daha sonra kapanan mumlarla
  checkpoint ilerletmesi. Mevcut fiyat, maliyet, sinyal,
  Telegram ve SHORT/LONG atamaları değişmez.
- İşlem başına ekstra REST sorgusu yok; aynı 40 WebSocket
  kapalı 1m mumunun geçmişi kullanılır.
- Testler: 75 Python birim testi PASS, Stage22 ve Stage24
  yürütme/emir güvenliği regresyonları PASS.

## Sıradaki bilimsel doğrulama

Birden fazla gün/regime aynı kuralları hiç değiştirmeden izlemek,
gerçekte Telegram'a gönderilmiş erken sinyallerin 1/3/5m
kararlarını aynı zaman damgasında saklamak, 15/30/60m
sonuçlarını bağlamak ve zamana/coin'e göre kümelenmiş sonuçları
karşılaştırmak. Ayrıca bu tip yeniden doğrulamalar,
Telegram gönderimi üzerine çıkış sinyali değildir:
bunlar araştırma gölgesidir.
