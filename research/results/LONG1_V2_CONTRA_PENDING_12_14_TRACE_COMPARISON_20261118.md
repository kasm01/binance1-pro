# LONG1 12–14 Kasım 2026 — Market Context V2 / Contra-Trend / PENDING karşılaştırması
Tarih: 18 Kasım 2026 (TRT). **Araştırma ve retrospektif izleme; canlı strateji değişikliği yok.**

## Amaç ve kimlik kanıtı
Ortak kullanıcı pencereleri, 89 gerçek MODEL LONG puanlama olayı,
Market Context V2'nin 89 as-of araştırma kararı, bu kararlara ait 89
araştırma PENDING takip satırı ve 89 varsayımsal 60m ilk-fiyat-teması
satırı ayrı kaynaklardan tekil `model_ts_tr` / `close_id` ile
birebir kontrol edildi. **89/89 arşiv olayı birebir eşleşiyor.**
Bu, Stage6/7/8 **gerçek trace_id** eşleşmesi değildir:
eski MODEL→SIGNAL kimlikleri yazılmamış. Üretim Redis'indeki
12–14 Kasım **83/83** CANDIDATE→TOP5→TRADE INTENT→EXECUTION INTENT
kesin kimliği farklı olay popülasyonudur. 89 ile 83 arasında doğrudan
model→intent join **kurulmadı**; geriye dönük skor/zaman üzerinden
doğrulanmış ORDER/FILL iddia edilmedi.

## V2 sonucu (89 gerçek MODEL LONG)
| Kullanıcı referansı | MODEL LONG | VETO_ADVISORY | PENDING |
|---|---:|---:|---:|
| LONG_AVOID | 67 | 18 | 49 |
| LONG_TARGET | 7 | 2 | 5 |
| UNLABELLED | 14 | 2 | 12 |
| CONFLICT_NO_TRADE | 1 | 0 | 1 |
| **Toplam** | **89** | **22** | **67** |

- **READY_CANDIDATE = 0**. Doğrudan zorunlu gate olarak
  uygulanırsa geçmiş örneklemde yeni hiçbir LONG girişine izin vermez.
- 48/89 (≈%53,9) sinyalde as-of signed-flow yok.
  Missing flow hiçbir zaman olumlu flow olarak yorumlanmadı.
- VETO nedenleri `deep_5m_15m_decline` (22). PENDING nedenleri
  `multi_tf_downtrend`, `missing_flow_to_confirm_recovery`,
  `positive_flow_against_bearish_price`,
  `insufficient_confluence`. Kullanıcı etiketleri karara input değil,
  yalnız sonradan konumlandırma için kullanılıyor.
- 89/89 PENDING araştırma satırının hiçbirinde 30 dakika içinde
  önerilen bağımsız MODEL+flow recovery kanıtı bulunmadı.
  Araştırma takipçisi **yeni tamamlanmış 3m/5m mumları ve gerçek 1m
  Entry Confirmation'u bağımsız doğrulamadığı için** bu 0 bulgusundan
  'hiçbir sinyal geri dönmedi' sonucuna varılamaz.

## İlk-temas karşıolgusal kontrolü (gerçek işlem P&L'si DEĞİL)
| V2 kararı | 60m TP_FIRST | 60m SL_FIRST | NEITHER |
|---|---:|---:|---:|
| VETO_ADVISORY (22) | 14 | 0 | 8 |
| PENDING (67) | 49 | 4 | 14 |
| **Toplam** | **63** | **4** | **22** |

Burada fiyat referansı ilk sinyal sonrası kapanmış 1m mumundan alınır,
3x brüt ROI hedefi %1,25 ve fiyat SL ilk teması retrospektif OHLC
kuralına bağlıdır. Stratejinin gerçek Sniper/Entry Confirmation,
native stop, dinamik kilit, emir gerçekleşmesi, kayma ve funding'i
yansıtılmaz. Ücret varsayımı %0,08 notional gidiş-dönüş örneğidir;
Binance hesap gerçekleşmesi veya net kârlılık ölçümü değildir.
Market V2 VETO, bu örneklemde **0/4 varsayımsal SL-first** yakalarken
**14 varsayımsal TP-first** olayını dışlamış oluyor. Bu tek başına
yeni gate'in risk/ödül performansını iyileştirdiğini göstermez.
LONG_AVOID etiketine sahip 67 model olayında da 42 TP_FIRST,
4 SL_FIRST, 21 NEITHER vardır; LONG_AVOID kullanıcı araştırma
penceresidir, otomatik zarar veya yasak etiketi değildir.

## Operasyonel Contra-Trend / gerçek 1m karar kayıtları
Ortak referansın `LONG1_SHARED_REFERENCE_STAGE_COUNTS_20261111_15_V1.json`
özeti, 12–14 Kasım için şunları bildiriyor (1m tekrarları içerir,
89 bağımsız MODEL skoruyla aynı payda DEĞİLDİR):
- LONG_AVOID: 4 `entry_open_decisions`, 25 BLOCK, 28 PENDING,
  29 `pending_cleared`; `contra_pending=0`.
