"""Read-only audit of user-labelled 11-15 Nov windows, 1m green candle .22 ROI.

A green candle at CLOSE and its earlier HIGH are hindsight information.
An isolated candle OPEN->HIGH gross 3x ROI >=.22 is not proof that an
existing LONG bot could enter at OPEN or successfully ARM/EXIT.
Only actual retained MODEL LONG event clocks count as observed events.
No timeline heuristics used to manufacture MODEL -> Intent ancestry.
No exchange calls, redis writes, timers, production modifications.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from collections import Counter
from bisect import bisect_left
import csv,gzip,json
R=Path(__file__).resolve().parents[2];OUT=R/'research/results'
TR=ZoneInfo('Europe/Istanbul')
W=json.loads((R/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json').read_text())['user_intervals']
S=json.loads((OUT/'LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())['events']
P=json.loads((OUT/'LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json').read_text())['events']
assert len(W)==70 and len(S)==103 and len(P)==103
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 B=[{**{k:float(x[k]) for k in ('open','high','low','close')},
    't':int(x['open_time_ms']),
    'flow':float(x['canonical_kline_taker_imbalance']),
    'volume':float(x['quote_volume'])} for x in csv.DictReader(f)]
assert len(B)==8640
bar_ms=[b['t'] for b in B]
model_minute={}
for x in S:
 ts=datetime.fromisoformat(x['model_time_tr'])
 k=int(ts.timestamp()*1000)//60000*60000
 model_minute.setdefault(k,[]).append(x)
assert sum(map(len,model_minute.values()))==103
# The interval is [start,end) for underlying bar OPEN, but only fully
# INSIDE windows have their full 1m future outcome within user window.
def inside(b,w):
 lo=int(datetime.fromisoformat(w['start_tr']).timestamp()*1000)
 hi=int(datetime.fromisoformat(w['end_tr']).timestamp()*1000)
 return lo<=b['t'] and b['t']+60000<=hi
def labels_at(t):
 return sorted({w['user_label'] for w in W if inside({'t':t},w)})
def bar_row(b):
 o=b['open']; h=b['high'];l=b['low'];c=b['close']
 high_roi=300*(h/o-1)
 close_roi=300*(c/o-1)
 green=c>o
 highhit=green and high_roi>=.22-1e-10
 closehit=green and close_roi>=.22-1e-10
 models=model_minute.get(b['t'],[])
 return {'start_tr':datetime.fromtimestamp(b['t']/1000,TR).isoformat(),
  'end_tr':datetime.fromtimestamp((b['t']+60000)/1000,TR).isoformat(),
  'open':o,'high':h,'low':l,'close':c,
  'gross_3x_roi_open_to_high_pp':round(high_roi,6),
  'gross_3x_roi_open_to_close_pp':round(close_roi,6),
  'green':green,'green_open_to_high_arm_022_hit':highhit,
  'green_open_to_close_arm_022_hit':closehit,
  'net_ideal_floor_roi_pp_after_0p10_gb_0p24_fee':-.12 if highhit else None,
  'same_minute_observed_long_model_events':len(models),
  'same_minute_model_decisions':[z['decision'] for z in models],
  'same_minute_model_times':[z['model_time_tr'] for z in models],
  'signal_absence_in_same_minute':not bool(models),
  'market_flow_1m':round(b['flow'],6),
  'user_window_labels':labels_at(b['t']),
  'conflict_no_trade':len(labels_at(b['t']))>1,
  'not_a_real_open_fill':True}
def summarize(rows):
 return {'fully_within_1m_candles':len(rows),
  'green_1m_candles':sum(x['green'] for x in rows),
  'green_open_to_high_022_arms':sum(x['green_open_to_high_arm_022_hit'] for x in rows),
  'green_open_to_close_022_arms':sum(x['green_open_to_close_arm_022_hit'] for x in rows),
  'high_022_arm_no_long_model_same_minute':sum(x['green_open_to_high_arm_022_hit'] and x['signal_absence_in_same_minute'] for x in rows),
  'close_022_arm_no_long_model_same_minute':sum(x['green_open_to_close_arm_022_hit'] and x['signal_absence_in_same_minute'] for x in rows),
  'high_022_arm_with_long_model_same_minute':sum(x['green_open_to_high_arm_022_hit'] and not x['signal_absence_in_same_minute'] for x in rows),
  'conflict_green_high_022_candles':sum(x['green_open_to_high_arm_022_hit'] and x['conflict_no_trade'] for x in rows),
  'observed_long_model_events_on_candles':sum(x['same_minute_observed_long_model_events'] for x in rows)}
result=[]
union_ids={};by_label={label:{} for label in ('LONG_WANTED','LONG_AVOID')}
for ix,w in enumerate(W,1):
 lo=int(datetime.fromisoformat(w['start_tr']).timestamp()*1000)
 hi=int(datetime.fromisoformat(w['end_tr']).timestamp()*1000)
 a=bisect_left(bar_ms,lo);b=bisect_left(bar_ms,hi)
 rows=[bar_row(z) for z in B[a:b] if inside(z,w)]
 result.append({'window_number':ix,'start_tr':w['start_tr'],'end_tr':w['end_tr'],
   'user_label':w['user_label'],'counts':summarize(rows),
   'green_open_to_high_022_details':[z for z in rows if z['green_open_to_high_arm_022_hit']],
   'green_other_details':[z for z in rows if z['green'] and not z['green_open_to_high_arm_022_hit']]})
 for z in rows:
  key=z['start_tr']
  by_label[w['user_label']][key]=z
  union_ids[key]=z
# Unique candles in the group, no double counting from overlapping windows.
by_group={k:summarize(list(v.values())) for k,v in by_label.items()}
by_group['UNION_ALL_UNIQUE_CANDLES']=summarize(list(union_ids.values()))
by_group['LONG_WANTED_NO_MODEL_MINUTE_IN_ENTIRE_WINDOW']={}
for w in result:
 if w['user_label']=='LONG_WANTED' and w['counts']['observed_long_model_events_on_candles']==0:
  by_group['LONG_WANTED_NO_MODEL_MINUTE_IN_ENTIRE_WINDOW'][str(w['window_number'])]=w['counts']['green_open_to_high_022_arms']
missing_only=[w for w in result if w['user_label']=='LONG_WANTED' and
   w['counts']['observed_long_model_events_on_candles']==0]
out={'schema':'long1_user_70_1m_green_022_arm_observation_audit_v1',
 'period':'2026-11-11_to_2026-11-15_TRT','symbol':'NEARUSDT',
 'input_candles':len(B),'user_windows':70,'user_target_windows':44,
 'user_avoid_windows':26,
 'historical_model_events_103':len(S),
 'only_fully_inside_1m_candles':True,
 'retrospective_green_is_not_knowable_before_candle_close':True,
 'open_to_high_is_hindsight_extremum_not_trade_fill':True,
 'candle_open_price_is_hypothetical_not_actual_entry':True,
 'arm_gross_roi_pp':.22,'leverage':3,
 'minimum_price_up_from_open_pct_for_022_3x_roi':.22/3,
 'fee_roi_pp_assumed':.24,'giveback_roi_pp':.10,
 'theoretical_first_floor_net_roi_pp':-.12,
 'model_same_minute_does_not_prove_executable_signal':True,
 'no_model_in_minute_not_proof_engine_never_evaluated':True,
 'historical_window_labels_not_trading_rules':True,
 'global_conflict_no_trade':True,
 'total_target_windows_without_same_minute_model':len(missing_only),
 'target_without_model_high022_hits_sum':sum(w['counts']['green_open_to_high_022_arms'] for w in missing_only),
 'target_without_model_candle_details':[{'window_number':w['window_number'],
    'start_tr':w['start_tr'],'end_tr':w['end_tr'],
    'green_high022_hits':w['counts']['green_open_to_high_022_arms'],
    'green_close022_hits':w['counts']['green_open_to_close_022_arms'],
    'green_1m':w['counts']['green_1m_candles']} for w in missing_only],
 'group_unique_counts':by_group,'windows':result,
 'candidate_signal_missed_is_diagnostic_only':True,
 'exact_model_intent_lineage_verified':False,
 'real_orders':0,'production_redis_writes':0}
path=OUT/'LONG1_70_WINDOWS_GREEN_022_ARM_AND_MISSING_MODEL_20261120.json'
path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','group_unique_counts':{k:v for k,v in by_group.items() if not k.startswith('LONG_WANTED_NO_MODEL')},
 'fully_no_model_wanted_windows':len(missing_only),
 'green_high_022_in_no_model_wanted_windows_sum':out['target_without_model_high022_hits_sum'],
 'windows_top_by_022':sorted([{'window':x['window_number'],'start_tr':x['start_tr'],
 'hit':x['counts']['green_open_to_high_022_arms'],
 'no_model_hit':x['counts']['high_022_arm_no_long_model_same_minute']}
 for x in result if x['user_label']=='LONG_WANTED'],key=lambda x:-x['hit'])[:12]},sort_keys=True))
