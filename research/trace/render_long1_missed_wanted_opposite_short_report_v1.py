"""Human report and CSV; only existing local JSON files, no API or writes to prod."""
from __future__ import annotations
import json,csv
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[2]/'research/results'
name='LONG1_MISSED_11_AND_OPPOSITE_SHORT_4_PRICE_PATH_20261118'
data=json.loads((ROOT/(name+'.json')).read_text())
miss=data['missed_model_events'];short=data['opposite_short_from_four_long_avoid_entries']
assert len(miss)==11 and len(short)==4

def csvrows(outname, rows,fields):
 with (ROOT/(outname+'.csv')).open('w',newline='',encoding='utf8') as out:
  w=csv.DictWriter(out,fieldnames=fields,extrasaction='ignore',lineterminator='\n')
  w.writeheader();w.writerows(rows)
recs=[]
for x in miss:
 y=x['upstream_historical_diagnostic']
 recs.append({'time_tr':x['timestamp_tr'],
   'model_score':x['score'],'rolling_threshold':x['rolling_threshold'],
   'rolling_gate_passed':x['score_above_rolling'],
   'old_60m_hypothetical_tp_first':x['hypothetical_60m_first_hit'],
   'old_hypothetical_first_tp_time_tr':x['hypothetical_60m_first_tp_time_tr'],
   'market_context_v2':x['context_v2'],'v2_reason':x['context_v2_reason'],
   'asof_flow_present':x['flow_asof_available'],
   'broker_verified_long_already_open':y['broker_verified_long_already_open_at_model_event'],
   'nearby_trade_intents_heuristic':x['nearby_trade_intents_not_exact_trace'],
   'nearby_top5_same_rounded_score_heuristic':y['legacy_top5_same_score_within_180s_count'],
   'all_nearby_top5_against_long_at_current_whale_threshold':
      y['matched_top5_whale_contra_meeting_current_045_threshold'],
   'exact_model_to_intent_trace':False})
csvrows('LONG1_MISSED_LONG_TARGET_11_MODEL_EVENTS_20261118',recs,list(recs[0]))
out=[]
for x in short:
 v=x['windows']
 q=v['60m'];held=v['original_long_hold']
 out.append({'open_tr':x['original_long_open_tr'],
  'original_long_close_tr':x['original_long_close_tr'],
  'hypothetical_short_entry':x['same_price_hypothetical_short_entry'],
  'short_at_real_long_close_roi_pct':x['hypothetical_short_roi_at_long_close_pct'],
  'short_first_60m_mfe_roi_pct':q['short_mfe_roi_pct'],
  'short_first_60m_mfe_time_tr':q['short_mfe_time_tr'],
  'short_first_60m_mfe_low_price':q['short_mfe_low_price'],
  'short_first_60m_mae_roi_pct':q['short_mae_roi_pct'],
  'short_first_60m_final_bar_roi_pct':q['short_roi_final_full_bar_close_pct'],
  'short_first_60m_max_reversal_from_best_roi_points':
     q['max_reversal_after_best_roi_points'],
  'short_first_120m_mfe_roi_pct':v['120m']['short_mfe_roi_pct'],
  'short_first_240m_mfe_roi_pct':v['240m']['short_mfe_roi_pct'],
  'short_original_long_hold_mfe_pct':held['short_mfe_roi_pct'],
  'short_original_long_hold_mfe_time_tr':held['short_mfe_time_tr'],
  'short_first_60m_touch_0p6_roi':'0.6' in q['first_arm_touch_time_tr'],
  'short_first_60m_touch_0p95_roi':'0.95' in q['first_arm_touch_time_tr'],
  'short_first_60m_touch_1p2_roi':'1.2' in q['first_arm_touch_time_tr'],
  'short_first_60m_touch_2p5_roi':'2.5' in q['first_arm_touch_time_tr']})
