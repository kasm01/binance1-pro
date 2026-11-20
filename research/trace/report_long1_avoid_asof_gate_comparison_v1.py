"""Render sourced 26-window comparison with explanatory no-order caveats."""
from pathlib import Path
from collections import Counter
import json
R=Path(__file__).resolve().parents[2];OUT=R/'research/results'
x=json.loads((OUT/'LONG1_AVOID_ASOF_GATE_COMPARISON_20261120.json').read_text())
a=x['green_close_arm_022_groups']['LONG_AVOID']
w=x['green_close_arm_022_groups']['LONG_WANTED']
model=x['actual_model_avoid_future_5m_by_stage']
seq=['body_research_min_0p22','retrace_research_max_0p35','flow1_research_min_0p03',
     'flow3_research_positive','r3_research_positive','flow3_research_delta_0p08',
     'r3_research_delta_0p10pp','r5_closed_proxy_positive']
fails=Counter()
for z in x['green_close_arm_022_rows']:
 if z['groups']!='LONG_AVOID':continue
 for k in seq:
  if not z['gates'][k]:
   fails[k]+=1;break
hard=a['all_strict_1m_and_5m_proxy_positive']
assert sum(fails.values())+hard==a['count']==581
lines=[
 '# LONG1 — LONG_AVOID saatlerinde kısa yükseliş / filtre kaçırma incelemesi',
 '',
 '20 Kasım 2026. 11–15 Kasım, Europe/Istanbul. Binance NEARUSDT 1m',
 'kapalı fiyat/flow mumları, önceki Stage13 MODEL kayıtları.',
 'NO LIVE ORDER. Üretim servisleri kapalı. Bu simülasyon, gerçek',
 'Sniper/Entry/Whale veya kaynak kimliği doğrulanmış işlem değildir.',
 '',
 '## 1. Gerçek LONG1 eşikleri ve tarihsel MODEL kararları',
 '',
 'VM whitelist üretim ayarı: rolling model gate quantile 0,965;',
 'min 0,491, max 0,525; Entry body >=0,15, max retrace <=0,50,',
 'Entry quality >=0,52; Sniper candle progress 0,05–0,60;',
 'Contra Guard enabled; en fazla 1 pozisyon; scale-in disabled.',
 'Bunlar çalışan servislerden alınmış yeni anlık sinyal değil,',
 'VM içindeki mevcut konfigürasyon dosyasının salt-okunur kopyasıdır.',
 '',
 'Önceki tam-kapalı 1m araştırma filtreleri bundan farklıdır:',
 'body>=0,22, retrace<=0,35, flow1>=0,03, 3m flow pozitif,',
 '3m fiyat return pozitif, 3m flow delta>=0,08 ve',
 '3m fiyat delta>=0,10 yüzde puan. Ayrıca destek için',
 'son 5 kapanmış 1m üzerinden 5m return >0 araştırma',
 'filtresi eklendi: bu, borsanın gerçek LIVE 5m context gate',
 'fonksiyonunun yeniden çalıştırıldığı anlamına gelmez.',
 '',
 'LONG_AVOID aralıklarına düşen 70 arşiv MODEL olayı:',
 '',
 '| Stage13 sonucu | Model olayları | Sonraki 5m brüt +0,22 MFE gördü | +0,35 MFE gördü | +0,80 MFE gördü | 5m sonu ücret sonrası pozitif |',
 '|---|---:|---:|---:|---:|---:|'
]
for key in ('MODEL_GATE','CONTRA_WAIT_30M','ENTRY_PENDING_EXPIRED','RESEARCH_READY_NO_REAL_INTENT'):
 z=model[key]
 lines.append(f"| {key} | {z['events']} | {z['5m_mfe_arm022']} | {z['5m_mfe_arm035']} | {z['5m_mfe_arm080']} | {z['5m_end_net_positive_after_fee']} |")
