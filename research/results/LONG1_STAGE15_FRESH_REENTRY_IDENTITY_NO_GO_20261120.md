# LONG1 Aşama 15 — PENDING süresi dolunca yeni MODEL + niyet zorunluluğu

Tarih: 20 Kasım 2026, TRT. Yalnız LONG1 NEARUSDT. Fail-closed araştırma; canlı emir NO-GO.

## Aşama 14 bulgusu
11–15 Kasımda 103 ayrı MODEL LONG ve 112 tutulmuş Trade Intent incelendi. Stage13'ün 32 araştırma READY kararından hiçbirinde MODEL→SIGNAL→CANDIDATE→INTENT zinciri tam kimlikle doğrulanmadı. Fiyat toparlanması yeni bir işlem niyeti değildir.

## Mevcut gerçek executor yaşam döngüsü
- TradeExecutor._classify_long_pending_window: confirmation / early PENDING yeni 1m mumda EXPIRED; late PENDING ise en geç ikinci sonraki mumda EXPIRED.
- preserve_pending_origin ilk PENDING attempt ve orijin Intent kimliğini koruyor, yeni recheck Intent'i ayrı taşıyor. Ancak yeni MODEL'in farklı olduğunu tek başına kanıtlamıyor.
- Contra-Trend daha uzun 3m/5m toparlanması arayabilir; süresi dolan native 1m PENDING'i yeniden emir yetkisine dönüştürmez.

## Yeni bağımsız araştırma doğrulayıcısı
Modül: orchestration/trace/long1_fresh_reentry_validator_v1.py.
İşlem fonksiyonlarına bağlanmadı, kendi başına MODEL/Intent oluşturmaz.

Giriş şartları:
1. NEARUSDT ve long; orijinal ve yeni intent_id ile model_evaluation_id farklı ve geçerli olmalı.
2. pending_attempt_id korunmalı; origin Intent ve recheck Intent asıl rolleriyle saklanmalı.
3. Gerçek kaynak exact MODEL→SIGNAL→CANDIDATE→INTENT parent zinciri ve yeni MODEL olayını attest etmeli.
4. Yeni 3m/5m tam mum kapanışları orijinden sonra, gözlem anından önce; gerçek Context dönüş onayı mevcut olmalı.
5. Yeni 1m Sniper ve Entry Confirmation, EXPIRED ilk PENDING, çakışmasız pencere, boş broker pozisyonu ve ortak Risk Master izin kanıtları bulunmalı.
6. Eksik veya çelişkili şart -> NO_GO; tüm şartlar dolu ise sadece RESEARCH_PROVENANCE_COMPLETE; live_order_authorized=false.

Bu doğrulayıcı attestasyon bayraklarını gerçek kaynaklardan kendi kendine getirmez veya kriptografik doğrulamaz. Üretim ORDER yolunun kapısı değildir; gerçek kaynaklara bağlanmadan canlı güvenlik izni kabul edilemez.

## Test
- 8 farklı kimlik veya soy zinciri çelişkisi: NO_GO.
- 15 ayrı kanıt alanının başarısız/eksik olması: NO_GO.
- Gerçek LONG1 native 1m PENDING sınıflandırıcısında 3 expiry senaryosu: EXPIRED.
- Tam örnek attestasyon durumunda bile ORDER izni yok.
- Mevcut Stage14 audit, Stage11 observer, Stage8 PENDING trace ve Stage24 güvenlik testleri birlikte yeniden çalıştırıldı.

## Sonraki aşama
Gelecekte gerçek kaynak tarafından üretilmiş yeni model_evaluation_id, intent_id, tam parent lineage, tamamlanmış mum kimlikleri ve 1m Entry kararlarını forward-only shadow kaydında birleştirerek doğrula. Eski PENDING üzerinden emir emit edilmediğini uçtan uca test et. İşlem eşiği gevşetme, yalnız kârlı görünen geçmiş örnekleri açmaya çalışma.

SHORT1, .env, native stop, LONG1 executor giriş/çıkış kararları, merkezi Risk Master, bot servisleri ve Binance emirleri değiştirilmedi.
