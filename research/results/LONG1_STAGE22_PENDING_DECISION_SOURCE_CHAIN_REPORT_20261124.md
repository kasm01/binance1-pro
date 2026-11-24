# LONG1 Aşama 22 — PENDING origin → fresh Intent → Entry trace denetimi

24 Kasım 2026, NEARUSDT LONG1. Varsayılan kapalı,
salt-okunur, geriye dönük emir yetkisi vermeyen araştırma.

## Amaç

Önceki Stage17/18 denetimlerinde 285 eski Intent'in
0'ı tam kaynak zincirine bağlanabildi. Stage19, yalnız
yeni Intent için Stage6/7 parent kimliği ve mevcut Entry
karar izini eşleştirdi. Stage20/21 kapanmış fiyat/akış
proxy testleri 32 araştırma READY sinyalinin gerçek
OPEN olduğunu kanıtlamadı.

Stage22, kaynak kimlikleri EKSİKSİZ olduğunda bile,
PENDING origin, yeni recheck Intent ve Contra-Trend
kararlarının doğru attempt ve sırada geldiğini
kontrol eden saf denetimdir. Sadece mevcut Redis
akışlarını okur, üretim kararlarını değiştirmez.

## Kaynaklar

- Stage18 ileriye dönük Trade Intent cursor:
  research/local_market_data/long1_stage18/forward_cursor.json
- Model→Signal→Candidate→Intent parent kimliği:
  Stage19 resolve_new_exact_intents; aynı gerçek Stage6/7
  kaynak hesaplarını yeniden türetir
- Executor Stage11 karar gözlemi:
  telemetry:long1:entry_decision_trace:v1
- Source kimliği için zaman/skor/fiyat yakınlığı
  KESİNLİKLE kullanılmaz.

## Denetim kuralları

| Hata / eksik kanıt | Fail-closed kararı |
|---|---|
| PENDING origin hiç yok veya yinelenmiş | ORIGIN_MISSING_OR_AMBIGUOUS |
| Yeni recheck kararı yok | RECHECK_MISSING |
| Origin eski kayıt, kanonik kaynak kimliği yok | ORIGIN_INTENT_NOT_EXACT |
| Yeni Intent'in parent kimliği yok | RECHECK_INTENT_NOT_EXACT |
| Köken Intent değiştirilmiş | PENDING_ORIGIN_CHANGED |
| Recheck Intent yanlış yazılmış | RECHECK_INTENT_FIELD_MISMATCH |
| Origin ve yeni Intent aynı | OLD_INTENT_REUSED |
| Yeniden kontrol origin timestamp'ten sonra değil | NOT_FRESH_AFTER_ORIGIN |
| Yeniden kontrol sayacı bozuk veya yinelenmiş | INVALID_RECHECK_COUNT / DUPLICATE_RECHECK_COUNT |
| Kapanmış exchange candle kaynak kimliği yok | NATIVE_CANDLE_IDENTITY_NOT_PROVEN |
| Recovery READY ama gerçek Contra doğrulaması yok | CONTRA_RECOVERY_EVIDENCE_NOT_PROVEN |
| Risk Master / Broker flat / Final Safety yok | RISK_MASTER_FINAL_SAFETY_NOT_PROVEN |

Bir PENDING karar zincirinin ID dizisi uyumlu olsa
bile Stage11 shadow kaydı bağımsız Binance 3m/5m
candle kimliği, order-book, native stop,
shared Risk Master, final safety veya order-fill
kanıtı sağlamıyor. Bu nedenle asla ORDER çıkışı yok.

## Gerçek mevcut durum

Salt-okunur son denetim:
- Yeni Intent: 0
- Stage11 Entry karar trace kayıtları: 0
- Görülen PENDING attempt: 0
- Doğrulanmış gerçek yeniden giriş: 0
- Gerçek Binance emir: 0
- Redis üretim state yazımı: 0
- Cursor ilerletme: yok; servis başlatma: yok

Bu 0, canlı servislerin kapalı olduğu dönem içindir.
Geçmiş 103 MODEL olayının olmadığını iddia etmez.
Eski 285 Intent Stage18 cursor öncesinde olduğundan
süreçte tam kanıt üretmiş gibi gösterilmiyor.

## Offline testler

Gerçek Stage6/7 fixture + Stage11 karar payload
üzerinde (sentetik eventler):
- Köken ve yeni Intent kimlik kontrolü
- Recheck attempt değişimi ve orijinal Intent'i
  yeni Intent yerine tekrar kullanma hataları
- Origin/recheck saat sıralaması, sayaç uyumu
- Şema bozulması / yetki alanı manipülasyonu
- Tam kaynak zinciri olsa bile yalnız shadow
  provenance; gerçek emir yetkisi yok
- Stage18 ve Stage19 önceki regresyonları PASS
- Stage24 Risk Master order/veto regresyonu PASS

## Sınır ve sonraki aşama

Stage11 gözlemcisi varsayılan kapalı ve Redis trace
şu anda 0. Gerçek yeni olay oluşmadan bu modül
girişin kâr/zarar nedenini doğrulayamaz.

İleriye dönük gözlemde yeni source chain için
exact Intent ve PENDING attempt identity,
independently sourced completed 3m/5m candle
kimlikleri, 15m/60m flow, actual partial-1m
Sniper/Entry ve Risk Master izinlerini birleştirmek
gerekecek. Üretim kodu açılmadan, STOP/TP veya
giriş eşikleri değiştirilmeden araştırma sürmeli.

Dosyalar:
research/trace/long1_stage22_pending_decision_chain_audit_v1.py
research/trace/test_long1_stage22_pending_decision_chain_audit_v1.py