lines+=['',
 'Görüldüğü gibi Contra/PENDING tarafından reddedilen olaylarda',
 'kısa yükselişler görülebiliyor. Ancak MFE en yüksek gelecek',
 'fiyatı olduğu için bu tablo kârlı giriş/çıkış olacağını kanıtlamaz.',
 'Bazı olaylar aynı fiyat yükselişine denk gelebilir.',
 '',
 '## 2. MODEL sinyalinden BAĞIMSIZ tüm dakika adayları',
 '',
 '1m CLOSE yeşil ve OPEN→CLOSE 3x ROI en az +%0,22 ise,',
 'yalnızca SONRAKİ 1m OPEN için araştırma adayı tanımlandı.',
 'Gelecekteki HIGH veya LOW ile aday seçilmedi.',
 'Aynı anda LONG_WANTED ve LONG_AVOID etiketi olan 13',
 'çakışan mum araştırma giriş adayı olarak dışlandı.',
 '',
 '| Ölçüm | LONG_AVOID | LONG_WANTED |',
 '|---|---:|---:|',
 f"| Kapanmış yeşil +%0,22 aday mum | {a['count']} | {w['count']} |",
 f"| 1m canlı body>=0,15 ve retrace<=0,50 basit görünüm (Entry quality, Sniper hariç) | {a['all_live_shape_body_retrace']} | {w['all_live_shape_body_retrace']} |",
 f"| Katı 1m araştırma filtresi tam geçiş | {a['all_strict_1m_filters_proxy']} | {w['all_strict_1m_filters_proxy']} |",
 f"| Katı 1m + son 5 kapalı 1m return pozitif | {hard} | {w['all_strict_1m_and_5m_proxy_positive']} |",
 f"| Sonraki 5m fiyatın brüt +%0,22 ROI tepesini görmesi | {a['gross_0p22_touch']} | {w['gross_0p22_touch']} |",
 f"| Sonraki 5m CLOSE ücret sonrası net artı | {a['net_positive_end_after_fee']} | {w['net_positive_end_after_fee']} |",
 '',
 'Kapanmış mumla seçilen %0,22 adaylar ilk hareketin',
 'artık gerçekleştiği noktalardır; sonraki 5 dakika yukarı',
 'hareketin süreceğini garanti etmez. Aday mumun kendi',
 'OPEN→HIGH farkı gelecekteki işlem kârı sayılamaz.',
 '',
 '## 3. Hangi katmanda eleniyor? (Aşamalı İLK başarısız eşik)',
 '',
 '| Kontrol sırası | İlk kez elenen aday (LONG_AVOID) |'
 ,'|---|---:|']
for key in seq:
 lines.append(f'| {key} | {fails[key]} |')