csvrows('LONG1_OPPOSITE_SHORT_4_REFERENCE_PATHS_20261118',out,list(out[0]))
lines=[
'# LONG1 — kaçırılan LONG fırsatları ve 4 karşı yön SHORT senaryosu',
'',
'## Kapsam',
'',
'11–15 Kasım 2026 kullanıcının ortak çalışma referansında LONG açılmalı',
'44 pencere ve LONG açılmamalı 26 pencere bulunuyor. Bu rapor yalnız',
'geçmiş gözlem ve NEARUSDT karşıolgusal fiyat yoludur. Gerçek SHORT1',
'INJUSDT stratejisini, SHORT1 model skorunu ya da canlı SHORT emrini',
'temsil etmez. Kullanıcı pencereleri canlı saat yasakları olarak kullanılmaz.',
'',
'## Açılmalı LONG neden kaçtı?',
'',
'- 44 açılmalı pencerede 10 farklı pencerede 11 bağımsız MODEL LONG',
'  olayı vardı. 11/11 rolling model eşiğinin üstündeydi.',
'- 9 Trade Intent yalnız üç açılmalı pencerede oluştu;',
'  bunların hiçbiri borsada pozisyon açmadı.',
'- 9 niyet: yönlü 1m mum eksikliği 4, Sniper geçmiş 2, Sniper erken 1,',
'  güçlü 1m ters dönüş 1, PENDING recheck wait 1.',
'- 11 model sinyali eski bağımsız 60m OHLC araştırmasında 11/11 TP_FIRST;',
'  bunlar sanal 3x LONG girişleri için ilk temas sonuçlarıdır,',
'  gerçek 1m giriş sinyali, fill, stop ve ücretli net kâr değildir.',
'- 11 olaydan 2 tanesinde Binance tarafından doğrulanmış daha önce',
'  açılmış bir LONG pozisyon zaten aktifti. Ayrı yeni giriş yapmamak',
'  tek pozisyon koordinasyonu açısından güvenli davranıştır.',
'- Dört olayda aynı yuvarlanmış skora ve 180 saniyelik ileri pencereye',
'  sahip TOP5 kayıtlarının tümü SHORT yönlü whale ve %0,45 üzeri',
'  whale skoruyla uyumludur. Bu mevcut Master whale veto şartıyla',
'  **UYUMLU**, ancak eski close_id TOP5 içine aktarılmadığı için',
'  MODEL bazında kesin sebep değildir.',
'- Diğer yeni MODEL_LONG→TOP5→intent bağlantıları eski kayıtlardan',
'  kesin kurulamaz. Üretim Stage8 trace meta ileriye dönük kuruldu;',
'  bu eski olaylara trace_id uydurulmadı.',
'',
'| MODEL sinyali (TR) | Rolling eşiği geçti | V2 shadow | TOP5 as-of iz | Niyet / gözlem | Sanal 60m |',
'|---|---|---|---|---|---|',
]
for x in miss:
 diag=x['upstream_historical_diagnostic']
 if diag['broker_verified_long_already_open_at_model_event']:why='Zaten LONG açık'
 elif diag['matched_top5_whale_contra_meeting_current_045_threshold'] is True:why='Whale kontra (olasılık)'
 elif x['nearby_trade_intents_not_exact_trace']:why=f"{x['nearby_trade_intents_not_exact_trace']} yakında niyet"
 else:why='Kesin upstream neden yok'
 lines.append(f"| {x['timestamp_tr'][5:16].replace('T',' ')} | Evet | {x['context_v2']} | {diag['legacy_top5_same_score_within_180s_count']} tahmini | {why} | {x['hypothetical_60m_first_hit']} |")
lines.extend([
'',
'Bu tablo içinde eski MODEL/TOP5 ilişkileri yalnız zaman + 6-basamak',
'skor eşleşmesidir; 112 Trade Intent için önceki çalışmadaki',
'kesin candidate→top5→intent zinciri ile karıştırılmamalıdır.',
'V2 kararları geçmişte canlı risk kapısında değildi; V2 PENDING/VETO',
'etiketini gerçek açılmama nedeni olarak göstermiyoruz.',
'',
'## Dört LONG_AVOID açılışı aynı fiyatla SHORT olsaydı?',
'',
'Yöntem: Binance NEARUSDT public Futures 1m OHLC; tarihsel gerçek',
'LONG BUY fiyatı, farazi SHORT açılış fiyatı; 3x kaldıraç.',
'İşlem açma/pozisyon taşıma yetkisi yok. Giriş/çıkış dakikalarının',
'OHLC mumları senaryoya katılmadı; bunlar kesin uygulanabilir',
'saat ve fiyat emirleri değildir. Önce net P&L ve funding/komisyon',
'dahil edilmemiş **brüt 3x ROI** üst sınırlarıdır.',
'',
'| Gerçek LONG açılışı TR | SHORT MFE (ilk 60m) | SHORT lehine dip fiyatı | Dip saati | 60m en aleyhe ROI | LONG kapanışında SHORT ROI |',
'|---|---:|---:|---|---:|---:|',
])
for x in short:
 v=x['windows']['60m']
 lines.append(f"| {x['original_long_open_tr'][5:16].replace('T',' ')} | +%{v['short_mfe_roi_pct']:.3f} | {v['short_mfe_low_price']:.3f} | {v['short_mfe_time_tr'][11:16]} | %{v['short_mae_roi_pct']:.3f} | %{x['hypothetical_short_roi_at_long_close_pct']:+.3f} |")
