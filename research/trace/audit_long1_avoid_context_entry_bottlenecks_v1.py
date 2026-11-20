"""As-of comparators for LONG_AVOID vs LONG_WANTED; no real trading authority.

Two independent cohorts:
A) 103 genuine observed model events, classify Stage13 proxy decisions, then
   measure ex-post next fully opened 1m candle price excursions.
B) Every 1m fully closed green +0.22ROI close candle within a user window,
   as-of entry proxy for NEXT 1m open; no assumed MODEL/intent.
Exclude both-label conflict windows and pre-existing real broker occupancy.
No future candle HIGH used to select an entry; HIGH/LOW measured AFTER signal.
Fee assumption 0.24 ROI pp, no fill/slippage/funding, no production writes.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict,Counter
from bisect import bisect_left
import json,gzip,csv,statistics
R=Path(__file__).resolve().parents[2];OUT=R/'research/results';TR=ZoneInfo('Europe/Istanbul')
S=json.loads((OUT/'LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
REF=json.loads((R/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json').read_text())
REAL=json.loads((OUT/'LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())['trades']
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 B=[dict(t=int(x['open_time_ms']),o=float(x['open']),h=float(x['high']),l=float(x['low']),c=float(x['close']),
         q=float(x['quote_volume']),buy=float(x['taker_buy_quote_volume'])) for x in csv.DictReader(f)]
assert len(B)==8640
T=[z['t'] for z in B]
M={};mi=defaultdict(list)
for z in S['events']:
 dt=datetime.fromisoformat(z['model_time_tr']);idx=bisect_left(T,int(dt.timestamp()*1000))
 if idx<len(B) and T[idx]>int(dt.timestamp()*1000):idx-=1
 assert idx>=0 and B[idx]['t']<=int(dt.timestamp()*1000)<B[idx]['t']+60000
 mi[idx].append(z)
assert sum(map(len,mi.values()))==103
ranges=[(int(datetime.fromisoformat(z['start_tr']).timestamp()*1000),
         int(datetime.fromisoformat(z['end_tr']).timestamp()*1000),z['user_label']) for z in REF['user_intervals']]
brok=[(int(datetime.fromisoformat(z['open_tr']).timestamp()*1000),
       int(datetime.fromisoformat(z['close_tr']).timestamp()*1000)) for z in REAL]
def labels(ms):
 return sorted({l for lo,hi,l in ranges if lo<=ms<hi})
def occupation(ms):
 return any(lo<=ms<hi for lo,hi in brok)
def f3(i):
 q=sum(z['q'] for z in B[i-2:i+1])
 return 2*sum(z['buy'] for z in B[i-2:i+1])/q-1 if q else 0.
def f5(i):
 # five COMPLETED 1m bars only, not live 5m full candle authority.
 return 100*(B[i]['c']/B[i-5]['c']-1)
def feats(i):
 z=B[i];rng=z['h']-z['l']
 return {
 'body':max(z['c']-z['o'],0)/rng if rng>0 else 0.,
 'retrace':(z['h']-z['c'])/rng if rng>0 else 1.,
 'flow1':2*z['buy']/z['q']-1 if z['q'] else 0.,
 'flow3':f3(i),
 'r3':100*(z['c']/B[i-3]['c']-1),
 'r5':f5(i),
 'flow3_delta':f3(i)-f3(i-3),
 'r3_delta':100*(z['c']/B[i-3]['c']-B[i-3]['c']/B[i-6]['c']),
 'closed_green_arm':z['c']>z['o'] and 300*(z['c']/z['o']-1)>=.22-1e-10
 }
def gates(z):
 return {
 'body_live_min_0p15':z['body']>=.15,
 'body_research_min_0p22':z['body']>=.22,
 'retrace_live_max_0p50':z['retrace']<=.50,
 'retrace_research_max_0p35':z['retrace']<=.35,
 'flow1_research_min_0p03':z['flow1']>=.03,
 'flow3_research_positive':z['flow3']>0.,
 'r3_research_positive':z['r3']>0.,
 'flow3_research_delta_0p08':z['flow3_delta']>=.08,
 'r3_research_delta_0p10pp':z['r3_delta']>=.10,
 'r5_closed_proxy_positive':z['r5']>0.,
 'r5_closed_proxy_strict_negative_veto':z['r5']>=-.10
 }
def forward(idx,h):
 # Entry ONLY AFTER candle idx fully closes, at idx+1 OPEN.
 i=idx+1
 if i+h>len(B):return None
 entry=B[i]['o']
 rows=B[i:i+h]
 mfe=300*(max(x['h'] for x in rows)/entry-1)
 mae=300*(min(x['l'] for x in rows)/entry-1)
 end=300*(rows[-1]['c']/entry-1)
 return {'assumed_next_1m_open':entry,'mfe_roi_pp':round(mfe,6),
  'mae_roi_pp':round(mae,6),'end_roi_pp':round(end,6),
  'gross_0p22_touch':mfe>=.22-1e-10,
  'gross_0p35_touch':mfe>=.35-1e-10,
  'gross_0p80_touch':mfe>=.80-1e-10,
  'net_positive_end_after_fee':end>.24,
  'drawdown_below_negative_0p80roi':mae<=-.8}
def summarize(items):
 c=Counter()
 for z in items:
  c['count']+=1
  for k in ('gross_0p22_touch','gross_0p35_touch','gross_0p80_touch','net_positive_end_after_fee','drawdown_below_negative_0p80roi'):
   c[k]+=bool(z['outcome_5m'][k])
  c['actual_model_same_minute']+=bool(z['model_ids_same_minute'])
  c['broker_occupied']+=z['broker_occupied']
  for k,v in z['gates'].items():
   c['pass_'+k]+=bool(v)
  c['all_live_shape_body_retrace']+=z['gates']['body_live_min_0p15'] and z['gates']['retrace_live_max_0p50']
  c['all_strict_1m_filters_proxy']+=all(z['gates'][k] for k in ('body_research_min_0p22','retrace_research_max_0p35',
    'flow1_research_min_0p03','flow3_research_positive','r3_research_positive',
    'flow3_research_delta_0p08','r3_research_delta_0p10pp'))
  c['all_strict_1m_and_5m_proxy_positive']+=all(z['gates'][k] for k in ('body_research_min_0p22','retrace_research_max_0p35',
    'flow1_research_min_0p03','flow3_research_positive','r3_research_positive',
    'flow3_research_delta_0p08','r3_research_delta_0p10pp','r5_closed_proxy_positive'))
 c['sum_5m_mfe_pp']=round(sum(z['outcome_5m']['mfe_roi_pp'] for z in items),4)
 c['sum_5m_mae_pp']=round(sum(z['outcome_5m']['mae_roi_pp'] for z in items),4)
 return dict(c)
# A: genuine MODEL event available once per event. Event candle is
# incomplete when emitted: don't use its current high/close as entry.
actual=[]
for i,members in mi.items():
 for m in members:
  point=forward(i,5)
  if point is None:continue
  x={'model_time_tr':m['model_time_tr'],'original_reference':m['label'],
     'stage13_decision':m['decision'],'context_contra_proxy':m['proxy_origin_contra'],
     'model_gate_passed':m['model_score_pass'],
     'entry_same_minute_unverified':True,'outcome_5m':point,
     'next_open_time_tr':datetime.fromtimestamp(B[i+1]['t']/1000,TR).isoformat()}
  actual.append(x)
# B: screen only completed 1m green close events. Posterior labels
# become reporting segments, NOT input to the candle trigger.
rows=[]
for i in range(7,len(B)-7):
 ms=B[i]['t'];lab=labels(ms)
 if not lab:continue
 # A COMPLETED one-minute candle must fit fully in that label window.
 lab_close=labels(ms+59999)
 if lab!=lab_close:continue
 x=feats(i)
 if not x['closed_green_arm']:continue
 g=gates(x)
 out=forward(i,5)
 if out is None:continue
 present=[m['model_time_tr'] for m in mi.get(i,())]
 rows.append({'minute_close_tr':datetime.fromtimestamp((ms+60000)/1000,TR).isoformat(),
  'entry_proxy_next_open_tr':datetime.fromtimestamp(B[i+1]['t']/1000,TR).isoformat(),
  'labels':lab,'groups':'CONFLICT' if len(lab)>1 else lab[0],
  'model_ids_same_minute':present,'broker_occupied':occupation(B[i+1]['t']),
  'feats':{k:round(v,6) if isinstance(v,float) else v for k,v in x.items()},
  'gates':g,'outcome_5m':out,
  'not_an_executable_signal':True})
by_group={name:[z for z in rows if z['groups']==name] for name in ('LONG_AVOID','LONG_WANTED','CONFLICT')}
avoid_by_window=[]
for num,w in enumerate(REF['user_intervals'],1):
 if w['user_label']!='LONG_AVOID':continue
 lo=int(datetime.fromisoformat(w['start_tr']).timestamp()*1000)
 hi=int(datetime.fromisoformat(w['end_tr']).timestamp()*1000)
 subset=[z for z in rows if z['groups']=='LONG_AVOID' and lo< int(datetime.fromisoformat(z['minute_close_tr']).timestamp()*1000)<=hi]
 audit=summarize(subset)
 audit.update(window_number=num,start_tr=w['start_tr'],end_tr=w['end_tr'])
 avoid_by_window.append(audit)
strict_keys=('body_research_min_0p22','retrace_research_max_0p35','flow1_research_min_0p03',
  'flow3_research_positive','r3_research_positive','flow3_research_delta_0p08',
  'r3_research_delta_0p10pp')
eligible=[z for z in rows if z['groups']=='LONG_AVOID' and all(z['gates'][k] for k in strict_keys)
 and not z['broker_occupied'] and z['gates']['r5_closed_proxy_positive']]
# Nonoverlap 5m windows (DO NOT optimize entries by future outcomes)
selected=[];last=-1
for z in eligible:
 idx=bisect_left(T,int(datetime.fromisoformat(z['entry_proxy_next_open_tr']).timestamp()*1000))
 if idx<=last:continue
 selected.append(z);last=idx+5
measures={
 '5m_mfe_022_seen':sum(z['outcome_5m']['gross_0p22_touch'] for z in selected),
 '5m_mfe_035_seen':sum(z['outcome_5m']['gross_0p35_touch'] for z in selected),
 '5m_mfe_080_seen':sum(z['outcome_5m']['gross_0p80_touch'] for z in selected),
 '5m_end_net_positive_after_fee':sum(z['outcome_5m']['net_positive_end_after_fee'] for z in selected),
 '5m_end_net_roi_pp_sum_assuming_exit_at_fifth_close':round(sum(z['outcome_5m']['end_roi_pp']-.24 for z in selected),5),
 '5m_mfe_mae_same_bar_order_unknown':True}
out={'schema':'long1_avoid_asof_context_entry_bottleneck_v1',
 'source_model_events':len(actual),'real_model_long_avoid_events':sum(z['original_reference']=='LONG_AVOID' for z in actual),
 'research_stage13_model_decision_counts_avoid':dict(Counter(z['stage13_decision'] for z in actual if z['original_reference']=='LONG_AVOID')),
 'actual_model_avoid_future_5m_by_stage':{k:{'events':len([z for z in actual if z['original_reference']=='LONG_AVOID' and z['stage13_decision']==k]),
  '5m_mfe_arm022':sum(z['outcome_5m']['gross_0p22_touch'] for z in actual if z['original_reference']=='LONG_AVOID' and z['stage13_decision']==k),
  '5m_mfe_arm035':sum(z['outcome_5m']['gross_0p35_touch'] for z in actual if z['original_reference']=='LONG_AVOID' and z['stage13_decision']==k),
  '5m_mfe_arm080':sum(z['outcome_5m']['gross_0p80_touch'] for z in actual if z['original_reference']=='LONG_AVOID' and z['stage13_decision']==k),
  '5m_end_net_positive_after_fee':sum(z['outcome_5m']['net_positive_end_after_fee'] for z in actual if z['original_reference']=='LONG_AVOID' and z['stage13_decision']==k)}
  for k in ('MODEL_GATE','CONTRA_WAIT_30M','ENTRY_PENDING_EXPIRED','RESEARCH_READY_NO_REAL_INTENT')},
 'eligible_closed_green_minute_trigger':True,
 'trigger_only_fully_closed_1m_return_open_to_close_3x_roi_ge_0p22':True,
 'market_5m_return_is_past_5_COMPLETED_1m_not_live_5m_gate':True,
 'research_thresholds':{'body_min':.22,'retrace_max':.35,'flow1_min':.03,
   'flow3_positive':True,'r3_positive':True,'flow3_delta_min':.08,'r3_delta_pp_min':.10,
   'five_completed_1m_return_positive_support':True},
 'native_live_quality_partial_sniper_whale_unavailable':True,
 'user_labels_reporting_only_conflicts_hard_veto':True,
 'one_coin_nonoverlap_five_minute_screen_for_diagnostic_only':True,
 'no_true_new_model_or_intent_generated':True,
 'no_model_minute_not_complete_negative_signal_evidence':True,
 'no_future_high_used_to_generate_trigger':True,
 'fee_3x_roi_pp_assumed':.24,
 '5m_model_events':actual,
 'green_close_arm_022_groups':{k:summarize(v) for k,v in by_group.items()},
 'green_close_arm_022_rows':rows,
 'avoid_windows':avoid_by_window,
 'strict_avoid_candidates_before_dedupe':len(eligible),
 'strict_avoid_nonoverlap_5m_candidates':len(selected),
 'strict_avoid_nonoverlap_5m_measures':measures,
 'strict_avoid_nonoverlap_rows':selected,
 'real_orders':0,'redis_writes':0}
path=OUT/'LONG1_AVOID_ASOF_GATE_COMPARISON_20261120.json'
path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS',
 'stage13_real_avoid_events':out['real_model_long_avoid_events'],
 'stage13_by_stage':out['actual_model_avoid_future_5m_by_stage'],
 'green_close_arm022_groups':out['green_close_arm_022_groups'],
 'strict_avoid_before_dedupe':len(eligible),
 'strict_avoid_5m_nonoverlap':len(selected),
 'strict_avoid_5m_measures':measures,
 'top_avoid_windows':sorted(avoid_by_window,key=lambda v:-v['count'])[:8],
 'orders':0},sort_keys=True))