lines+= [f'| **Tüm kontrolleri geçen** | **{hard}** |',
 '',
 'Bu tablo eşikleri sırayla uygular. Her eşik bağımsız',
 'bir neden değildir: farklı sıralamayla ilk elenme',
 'dağılımı değişir. Tam canlı Market Context, Whale,',
 'Sniper ve gerçek rolling MODEL skor bilgisi bu',
 'yapay yeni adaylarda mevcut değildir.',
 '',
 '## 4. Gerçekçi aday sayısını daraltma ve 5m hareket',
 '',
 f"- {hard} kapalı-1m+5m as-of tarama geçişinden",
 f"- mevcut gerçek broker LONG zamanlarını dışlayınca",
 f"  {x['strict_avoid_candidates_before_dedupe']} adet kaldı.",
 '- Aynı coin için tek pozisyon, en az 5m aralıkla',
 f"  sırayla seçilince {x['strict_avoid_nonoverlap_5m_candidates']} araştırma adayı kaldı.",
 'Bu seçim her adayın gelecekte nasıl sonuçlanacağını',
 'kullanmıyor, yalnız kronolojik olarak ilerliyor.',
 f"- Sonraki 5m içinde brüt +%0,22 ROI yüksek fiyatı görülen: {x['strict_avoid_nonoverlap_5m_measures']['5m_mfe_022_seen']}.",
 f"- Brüt +%0,35 görülen: {x['strict_avoid_nonoverlap_5m_measures']['5m_mfe_035_seen']}.",
 f"- Brüt +%0,80 görülen: {x['strict_avoid_nonoverlap_5m_measures']['5m_mfe_080_seen']}.",
 f"- 5m sonunda %0,24 ROI komisyon sonrası net pozitif: {x['strict_avoid_nonoverlap_5m_measures']['5m_end_net_positive_after_fee']}.",
 f"- 5m sonundaki farazi tüm çıkışların toplam ROI puanı:",
 f"  {x['strict_avoid_nonoverlap_5m_measures']['5m_end_net_roi_pp_sum_assuming_exit_at_fifth_close']}.",
 'Bu toplam beklenen strateji performansı değildir: stop',
 'yönetimi, gerçek TP, giriş emirleri, minQty, slippage',
 've interval geçişlerindeki başka pozisyonlar test edilmedi.',
 'Stop/TP high ve low sırası 1m OHLC ile kesin bilinmiyor.',
 'Mevcut 2.000 USDT hesabın dört bota dağıtılmasını',
 'pozisyon açma kanıtı olarak yorumlamayın.',
 '',
 '## 5. 26 LONG_AVOID aralığı için saat bazında gözlem',
 '',
 '| Başlangıç TRT | Bitiş TRT | Kapalı yeşil +%0,22 | Katı 1m+5m geçti | Sonraki 5m HIGH +%0,22 | Sonraki 5m CLOSE ücret sonrası pozitif | Aynı dakikada MODEL |',
 '|---|---|---:|---:|---:|---:|---:|']
for z in x['avoid_windows']:
 lines.append(f"| {z['start_tr'][5:16]} | {z['end_tr'][5:16]} | {z['count']} | {z['all_strict_1m_and_5m_proxy_positive']} | {z['gross_0p22_touch']} | {z['net_positive_end_after_fee']} | {z['actual_model_same_minute']} |")
lines+=['',
 '## 6. Kanıt sınırı ve önerilen doğrulama',
 '',
 '- Sinyal yok görünen dakikalarda yeni MODEL hesaplanmadığı',
 '  ispatlanmaz; sadece 103 arşivlenmiş MODEL LONG olayı',
 '  arasında aynı dakika kaydı yok.',
 '- LONG_AVOID tarihleri geriye dönük etiketler; canlı',
 '  trade whitelist/veto işlevi kazandırılmamalı.',
 '- Katı filtreyi düşürmeden önce ters trend + pozitif',
 '  kapanmış 3m/5m + yeni gerçek MODEL/Intent + taze',
 '  1m Sniper/Entry koşulunu ölçen forward-only shadow',
 '  gerekir. Merkezi Risk Master/global coin lock korunur.',
 '- Özellikle kısa tepki hareketlerinin 5m bitişte sönmesi',
 '  nedeniyle yalnız +%0,22 ARM görme kuralı bir strateji',
 '  avantajı olarak kabul edilmemeli: ilk floor -%0,12',
 '  ROI (%0,10 geri çekilme + %0,24 fee).',
 '- Bir sonraki test: gerçek trade/aggTrade tick ile',
 '  girişten SONRA peak/drawdown sırası, fill ve',
 '  6 basamaklı kısmi TP maliyet hassasiyeti.',
 '- Servisler kapalı, real orders/Redis write=0.',
 '',
 'Kaynaklar:',
 '- research/trace/audit_long1_avoid_context_entry_bottlenecks_v1.py',
 '- research/trace/test_long1_avoid_context_entry_bottlenecks_v1.py',
 '- LONG1_AVOID_ASOF_GATE_COMPARISON_20261120.json',
 '']
(OUT/'LONG1_AVOID_ASOF_GATE_COMPARISON_REPORT_20261120.md').write_text('\n'.join(lines))
print(json.dumps({'status':'PASS','avoidable_group_closed_arm022':a['count'],
 'strict_asof_plus5m':hard,'consecutive_first_fail':dict(fails),
 'long_avoid_windows':len(x['avoid_windows']),
 'no_trade_authorization':True},sort_keys=True))
