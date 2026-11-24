# Binance1 — Ortak 40 coin izleme servis kurulumu

24 Kasım 2026. Binance USDT-M Futures üzerinde manuel-only, public-data market WATCH sistemi kuruldu.

## Gerçek test kanıtları
- Binance 2026 WebSocket adresi wss://fstream.binance.com/market/stream?streams= kullanılmalı; önceki /stream adresi bağlantı kabul ediyor görünmesine rağmen veri göndermiyordu.
- Yeni adreste 40 coin, 83 saniye kontrollü tek WebSocket testi: **3949 veri mesajı, 40 tam kapanmış 1m mum, 1 WATCH, 0 kopma, 0 Binance emir, 0 Telegram mesajı**.
- 40 REST kline bootstrap ilk testte 20/40 çıktı; istek başındaki as-of zamanı 40 sorgu sürerken yeni kapanmış mumları geçersiz sayıyordu. Her REST isteğinin bittiği zamandaki Binance server-clock uyarlanmış zaman kullanılarak 40/40 geçerli, 6 WATCH gözlemi oldu.
- WATCH kârlı bir AL/SHORT sinyali değildir. READY ve emir yetkisi sıfır.

## Kurulan servis
- systemd user unit: binance1-manual-watch.service
- Repo unit: deploy/systemd/binance1-manual-watch.service
- VM unit: ~/.config/systemd/user/binance1-manual-watch.service
- Durum: active/running. İlk kontrol PID 8142, ~46 MB RAM, 0 restart.
- Boot policy: disabled (VM reboot sonrası otomatik başlamaz); user linger=yes.
- 40 farklı coin, tek stream; aynı kaynak LONG1..4 ve SHORT1..4 için ortak.
- Dynamic universe yeniden seçim: 30 dakikada bir planlı, ayrıca websocket kopma/15s no-events sırasında REST refresh ve reconnect.
- Kapanmamış kline, duplicate, gap, stale ve bozuk veri fail closed. REST bootstrap dışında Binance'e sadece WebSocket public read.
- Yenilenme ve reconnect dayanıklılığı 24h gerçek kullanımda henüz doğrulanmadı.
- Yerel snapshot: run/signal_center/status.json (izinler 0600, dizin 0700).
- Telegram systemd unit Environment ile kapalı: TELEGRAM_SIGNAL_CENTER_ENABLED=0, TELEGRAM_SIGNAL_CENTER_SEND_ENABLED=0.
- Binance trading execution, eski LONG/SHORT supervisors/orchestrator, Redis ve PostgreSQL kullanılmıyor. Eski emir servisleri KAPALI.
- Strateji motorları şimdilik WATCH izleme seviyesinde; READY giriş/çıkış modeli ve performans henüz kurulmadı.

## Kullanım
Sadece izleme:
- cd ~/binance1-pro
- ./scripts/manual_watch_control.sh status
- ./scripts/manual_watch_control.sh start
- ./scripts/manual_watch_control.sh stop
- ./scripts/manual_watch_control.sh restart

UYARI: ./shadow_start.sh eski LONG/SHORT emir stack'ini başlatabilir. Manuel izleme için ASLA kullanma. ./shadow_stop.sh keşfedilen bütün binance1-* servislerini durdurur, native-stop güvenlik preflight'i eskisi gibi korunur.

## Kaynak ve maliyet
- Her 30 dakikalık universe refresh yaklaşık 43 public REST request (40 sembol + 3 metadata), 24 saat boyunca yaklaşık 2064 request artı reconnect. WebSocket tek multiple market bağlantısı.
- Mevcut Google Cloud e2-medium VM ücreti devam ediyor; Redis/PG RAM ihtiyacı ayrı mesele.
- Üç yeni pure cache testi ve önceki 22 test dahil toplam 25 unittest PASS.
- Gerçek otomatik emir ve Telegram gönderimi YOK.
- Telegram bildirimini gerçek bağlantıda açmadan önce açık onay, test mesajı, duplicate/spam ve gerçek gönderim doğrulaması gerekli.