- LONG_TARGET: 0 OPEN, 0 BLOCK, 4 PENDING, 2 `pending_cleared`;
  `contra_pending=0`.
- UNLABELLED: 4 OPEN, 3 BLOCK, 7 PENDING, 8 `pending_cleared`;
  `contra_pending=0`.
- CONFLICT: 0 OPEN/PENDING/BLOCK; `contra_pending=0`.
- TOPLAM 8 OPEN, 28 BLOCK, 39 PENDING, 39 `pending_cleared`,
  **0 contra_pending**. Bunlar karar/log olayıdır; 8 pozisyon açıldığı,
  39 benzersiz PENDING denemesi ya da 39 kârlı kurtarma olduğunu
  göstermez. `pending_cleared` READY / executed demek DEĞİLDİR.

Canlı Contra-Trend Guard, Market Context V2'dan **ayrı** bir
dar R1+flow ve yeni intent/yeni 3m/5m recovery mantığı kullanır ve
yalnız upstream READY sonrasında çağrılabilir. Kaynakta üç gün
0 `contra_pending` görünmesi true/false guard kararlarının tam
paydasını sağlamaz; guard kalitesi ve kaçırdığı kâr burada ölçülemez.
14–15 Kasım ayrı log denetiminde 15 Kasım 04:36'da guard
gerçek upstream READY girişini PENDING yapmıştır; bu olay
12–14 Kasım testinin dışındadır, ayrık kanıttır.

## Dört hızlı geri dönüşün yeniden eşleştirilmesi
| TR zaman | Kullanıcı etiketi | V2 | Neden | 60m ilk temas | Eski 1m bağlantı |
|---|---|---|---|---|---|
| 12 Kas 01:36:16 | LONG_AVOID | PENDING | multi_tf_downtrend | SL_FIRST | MODEL_ONLY |
| 14 Kas 17:06:14 | LONG_AVOID | VETO | deep_5m_15m_decline | NEITHER | MODEL_ONLY |
| 14 Kas 19:06:12 | LONG_AVOID | PENDING | multi_tf_downtrend | NEITHER | HEURISTIC_SCORE_TIME, 2 PENDING log |
| 14 Kas 23:57:09 | LONG_AVOID | PENDING | positive_flow_against_bearish_price | SL_FIRST | MODEL_ONLY |

12 Kas 01:36 signed-flow eksik; 14 Kas 23:57 flow pozitif olsa
da orta vadeli fiyat bağlamı negatif; LONG için flow tek başına
READY izni oluşturmamalı. 14 Kas 19:06 ile ilişkilendirilen iki
PENDING log kesin MODEL→EXECUTION trace olmadığı için işlemin
gerçekleştiğini ispatlamaz.

## Karar / sonraki güvenilir deney
1. **Market Context V2'yı canlı OPEN gate'e yükseltme: NO-GO.**
   Şu an saf shadow diagnostik; aşırı kısıtlayıcı (0 READY), akış
   kapsamı yetersiz ve varsayımsal SL-first ayırımı başarısız.
2. **Mevcut Contra-Trend, Native Stop ve 1m Entry Confirmation'ı
   koru.** Sadece 0 contra_pending loguyla iyileştirme veya
   gevşetme çıkarımı yapılmasın.
3. PENDING araştırmasında origin_intent_id / current_intent_id /
   pending_attempt_id, source completed 3m/5m/15m timestamps, flow
   kaynağı/güncelliği, **gerçek 1m entry**, önce/sonra bağımsız
   3m mum kimlikleri ve stop/exit sonuçlarını tek trace'de ölç.
4. Basit VETO vs PENDING yerine rejim bazlı iki shadow adayı
   karşılaştırılabilir: (a) kontrollü mean-reversion scalp,
   (b) confirmed trend recovery. Bu veriyle eşik seçilmesin;
   farklı tarihlerde prospective shadow + net ücretli gerçek
   yürütme yolu replayer'ı gereklidir.
5. Missing-flow UNKNOWN olarak kalmalı; bunu READY'ye çevirmek veya
   tüm negatif 5m/15m hareketleri otomatik reddetmek doğrulanmış
   iyileştirme değildir.
6. Long1 live girişleri ortak Risk Master Stage24 VETO ile kapalı,
   hiçbir bot servisi başlatılmadı, canlı parametre/depolama
   veya gerçek Binance emri değiştirilmedi.

## Dosyalar ve tekrarlanabilirlik
- `research/trace/compare_long1_market_contra_pending_20261112_14_v1.py`
- `research/results/LONG1_V2_CONTRA_PENDING_12_14_TRACE_COMPARISON_20261118.json`
- Daha eski Stage6/7/8 trace doğrulama raporları.
Çalıştır:
`PYTHONPATH=. ./venv/bin/python research/trace/compare_long1_market_contra_pending_20261112_14_v1.py`
