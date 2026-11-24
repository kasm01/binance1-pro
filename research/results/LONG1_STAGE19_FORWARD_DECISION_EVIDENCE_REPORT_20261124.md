# LONG1 Aşama19 — Forward-only Entry karar / Intent kimlik denetimi

24 Kasım 2026, NEARUSDT LONG1. Varsayılan kapalı,
salt-okunur denetim. Üretim servisleri, canlı
strateji, TP/SL, LONG1/SHORT1 ve merkezi Risk Master
ayarları DEĞİŞMEDİ.

## Sorun ve yöntem

Eski 84 LONG_AVOID giriş sentetik araştırma sinyalleridir.
11–15 Kasım arşivinde 103 gerçek LONG MODEL olayı
bulunur, ama eski 285 LONG trade-intent'in hiçbiri
kanonik Signal→Candidate→Intent source transport
kimliğiyle doğrulanamamıştır. Bu nedenle zaman/score
ile geçmiş bir trade'i gerçek modele bağlamıyoruz.

Stage18 denetiminden sonra eklenen Stage19,
yeni trade-intent kayıtlarının explicit transport parent
alanlarından Stage6 candidate_parent ve Stage7
candidate_intent_parent kaynak kimliğini TEKRAR türetir.
Kısmi / eksik / bozulmuş / kırpılmış veya yinelenen
intent zincirini kesin olarak kanıtlanmış saymaz.

Sadece kaynak zinciri doğrulanan yeni intent ID'leri,
gerçek executor Stage11 shadow karar akışındaki
aynı intent_id ile eşleştirilir. Saat, skor, fiyat
ve geçmiş WANTED/AVOID etiketleri eşleştirme
anahtarı olarak kullanılmaz.

## Güvenlik karar matrisi

| Durum | Stage19 sonucu |
|---|---|
| Parent chain eksik veya bozuk | NO_EXACT_SOURCE_PARENT |
| Kaynak kanıtı var, Entry kaydı yok | TRACE_MISSING |
| Intent kimliği uyuşmuyor | TRACE_INTENT_NOT_EXACT |
| Trace schema/scope/action bozuk | TRACE_SCHEMA_INVALID veya TRACE_DECISION_INVALID |
| Trace aç diyor ama gerçek mum kimliği bağımsız doğrulanmamış | TRACE_INTENT_EXACT_CANDLE_UNPROVEN |
| Recovery READY diyor ama 3m/5m toparlanma attestasyonu yok | RECOVERY_NOT_PROVEN |
| Trace kendi mum kimliğine true dese bile bağımsız kaynak kanıtı yok | TRACE_INTENT_EXACT_INDEPENDENT_CANDLE_PROOF_MISSING |

Tüm durumlarda full_order_authority_proven=0.
Stage11 Entry karar akışı exchange candle identity,
Broker flat, Risk Master ve Final Safety / native
exchange stop / ORDER ACK belgelerini sağlamaz.
Bu nedenle Stage19 asla canlı OPEN yetkisi oluşturmaz.

## 24 Kasım mevcut ortamda salt-okunur gerçek denetim

Komut:
PYTHONPATH=. ./venv/bin/python research/trace/long1_stage19_decision_evidence_join_v1.py --audit-readonly --max-rows 2500

Sonuç:
- Stage18 sınırından sonraki yeni trade-intent batch: 0
- Yeni kanonik source exact intent: 0
- LONG1 Entry Decision Trace stream uzunluğu: 0
- Eşleştirilen gerçek yeni Entry karar izi: 0
- Bilinen 103 eski MODEL olayına otomatik OPEN atfı: 0
- Redis XADD/SET/DEL yazıları: 0
- Binance API ve gerçek ORDER: 0
- Mevcut forward cursor ilerletilmedi, daemon/collector açılmadı.

Bu 0, yeni bot çalışmadığı dönemde beklenen sonuçtur.
Geçmişte hiç sinyal olmadığı veya eski işlemlerin
açılmadığı anlamına GELMEZ.

## Test kapsamı

- Test fixture: gerçek Stage6 + Stage7 kaynak üreticileriyle
  kanonik yeni MODEL→Signal→Candidate→Intent.
- Aynı intent_id ile iki Entry kararı gözlenir,
  ancak mum bağımsız doğrulanmadığından OPEN yetkisi yok.
- Trace open bulunması, origin / pending / Risk Master
  chain'in tamamlandığı anlamına gelmez.
- Source parent değişirse kesin kimlik eşleşmesi NO-GO.
- Farklı / bilinmeyen intent_id OPEN'a dönüşmez.
- Yinelenen intent kimliği kaynak kanıtından düşer.
- RECOVERY READY fakat 3m/5m kanıtı eksikse reddedilir.
- CLI varsayılan modunda Redis bağlantısı veya dosya
  yazımı yok. Eksik trace/intent durumları fail closed.
- Stage18 idempotent forward-only ve Stage24 gerçek
  emir engeli regresyonları korunur.

## Sonraki aşama

Yeni real MODEL/Intent event'leri üretildiğinde, Stage19
yalnız as-of kaynak ve Entry karar sınıflandırmasını
hazırlar; kullanıcı canlı servis açmayı yetkilendirmeden
yeni event oluşması beklenmez. Bağımsız kapanmış
3m/5m context candle kimliği, Sniper, Entry,
Contra-Trend ve Risk Master kanıtları daha sonra gerekir.

LONG2-4 / SHORT2-4 çoğaltma yapılmıyor.
Komisyon / Redis / API maliyetini büyütecek
per-tick tracking kurulmadı.

Kaynak:
- research/trace/long1_stage19_decision_evidence_join_v1.py
- research/trace/test_long1_stage19_decision_evidence_join_v1.py
