# LONG1 Aşama21 — As-of 3m/5m/15m/60m para akışı ve PENDING kanıtı

24 Kasım 2026. NEARUSDT / LONG1. Yalnız research, üretim NO-GO.
Önceki Stage13'te gözlenen 103 gerçek MODEL olayının
32 RESEARCH_READY_NO_REAL_INTENT araştırma girişini
Stage20 kapalı 3m/5m mumlarıyla yeniden denetledik.

## Yeni as-of para akışı

Kaynak: 11–15 Kasım arşivindeki tam kapanmış 8640 Binance
USD-M 1m mumunun quote taker buy/sell hacmi. Karar anından
SONRAKİ barlar kullanılmaz; 3,5,15,60 dakikalık
geriye dönük taker net ratio hesaplanır.
Fiyat 3m ve 5m tam kapanmış mumun OPEN/CLOSE
yönüyle kontrol edilir.

Araştırma tanı kuralı:
1. Eksik veya gelecekteki kapanış: NO-GO.
2. 3m/5m tamamlanmış mum yükselişi yok: PRICE_REVERSAL_NOT_SUPPORTED.
3. 3m veya 5m signed taker flow negatif: 3M_5M_BUYER_FLOW_WEAK.
4. 15m veya 60m signed flow negatif: 15M_60M_CONTEXT_NEGATIVE.
5. Ancak hepsi olumluysa: ARCHIVE_RESEARCH_SUPPORT_ONLY.

Bu bir canlı filtre veya doğrulanmış Market Context
READY değildir. Asıl 3m/5m yapı, whale, canlı
taker akışı, model-score, Sniper ve canlı 1m partial
Entry Confirmation tekrar çalıştırılmadı.

## Sonuçlar: 32 araştırma-READY olayı

| As-of araştırma tanısı | Olay |
|---|---:|
| 3m/5m fiyat mumları yükseliş yönünde değil | 12 |
| 3m/5m yükseliş olsa da 15m veya 60m flow negatif | 20 |
| Bütün proxy kontroller olumlu | 0 |
| TOPLAM | 32 |

20 negatif uzun dönem flow tanısı, daha önce
Stage20'de yeşil 3m/5m mumlarıyla olumlu görünen
aynı 20 olayı açıklayabilir. Ancak tüm 103 gerçek
MODEL olayı üzerinde üretim filtresinin performansını
veya WANTED kaybını kanıtlamaz. Bu eşikler
geçmiş araştırma sonrası seçilmiştir; overfit
ve örnek bağımlılığı riski yüksektir.

Stage20 20/8/4 dağılımı ile Stage21 20/12
dağılımı çelişmez: Aşama21 yalnız fiyatın yükseliş
şartına bakarken Stage20'de dört olayın asıl
eksikliği MODEL sonrasında kapanmış taze 3m+5m
ikilisinin bulunmamasıydı. Stage21'de de bu dört
olaya PENDING tam-kaynak kanıtı verilmiyor.

## Tam PENDING provenance, fail-closed

Stage15 saf verify_fresh_reentry sözleşmesiyle
her araştırma olayı için kritik kanıtlar kontrol edildi.
Bu replay'de:
- gerçek yeni MODEL/Signal/Candidate/Intent parent: 0/32
- native 3m/5m source candle ve Contra recovery: 0/32
- gerçek yeni 1m Sniper ve Entry READY: 0/32
- gerçek expired PENDING attempt / origin identity: 0/32
- Risk Master broker-flat / shared risk permission: 0/32
- gerçek ORDER authority: 0/32

Stage21'de kimlikler yalnız test fixture sentetiğidir.
Kaynak zinciri veya canlı karar olduğuna dair
pozitif attestasyon üretilmedi, bunlar kesinlikle
gerçek yeni model veya yeni Intent değildir.

## Güvenlik ve testler

- 1m karar zamanından sonraki taker volume kullanılmaz;
- 3,5,15,60m window zamansal aralıkları denetlendi;
- eksik 1m source NO-GO;
- 15m veya 60m negatif flow research uyumunu engeller;
- 3m/5m ters fiyat research uyumunu engeller;
- future timestamp NO-GO;
- sentetik olumlu 3m/5m bile gerçek Intent/Risk
  Master izinlerini doğrulamadan emir üretemez;
- Aşama19 source-chain ve Stage24 merkezi Risk
  Master güvenlik regresyonları PASS.

Üretimde yeni gate veya Redis key/stream yazımı
yok. Yeni servis/timer/collector yok. Binance REST
API sıfır. Veri maliyeti sıfır. Canlı pozisyon/TP/SL
değişmedi. SHORT1 ve LONG2–4/SHORT2–4 etkilenmedi.

## Sıradaki çalışma

Bu negatif 15m/60m bağlamı araştırma hipotezi olarak
tutulmalı, DOĞRUDAN canlı sert veto yapılmamalı.
Önce gerçek canonical source → Market Context
as-of origin → pending store/recheck → canlı Entry
→ Risk Master kararını forward-only gözlemde
eşleştirmek gerekir. Yeni, dokunulmamış günlerde
kayıp WANTED fırsatlar ve kurtarılan AVOID riskleri
birlikte test edilmelidir.

Kod:
research/trace/long1_stage21_context_flow_pending_evidence_v1.py
research/trace/test_long1_stage21_context_flow_pending_evidence_v1.py
research/results/LONG1_STAGE21_FLOW_CONTEXT_PENDING_PROOF_20261124.json
