# LONG1 / SHORT1 Ortak Mimari, Ayar ve Maliyet Denetimi
15 Kasım 2026; VM binance-bot-vm; üretim ayarlarında, servislerde veya emirlerde değişiklik yapılmadı.

## Ortak referans
- Kaynak: research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json.
- Her iki projedeki SHA256: 0c852cc7e5b04204edaafea5fe984555c4621234f69048d2e7a7fe50941305d4.
- 11–15 Kasım: 44 LONG_WANTED, 26 LONG_AVOID, 7 çakışma, 77 ayrık alt aralık.
- Saatler Türkiye UTC+3, başlangıç dahil/bitiş hariç, gece yarısını aşan aralıklar bir kez sayılır.
- SHORT1 ters referans: LONG_WANTED -> SHORT_AVOID, LONG_AVOID -> SHORT_RESEARCH_CANDIDATE, çakışmada iki tarafta da NO_TRADE. Etiketler canlı emir izni değildir. NEAR LONG ile INJ SHORT farklı varlıklar olduğundan SHORT etiketleri ayrı veriyle test edilmelidir.

## Mimari durum
| Katman | LONG1 | SHORT1 | Ortak kontrol durumu |
|---|---|---|---|
| Model ve sinyal | NEARUSDT 3m model ve rolling quantile 0.965; LONG main + dört orkestrasyon işçisi çalışıyor | INJUSDT V5 ve V6 araştırma modelleri çalışıyor; canlı short main/orkestrasyon çalışmıyor | Redis akışları ayrı |
| Market context | NEAR mikro yapı, OI, 3m structure ve combined context | INJ V5/V6 context, V44 order-book hazard, OI collector | Kaynak ve coin ayrılığı var |
| Model gate | Rolling 0.965 aktif, dynamic model gate kapalı | Hard 0.555, soft band 0.545 etkin fakat research/dry | Eşikler ve skor semantiği ortaklaştırılamaz |
| Sniper | 1m %5–60 | 1m %10–42 | Stratejiye özgü |
| Entry Confirmation | Enabled; kalite >=0.52, retrace <=0.50, reject >=0.75 | Aynı kalite/retrace parametreleri ile ayrı SHORT FSM | Paylaşılan FSM değil |
| Contra / PENDING | Guard aktif, ayrı in-memory 30 dk bağlam ve native 1m PENDING | Yeni bağımsız MODEL kanıtı şartı; hard contra override dry-run-only | Yeniden başlatmada stale pending, TTL ve fail-closed testleri gerekli |
| Risk sizing | Equity %48, 3x, tek pozisyon, layers OFF | Equity %46, 3x, tek pozisyon; dry-run | Merkezi üretim atomik rezervasyon henüz yok |
| Central Risk Master | Canlı LONG1 executor'da CentralRiskClient çağrısı tespit edilmedi | CentralRiskClient yalnız self.dry_run dalında | Merkezi servisin authority=SHADOW_ONLY, production_ready=False |
| Final Safety | DRY_RUN=0, ARMED=1, kill=0; native stop aktif; SL %2.99, catastrophe %3.50, confirm30s | DRY_RUN=1, ARMED=0, kill=1; native stop kodu konfigüre, canlı SHORT yok | 8 botluk ortak trade güvenliği henüz tamamlanmadı |
| Exit | Brüt sabit ROI TP %1.25, giveback=0, profit lock/scalp/step/runner OFF | Sabit brüt ROI %1.25, shadow/dry | Kâr hedefi net PnL garantisi değil |
| Telemetry | LONG decision trace shadow aktif | INJ V5/V6, V44 hazard, V30 lifecycle shadow aktif | Birleşik olay/sonuç geribildirim henüz yok |

## P0: Live güvenlik ve SHORT canlıya hazırlık
1. scripts/short1_live_preflight.py READINESS=BLOCKED: 5 bloke eden kontrol. Üretim SHORT model dosyaları beklenen models/ dizininde yok, promotion=REJECT (model_quality_not_candidate, realized_return_nonpositive, pf_not_above_1), soft band live için kapalı isteniyor fakat açık, STRONG 60m kalite %63.6 ve hedef %65, central risk production_authorized=False. SHORT1'i canlıya açmayın.
2. Central Risk servisi aktif olsa da yalnız ENFORCE_DRY/SHADOW profilinde; LONG girişinde zorunlu global atomik portföy rezervasyonu yok. Aynı coin üzerinde 8 motor için tek pozisyon ve global exposure garantisi bugün üretim katmanında yok.
3. SHORT ana modeli ve emir yolu çalışmıyor; bazı servislerin active olması SHORT'un işlem yapabileceği anlamına gelmez.

## P1: Açılış ve model doğrulama
4. LONG mevcut rolling threshold dinamik, MIN 0.491 yalnız sınırdır; LONG_DYNAMIC_MODEL_GATE_ENABLE=0. LONG_CONTEXT_ADAPTIVE_GATE_ENABLE=1 ama yalnız TELEMETRY_ONLY, routing_changed=false. Recovery A/B/C canlıya bağlı değil.
5. LONG Contra Guard tamamlanmış 3m negatif ve iki flow negatif bileşimini bekletir; genel düşüşte tüm LONG'ları engelleyen bağımsız regime gate değildir.
6. LONG 1m native pending ve Contra pending ayrı bellek durumları. SHORT pending freshness kontratı ayrı. Ortak strateji-coin-intent-candle ve TTL, gözlemlenebilir revalidation journal eklenmeli; bunun emir yetkisi olmamalı.
7. SHORT hard contra pending override DRYRUN_ONLY=1. BRIDGE_SHORT_MICRO_GATE_FAIL_OPEN=1 de DRYRUN_ONLY araştırma filtresinde. Bu fail-open kavramı doğrudan canlı Final Safety'ye taşınmamalı.
8. LONG HARD_STOP_ENABLE=0 ve USDT_LOSS_KILL_ENABLE=0, buna karşılık exchange-native ve dinamik stop aktif. Bunların koruma sorumlulukları test edilmeli; canlı native stop asla belirsizliği gidermek amacıyla kapatılmamalı.

