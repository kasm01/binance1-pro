# Binance1 — LONG1 / SHORT1 Telegram WATCH pilotu ve token denetimi

24 Kasım 2026, Google Cloud. Otomatik Binance emirleri kapalı.

## Yapılanlar
- 40 coinin verisini tek WebSocket ile izleyen binance1-manual-watch.service çalışıyor.
- Yeni tg_bot/pilot_watch_alert_v1.py yalnız LONG1 ve SHORT1 stratejileri için güçlü hareket WATCH uyarısı hazırlar.
- Yalnız STRONG_WATCH veya EXTREME_WATCH, doğru LONG/SHORT yönü ve botun kendi 10 coin dilimi uygunsa aday üretilir. Zayıf, sıradan WATCH ve temkinli ekstrem uyarılar Telegram'a yönlendirilmez.
- Kaynak kapanmış 1m bar kimliği, yön, stale kontrolü ve telegram_ready=False, order_authorized=False fail-closed.
- Yeni gönderici iki ayrı env opt-in ve yetkili sohbet gerektirir; 2 saat aynı coin/strateji durumu tekrar gönderimini önler (process içi).
- Telegram HTTP çağrısı ayrı asyncio.to_thread içinde, websocket veri işleme aşamasını bloklamaz.
- Telegram gönderimi sayacı status JSON'a eklendi. Telegram /signals komutunda WATCH status alanı gösterimi düzeltildi.
- Eski trade executor ve Binance işlem kodu kullanılmıyor.

## Kritik Telegram engeli
Bir açıkça TEST olarak işaretlenmiş tek mesaj gönderme girişimi başarısız oldu. API success doğrulanmadı.
Telegram getMe, getChat ve getWebhookInfo çağrılarının tamamı HTTP 401 Unauthorized döndürdü.
Mevcut bot token yanlış veya artık geçerli değil. **Test mesajı teslim edilmediği için başarı iddia edilemez.**
Telegram izleme servisi gönderim bayrakları sıfır bırakıldı, komut poller da kapalı.
Gerçek Telegram sinyali henüz gönderilemiyor; WATCH ve coin takip yerel olarak çalışıyor.

Eski .env içindeki Telegram token ve chat kimliği, Binance trade API credential kopyalamadan,
özel 0600 izinli ~/.config/binance1-manual-signal/telegram.env dosyasına taşındı.
Token/chat ID çıktı ve GitHub raporuna yazılmadı.

Yeni tg_bot/telegram_auth_probe_v1.py yalnız --check-auth ile Telegram getMe + getChat yapar,
asla mesaj göndermez. Sonuç BOT_TOKEN_UNAUTHORIZED ise bildirim kapalı tutulur.
BotFather'dan token'ı kullanıcı yenileyip VM üzerindeki private telegram.env içine koymalı.
Sohbete asla token yazılmamalı.

## Operasyon ve testler
Servis açık, eski LONG1/SHORT1 otomatik trading servisleri kapalı.
Unit deploy/systemd/binance1-manual-watch.service özel Telegram env dosyasını okur,
ama TELEGRAM_SIGNAL_CENTER_ENABLED=0 ve TELEGRAM_SIGNAL_CENTER_SEND_ENABLED=0.
Testler: 31 unittest (yeni pilot, auth ve eski scanner/telegram), PASS.
Ayrıca Stage22 exact Intent ve Stage24 order safety regresyonları kontrol edilir.

Sonraki çalışma: Geçerli token ile AUTH_AND_CHAT_VALID, ardından tek test mesajı
teslim doğrulaması; sonra kontrollü LONG1/SHORT1 WATCH bildirim pilotunun açılması.
READY henüz üretilmiyor. Canlı ticaret açılmıyor.