lines.extend([
'',
'**Dipten dönüş gözlemi:**',
'',
])
for x in short:
 v=x['windows']['60m']
 p=v['short_mfe_roi_pct']
 r=v['max_reversal_after_best_roi_points']
 lines.append(f"- {x['original_long_open_tr'][5:16].replace('T',' ')}: ilk 60m SHORT tepe +%{p:.3f} ROI; "
 f"{'izleyen tam mumlarda dipten sonraki en büyük ters hareket '+str(r)+' ROI puanı' if r is not None else 'ilk 60m dip sonrası tam 1m mumda dönüş kanıtı henüz yok'}. "
 f"120m MFE +%{x['windows']['120m']['short_mfe_roi_pct']:.3f}, "
 f"240m MFE +%{x['windows']['240m']['short_mfe_roi_pct']:.3f}.")
lines.extend([
'',
'**Önemli:** 14 Kasım 06:34 LONG pozisyonu yalnız ~2 dakika açık',
'kaldığından SHORT, o gerçek LONG kapanışına göre negatif ROI',
'gösteriyor; +%5,165 SHORT tepe ancak yaklaşık bir saat',
'beklenirse geçmiş fiyat yolunda görülebiliyor. Bu, pratikte',
'o kadar süre zararı ve marjin riskini taşıyabileceğimiz',
'anlamına gelmez. İki yönde pozisyon açılması da ayrı bir',
'merkezi risk ve karşıt pozisyon yasağına tabidir.',
'',
'### %0,60–%2,50 ARM dokunuşları',
'',
'| SHORT varsayımı (TR) | %0,60 | %0,95 | %1,20 | %1,65 | %2,00 | %2,50 |',
'|---|---|---|---|---|---|---|',
])
for x in short:
 f=x['windows']['60m']['first_arm_touch_time_tr']
 vals=['Evet' if str(n) in f else 'Hayır' for n in (.6,.95,1.2,1.65,2.0,2.5)]
 lines.append(f"| {x['original_long_open_tr'][5:16].replace('T',' ')} | "+" | ".join(vals)+" |")
lines.extend([
'',
'- ARM dokunması, geri çekilme yüzdesine göre gerçekleşmiş',
'  trailing stop fill’i, kârın kilitlendiğini veya net kazanımı',
'  **KANITLAMAZ**. Mumun high/low sırası bilinmiyor.',
'- 3x örnek %0,08 notional gidiş-dönüş maliyet yaklaşık %0,24',
'  ROI puanına denk gelir; SHORT tarafı spread, slippage, funding',
'  ve Binance’in fiili BNB komisyonu bu hesapta yok.',
'- Gerçek SHORT1 INJUSDT olduğundan bu dört NEARUSDT senaryosu',
'  SHORT1 stratejisi için gerçek backtest diye sunulamaz.',
'',
'## Teknik karar',
'',
'1. Missing LONG tarafında aynı skordan tekrar yayılan sinyalleri',
'   ayrı fırsat saymayıp, ilk MODEL kararından itibaren',
'   Master whale veto, açık pozisyon, Sniper ve PENDING',
'   geçişlerini ayrı trace alanlarıyla saymak gerek.',
'2. Açılmalı pencerelerdeki 11 TP_FIRST sanal sonucu tek başına',
'   eşikleri gevşetmek için kullanma; yeni farklı dönemlerde',
'   karşıolgusal net ücretli, 1m Entry Confirmation replay yap.',
'3. SHORT için yüksek farazi MFE çıktığı için hemen SHORT açmak',
'   güvenli değil; LONG/SHORT merkezi Risk Master ve',
'   karşıt pozisyon engeli birlikte test edilmeli.',
'4. Çakışan 7 pencere geçmişte 0 gerçek fill; araştırma',
'   senaryosunda kesin NO_TRADE/REJECT korunuyor.',
'5. Her iki canlı bot kapalı, Stage24 canlı emir NO-GO,',
'   hiç Binance POST, Redis üretim yazması veya parametre',
'   değişikliği yapılmadı.',
'',
'## Yeniden çalıştırma',
'',
'- research/trace/replay_long1_missed_wanted_and_opposite_short_v1.py',
'- research/trace/augment_long1_missed_upstream_guards_readonly_v1.py',
'- research/trace/render_long1_missed_wanted_opposite_short_report_v1.py',
'- Ayrıntılı fiyat yolu JSON ve iki CSV bu raporla aynı klasörde.',
])
(ROOT/(name+'.md')).write_text('\n'.join(lines)+'\n')
print(json.dumps({'status':'PASS','report_rows_missed':len(recs),'short_scenarios':len(out),
 'files':4,'production_redis_writes':0,'binance_orders':0},sort_keys=True))