## P1: Tutarsız ve eski kontrol dosyaları
9. SHORT scripts/short1_preflight.sh dosyasında güncel .env ile uyuşmayan 5 sabit değer var:
   - MASTER_MIN_TRADE_SCORE: 0.540 bekliyor; güncel 0.555.
   - MASTER_SHORT_SOFT_SCORE_MIN: 0.530 bekliyor; güncel 0.545.
   - ROI_HARD_STOP_PCT: -0.1200 bekliyor; güncel -0.0897.
   - SHORT_DYNAMIC_STOP_CATASTROPHIC_PCT: 0.0600 bekliyor; güncel 0.0350.
   - MASTER_SHORT_MONEY_FLOW_EXHAUSTION_60M: -0.20 bekliyor; güncel -0.15.
   Bu komutu LEGACY olarak işaretleyip güncel tek preflight ile değiştirmek gerekir. Canlı .env değerlerini eski teste uydurmayın.
10. Her iki .env içinde yinelenen anahtar yok. LONG .env içinde eski exit/scalp/layer ayarlarının çoğu devre dışı; bağlı kod/test/research akışını envanterlemeden silinmesin.

## P2: Maliyet, log ve servis sadeleştirme
11. SHORT V5 ve V6 aynı scanner Python kodunu kullanır ama farklı model dizinleri ve farklı Redis streams çıktısı üretir; tam duplicate değildir. Ek test faydası bittiğinde tek model araştırması bırakılabilir.
12. Diğer sürekli servisler: SHORT v30 shadow, V44 WS hazard, V5/V6 signal bus, LONG shadow watcher, OI / micro / structure collectors ve central dry risk. Model promotion gerekçesi netleşmeden araştırma servisleri körlemesine durdurulmamalı.
13. SHORT signals_stream_short1 ve decision_funnel akışlarına 3 Kasım'dan beri yeni canlı/ana model olayları gelmiyor; buna karşılık INJ model shadow V5/V6 11–15 Kasım günlerinde olay yazmaya devam ediyor. Kaynak izlenebilirliği için live-shadow ayrımı zorunlu.
14. Disk %91 dolu, yaklaşık 3.5 GB boş. Redis RAM yaklaşık 603 MB ve maxmemory sınırsız (0). Eski logların güvenli saklama/rotate planı ve stream retention ölçümü gerekli; veri silinmedi, yeni ek API collector başlatılmadı.
15. VM'de Redis proses olarak çalışıyor, systemd user redis.service olarak görünmemesi tek başına kesinti demek değildir.

## İlk SHORT INJ V5/V6 referans eşlemesi (yalnız araştırma)
Aynı insan etiketli saatlerde INJ modellerinin skorları, LONG NEAR ile aynı piyasa yönü anlamına gelmez.
- V5: SHORT_RESEARCH_CANDIDATE etiketinde 798 shadow skoru, kendi olay eşiğini geçen 371; SHORT_AVOID etiketinde 540, geçen 241.
- V6: SHORT_RESEARCH_CANDIDATE 798, geçen 197; SHORT_AVOID 540, geçen 46.
- Çakışan saatlerde 8 model shadow olayı, V5 eşik üstü 7, V6 eşik üstü 6.
Bu rakamlar gerçek Entry Confirmation, emir, stop, komisyon veya sonuç değil; farklı hedef/eşik semantiği nedeniyle doğrudan win-rate karşılaştırması yapılamaz.

## Koordineli gelişim sırası
A. Ortak etiket/araştırma referansı ve okuma testleri: TAMAMLANDI.
B. Tek güncel preflight, config owner matrisi, canlı ve shadow ayrımı: Denetim tamamlandı, üretim kodu değişikliği yapılmadı.
C. Unified Telemetry: strategy_id, symbol, signal_id, model_close_id, gate_reason, pending_reason, risk_reservation, order_id, exit_fill, fees, realised_pnl. Var olan Redis akışlarını kullanarak API maliyetini artırmadan geliştir.
D. Central Risk Master: atomic reserve/release, cross-side same symbol + total exposure, idempotency, stale Redis ve VM restart fail-closed testleri. Önce dry-run.
E. LONG recovery ve SHORT independent bearish model. 11–15 Kasım saatleri DEVELOPMENT; ayrı görülmemiş günlerde fee-aware, slippage-aware gerçek lifecycle replay.
F. Koruma ve risk testleri geçtikten sonra kullanılmayan servis/legacy knobs kontrollü kaldırılır; Git yedek ve rollback zorunlu.

## İlgili dosyalar
- research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json
- research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1_README.md
- research/shared_reference/window_reference_reader_v1.py
- research/shared_reference/test_window_reference_reader_v1.py
- research/shared_reference/audit_long_short_coordination_v1.py
- research/shared_reference/LONG_SHORT_COORDINATION_AUDIT_V1.json

Hiçbir canlı strateji, .env, worker restart, service stop, order send veya Redis risk politikası değiştirilmedi.
