# LONG1 Stage11 — Sniper, Entry Confirmation ve PENDING kararları için opt-in trace

19 Kasım 2026. Yalnız LONG1 NEARUSDT. Ortak Risk Master LIVE OPEN NO-GO sürüyor.

## Amaç
Gerçek LONG1 yürütücüsündeki karar değişimlerini aynı mevcut kaynak kimlikleriyle
küçük, bounded ve fail-closed bir shadow kayıt akışına bağlamak. Gerçek giriş
stratejisini, eşikleri veya ORDER kararını değiştirmemek.

## Kod
- orchestration/trace/long1_entry_decision_audit_v1.py:
  kaynak lineage alanlarını mevcut compact() fonksiyonuyla aynen taşır.
  Model-score/tarih sezgisiyle eksik parent uydurmaz.
- core/trade_executor.py: Sniper kararından, Entry Confirmation kararından,
  yeni PENDING oluşturulmasından ve PENDING yeniden kontrolünden sonra
  sadece gözlemciyi çağırır.
- Kaydedilenler: kararın stage/action/reason bilgisi; kalite, body,
  retrace, progress, skor gibi varsa gerçek karar metrikleri;
  intent_id, model_evaluation_id, parent_trace_id ve pending_attempt_id.
- pending_origin_intent_id eski niyet, pending_recheck_intent_id yeni
  niyettir. Birbiri yerine geçirilmez.
- Kaydın advisory_only=true ve order_authority=false alanları sabittir.

## İşlem maliyeti, kontrol ve emniyet
- Varsayılan ayar LONG1_ENTRY_DECISION_TRACE_SHADOW_ENABLE kapalı.
  Üretim .env üzerinde bu değişken eklenmedi veya açılmadı.
- Etkinleşirse Redis stream telemetry:long1:entry_decision_trace:v1
  yaklaşık 2500 kayıtla sınırlı kalır (XADD MAXLEN APPROX).
  Aynı intent/pending_attempt/stage için tekrar eden action+reason
  ayrı yazılmaz. Bütün 1m mikro-snapshot verileri kopyalanmaz.
- Observer hata verirse bütün istisnalar yakalanır; karar değişmez.
  SHORT1, farklı semboller, emir servisi ve stop kodu değiştirilmedi.
- Tam 3m/5m recovery ve karar mum kimliği bu Stage11 kaydıyla henüz
  doğrulanmış değildir: her event içinde iki bağımsız kanıt alanı
  false olarak işaretlenir. PENDING ready emre yetki vermez.

## Testler
- test_long1_entry_decision_shadow_observer_stage11.py PASS:
  bağımsız Redis Unix socket port=0; 5 durum-değişimi event,
  yinelenen kararların filtrelenmesi, immutability ve default-off
  0 Redis yazımı.
- test_long1_stage8_exec_pending_outcome_isolated.py PASS:
  gerçek pending store, origin→recheck→outcome lineage.
- test_long1_candidate_to_intent_stage9.py PASS: 120 retained
  aday örneği, payload eşleşmeleri.
- test_stage24_live_guard_long_strict_v1.py PASS: gerçek Binance
  emir yetkisi verilmez, merkezi sıkı veto korunur.
- Eski test_long1_metadata_no_decision_delta_stage8.py,
  yeni observer kodundan bağımsız eski Aggregator fixture'ında
  .bus nesnesi atanmamış olduğundan AttributeError verdi;
  bunu Stage11 davranış regresyonu olarak göstermiyoruz.

## Sınırlar ve devam
Yeni kod yalnız kullanıcı açıkça etkinleştirirse gelecekteki
kararları gözlemler. Durmuş botlarla eski 11–16 Kasım kararlarına
yeni exact trace kimlikleri eklenmiş sayılmaz. Sıradaki iş,
tam kapanmış 3m/5m context mum kimlikleriyle Contra-Trend
revalidation kanıtını bu stream'e güvenli şekilde eklemek,
sonra gerçek tam-zincir shadow READY durumunu araştırmak.

Hiç emir gönderilmedi, canlı servis açılmadı, üretim Redis'e
yazılmadı veya canlı .env ayarı değişmedi.
