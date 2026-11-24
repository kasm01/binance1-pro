# Binance1 / Google Cloud — Yalnız izleme mimarisi maliyet ve servis denetimi

Tarih: 24 Kasım 2026, Google Cloud projesi binance1-476019.
Çalışma **sadece araştırma**: LONG1 / SHORT1 / Risk Master trading services yeniden başlatılmadı; emir ve Telegram mesajı gönderilmedi.

## Compute kaynakları

- Google Cloud region/zone: europe-west2-b (Londra).
- **Bir VM**: binance-bot-vm, RUNNING, e2-medium (2 vCPU / 4 GB RAM).
- **Bir bağlı boot disk**: 40 GB **pd-standard**, %83 dolu (yaklaşık 6.6 GB kullanılabilir).
- **Bir statik dış IP**: binance-static-ip, IN_USE. Kullanılmakta olan IP bağlantı/SSH için gerekli olabilir, silinmedi.
- Başka Compute Engine VM veya disk listelenmedi.
- Cloud Run (europe-west2) listesinde çalışan servis bulunamadı.
- Cloud SQL Admin API etkin değil: bilerek etkinleştirilmedi.
- Cloud Scheduler API etkin değil: bilerek etkinleştirilmedi.
- App Engine uygulaması yok.
- GCS: 2 mevcut bucket: binance1-476019_cloudbuild (245592011 bayt);
  run-sources-binance1-476019-europe-west2 (114510175 bayt).
  Toplam yaklaşık 360 MB. Silinmedi, olası build artifactleri içeriyor.

## VM üzerindeki servisler

- Kullanıcı binance1 LONG/SHORT servis/timer/collector: **0 çalışan, 0 enabled**.
- Systemd kullanıcı servisi: 0 running; timers: 0.
- Redis: running, enabled, yaklaşık 628 MiB used memory; Redis process ~647 MiB RSS. RDB persistence açık, AOF kapalı. 1 bağlantı (audit command'ın kendisi olabilir).
- PostgreSQL 15: running, enabled, tüm postgres process RSS toplamı yaklaşık 69 MiB; DB içeriğine yetkisiz dokunulmadı.
- Exim4 mailer: running, enabled, yaklaşık 17 MiB RSS.
- cron: running, enabled (sistem hizmeti; kapatılmadı).
- SSH / networking / Google Guest Agent / OSConfig / journald:
  **kritik sistem servisleri korunuyor**.
- Desktop Commander remote agent: ChatGPT'nin VM erişimi, kapatılmadı.

## Yapılan tek aktif kapatma

Yalnız kullanıcının crontab'ında, eski repo
/home/kasm920/binance1/scripts/clean_logs.sh
dosyasını her gün 04:00'te çalıştıran iş COMMENT haline getirildi.

**Gerçek durum kontrolü:** crontab'da aktif satır kalmadı.
Önceki crontab yerel klasöre yedeklendi:
run/ops/cron_before_manual_signal_cleanup_20261124.txt
Bu dosya bilerek GitHub'a yüklenmedi.
Diğer crontab satırları ve servisler değiştirilmedi.

Cron servisi sistem düzeyinde hâlâ açık; sadece eski bot
temizleme görevi iptal edildi. Log dosyaları silinmedi.

## Durdurulmayan ve nedenleri

Redis / PostgreSQL / Exim4, sistem systemd servisleridir;
uzak bağlantı bu ortamda yönetici komutunu çalıştırmayı
engelliyor. Redis yaklaşık 628 MB veri belleğinde tutuyor,
historical provenance araştırmaları için önem taşıyabilir.
RDB içerik yedeği teyit edilmeden veya gerekli yeni
collector bileşenleri tasarlanmadan shutdown yapılmadı.
PostgreSQL servisinin veritabanı içeriği bilinmeden silinmedi.
Hiçbir veri, VM veya bucket silinmedi.

**Potansiyel daha sonra yapılabilecek tasarruf:**
Yetkili shell üzerinden Redis snapshot'ı ve Postgres
gereksinimi teyit edildikten sonra gereksiz hizmetleri
önce stop+disable, ardından VM RAM testi; başarılıysa
e2-medium yerine e2-small değerlendirilebilir.
Şu an VM küçültülmedi, çünkü gelecekteki 40 coin
live shared WebSocket motorunun RAM/CPU load profili
ölçülmedi.

## Aylık yaklaşık hesap (730 saat, indirim/vergiler hariç)

- e2-medium europe-west2 ~$0.0432/saat ×730 = ~$31.54/ay.
- pd-standard Londra 40 GB ×$0.048/GB-ay ≈ $1.92/ay.
- Kullanımdaki statik IPv4 ~$0.005/saat ×730 ≈ $3.65/ay.
- **Yaklaşık toplam $37.1/ay** + küçük Cloud Storage,
  egress/Cloud Logging/ağ ücretleri ve vergiler.
- Bu **gerçek faturadaki tutar değil**. Billing SKU,
  vergi/kur, indirim veya Google Cloud kredisi
  hesaba katılmadı. Cloud Billing projesi etkin.

Bu maliyetin hemen hemen tamamı VM'nin çalışması,
kalıcı disk ve IP'dendir; **Redis/PG/Exim birer
ayrı faturalanan Cloud SQL/Memorystore değildir**.
Yalnız Redis servisini kapatmak doğrudan VM saatlik
fiyatını azaltmaz.

**VM durdurulursa** işlemci kullanımı sona erer,
ama disk ve ayrılmış IP ücretleri devam edebilir.
VM stop GCP üzerinden erişimi kestiği için
izinsiz yapılmadı: 7/24 Telegram sinyal takibi
gerekiyorsa VM açık kalmalıdır.

## Önerilen sıradaki aksiyonlar

1. Yeni shared 40-coin veri toplama motorunu önce 10 coinlik
   manuel/tek seferlik profil ile CPU/RAM testine tabi tut.
2. Yönetici izinleriyle güvenli Redis/PG yedeği ve
   shutdown/disable planı tasarla; veri yok etme yok.
3. 40 coin / 8 strateji aynı WebSocket feed'i paylaşınca
   e2-small için peak memory / CPU / reconnect kapasite
   karşılaştırması yap; ancak sonra küçült.
4. Cloud Billing > Reports / Cost table üzerinde gerçek
   SKU harcamaları, Cloud Storage, IP ve egress ayrıca
   kontrol edilsin. Bu rapor gözlenen anlık kaynakların
   maliyet tahminidir, fatura doğrulaması değildir.

Google Cloud kaynak listesi ve servis durumu VM'nin
CLI ve systemctl çıktılarıyla doğrulandı. Fiyat
kaynakları Google Cloud resmî Compute, disk, IP fiyatları
ile e2-medium Londra bölgesinin güncel maliyet
tablolarıdır. Durum tekrar denetlenmeden eski
kayıtlar üzerinden kaynak silinmemelidir.
