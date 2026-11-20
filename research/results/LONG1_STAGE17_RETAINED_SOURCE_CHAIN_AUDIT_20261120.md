# LONG1 Aşama 17 — Forward-only kaynağa hazırlık ve Redis salt-okunur denetim

20 Kasım 2026. Yalnız LONG1 / NEARUSDT. Bütün servisler kapalı ve
merkezi Risk Master canlı emir yetkisi NO-GO. Hiçbir gerçek Binance emri yok.

## Sonuç
Mevcut üretim Redis akışlarını yalnızca XRANGE/XREVRANGE/XLEN
tipi salt-okunur komutlarla tek sefer, üst sınır 3000 kayıt/stream
olarak denetledik. Kullanıcı tetikleyicisi olmadan denetleyici
Redis'e dahi bağlanmaz. Hizmet olarak başlatılmadı.

| Source | İncelenen kayıt |
|---|---:|
| signals_stream_long1 | 2473 |
| candidates_stream_long1 | 894 |
| trade_intents_stream_long1 | 285 |
| LONG trade intents içinde tam Stage6→Stage7 zinciri doğrulanan | 0 |
| Tam soy kimliği doğrulanamayan | 285 |

285 LONG Intent'in tamamında, kanonik üst düzey
source_candidate_stream_id değeri, saklanmış aday stream kaydını
tanımlayamadığı için kaynak zinciri doğrulanmadı.
Bu, tarihsel Intent'in sahte veya yanlış işlem olduğu
anlamına gelmez. Kayıtlar mevcut tam lineage şemasından
önce oluşturulmuş olabilir; eski veriye sonradan eksik
model veya candidate parent kimliği atanamaz.
Kayıtları zaman/fiyat/skor benzerliğinden birleştirip
kesin lineage iddiasında bulunmadık.

## Teknik tasarım
- research/trace/audit_long1_stage17_readonly_source_chain_v1.py
- Varsayılan CLI: DISABLED; Redis bağlantısı yok.
- Açıkça audit-readonly parametresiyle run: maximum 3000
  kayıt/stream (izin verilen range 100-5000).
- Signal/Candidate/Intent açık transport id'leriyle
  Stage16 gerçek kaynak zinciri fonksiyonu karşılaştırılır.
- Sadece aggregate sayım, hata nedenleri ve kişisel
  veri içermeyen en çok beş örnek neden tutulur.
- Üretim Redis'e XADD/SET/DEL yazılmaz; order emit yok.
- Hafıza/Redis I/O sınırlandırıldı; ücretli harici API yok.

## Test
test_long1_stage17_readonly_source_chain_v1.py:
- Sentetik, tam kaynak kimliği olan bir zincir -> exact source.
- Dokuz eksik/tahrif edilmiş kimlik durumu -> asla exact yok.
- Varsayılan CLI kullanımında ağ erişimi yok.
- Pozitif exact source bile ORDER authority yaratmıyor.
- Stage15/Stage16/Stage24 önceki güvenlik kontrolleri korunuyor.

## Kritik mimari karar
Aşama14'te geçmiş 32 research READY sinyalinin hiçbiri
tam gerçek model-intent parent ile onaylanmamıştı.
Yeni retain audit 285 historical Intent'te de tam kaynak
kanıtı bulunmadığını gösteriyor. Bu nedenle canlı LONG
giriş mantığı veya günlük işlem hedefi mevcut arşive göre
gevşetilmeyecek.

Bir sonraki aşama, gerçek üreticilerin bu kanonik alanları
gelecekteki MODEL/SIGNAL/CANDIDATE/INTENT olaylarında
tutarlı yazdığını ayrı bir forward-only shadow kaynak
testi ile ölçmektir. Bu kez gerçek yeni event akışı yok:
servisleri başlatmadık, varsayılan kapalı Stage11/12
gözlemcisini etkinleştirmedik. Tam kimlik + yeni Intent,
1m Entry, 3m/5m Market Context ve Risk Master kanıtları
birleşmeden GO yok.

## Çıktı
LONG1_STAGE17_RETAINED_SOURCE_CHAIN_READONLY_20261120.json
Yalnız araştırma modülü, regresyon testi ve rapor;
TradeExecutor, MasterExecutor, LIVE env, SHORT1, merkezi
risk, pozisyon lifecycle ve native stop değiştirilmedi.
