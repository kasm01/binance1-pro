# LONG1 Aşama 18 — İleriye dönük tam kaynak kimlik denetimi

20 Kasım 2026, TRT. Sadece LONG1 NEARUSDT.
**Tüm bot servisleri kapalı, merkezi Risk Master canlı OPEN NO-GO.**
Bu aşama kendiliğinden yeni MODEL veya Intent üretmez.

## Gerçek üretim zinciri denetimi
- main.py: model_evaluation_id her MODEL hesaplaması için üretilir;
  decorate_model_signal kaynak sinyalin üst seviyesine ekler.
- Aggregator: candidate_parent() sinyalin GERÇEK Redis transport
  ID'sini ve model evaluation kimliğini adayın üst seviyesine taşır.
- TopSelector: _source_stream_id adayın Redis ID'sidir.
- MasterExecutor: candidate_intent_parent() adayın transport
  ID'sini ve kanıtlanabilen üst parent kimliğini Intent'e ekler.
- Burada model_close_id_kind = wallclock_bucket_180s
  gerçek Binance tamamen kapanmış mum kimliği DEMEK DEĞİL.
- Hiçbir geçmiş MODEL/Intent soy bağlantısı
  skor, fiyat veya zaman benzerliğiyle uydurulmaz.

## Kurulan ileriye dönük audit
Yeni kod: research/trace/long1_stage18_forward_only_source_audit_v1.py

- Varsayılan CLI: DISABLED. Redis bağlantısı yok.
- Bir kez --initialize-cursor: ÜÇ kaynak akışının mevcut
  son Redis transport ID'sini **lokal gitignore dosyasında** saklar.
  Üretim Redis üzerinde SET/XADD/XDEL yazmaz.
- --audit-forward: Yalnız son Intent cursor ID'sinden daha
  yeni event'leri XRANGE exclusive ile inceler.
- Yeni Intent bulunduğunda bunların açık candidate/signal parent
  Redis ID'lerini sınırlı, read-only arşivden doğrular.
- --advance ayrıca verilmeden cursor ilerlemez. --advance ile
  önce lokal rapor atomik olarak yazılır, sonra yalnız lokal
  cursor atomik güncellenir.
- Kaynak trimming nedeniyle parent eksikse NOT_PROVEN.
  İlerleyen backlog 3000 sınırını aşarsa --advance engellenir.
- Yeni Intent yoksa binlerce önceki SIGNAL/CANDIDATE Redis kaydı
  tekrar okunmaz; yalnız basit XLEN kontrolleri yapılır.
- Doğrulama asla ORDER authority yaratmaz.
- Hiç ücretli harici API, daemon, timer veya collector kurulmadı.

### Başlangıç watermark'ları (servisler kapalıyken)
| Kaynak | Yeni kayıt sınırı |
|---|---|
| signals_stream_long1 | 1794845694935-0 |
| candidates_stream_long1 | 1794845651905-0 |
| trade_intents_stream_long1 | 1794842643079-0 |

Cursor dosyası araştırma cache'inde:
research/local_market_data/long1_stage18/forward_cursor.json
GitHub'a dahil EDİLMEDİ. Aynı VM'de saklanmalı; silinirse
yeni baseline eskiden kaçan eventleri tespit edemez.

### Başlangıç ve tekrar kontrol sonucu
- Gerçek retained stream adetleri: 2473 SIGNAL, 894 CANDIDATE,
  285 eski TRADE INTENT.
- Başlangıç sonrası **0 yeni Intent batch**.
- Eski 285 intent yeniden sayılmadı.
- 0 tam yeni parent zinciri; yeni üretim olmadığı için
  bu sayı gelecekteki gerçek producer kalitesi hakkında kanıt değil.
- 0 Binance emri, 0 üretim Redis yazısı.
- İkinci kontrol 0 yeni Intent'te 0 eski SIGNAL/CANDIDATE
  payload satırı okudu; gereksiz tarama yok.

## İzole testler
- test_long1_stage18_forward_only_v1.py: source chain exact,
  sadece yeni Intent, aynı cursor tekrarında 0 kayıt,
  bozuk/trimmed parent reddi, varsayılan CLI OFF.
- Stage17 retained-source, Stage16 gerçek parent,
  Stage24 canlı güvenlik vetosu testleri PASS.
- Bu aşama mevcut LONG1 executor/entry/STOP/risk davranışını
  değiştirmez; servisler kapalı kalır.

## Sonraki adım
Yeni REAL üretim event'leri yalnız kullanıcı canlı servis
başlatmaya izin verdiğinde ve Risk Master güvenli koordinasyon
tamamlandığında ortaya çıkabilir. Bunlar ortaya çıktığında
bu CLI ile forward-only denetim yapılarak tam kaynak soyunun
korunup korunmadığı incelenmeli. Tarihi 32 READY veya 18
farazi açılışı emir yetkisi gibi yorumlamamak gerekir.
SHORT1 ve diğer LONG örneklerine müdahale yok.
