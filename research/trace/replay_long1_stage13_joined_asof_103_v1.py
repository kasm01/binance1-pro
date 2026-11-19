"""Stage13 LONG1 joint timeline; conservative research only.

103 observed model-event clocks -> stage12 historical 3m/5m proxy
recovery -> frozen strict 1m entry confirmation on fully CLOSED bars
-> NEXT 1m OPEN fictional fill -> TP1.25 / six-tier HYBRID / stop2.99.
No implicit reuse of old pending: NEW model/intent not available and
'research_ready' does not equal actual trade eligibility.
Retro labels used only for reporting and explicit user-conflict veto.
Cost and stop are illustrative, all decisions as-of with no future input.
"""
from __future__ import annotations
from pathlib import Path
from bisect import bisect_right
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
from zipfile import ZipFile
from io import TextIOWrapper
import csv,gzip,json
from research.regime.long1_six_tier_lock_shadow_v1 import LockState,update
R=Path(__file__).resolve().parents[2]
BASE=R/'research/results'; TR=ZoneInfo('Europe/Istanbul')
M=json.loads((BASE/'LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json').read_text())['events']
C=json.loads((BASE/'LONG1_STAGE12_103_BINANCE_CLOSED3M5M_CONTRA_PROXY_20261119.json').read_text())['events']
CONFIG=json.loads((R/'research/staging/long1_research_only_settings_v2.json').read_text())['entry_revalidation']
REF=json.loads((R/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json').read_text())
REAL=json.loads((BASE/'LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())['trades']
assert len(M)==len(C)==103
model={x['model_ts_tr']:x for x in M}
context={x['model_event_tr']:x for x in C}
assert model.keys()==context.keys()
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 b=[dict(t=int(z['open_time_ms']),o=float(z['open']),h=float(z['high']),l=float(z['low']),
       c=float(z['close']),q=float(z['quote_volume']),buy=float(z['taker_buy_quote_volume']))
    for z in csv.DictReader(f)]
assert len(b)==8640
closes=[z['t']+60000 for z in b]
assert all(closes[i]-closes[i-1]==60000 for i in range(1,len(b)))
intervals=[(datetime.fromisoformat(z['start_tr']),datetime.fromisoformat(z['end_tr']),z['user_label'])
           for z in REF['user_intervals']]
brok=[(datetime.fromisoformat(z['open_tr']),datetime.fromisoformat(z['close_tr'])) for z in REAL]
def conflict(ts_ms):
 dt=datetime.fromtimestamp(ts_ms/1000,TR)
 return len({tag for lo,hi,tag in intervals if lo<=dt<hi})>1
def flow(i,n):
 rows=b[i-n+1:i+1];volume=sum(z['q'] for z in rows)
 return 2*sum(z['buy'] for z in rows)/volume-1 if volume else -1
def feat(i):
 z=b[i];span=z['h']-z['l']
 return {'body':max(z['c']-z['o'],0)/span if span>0 else 0,
  'retrace':(z['h']-z['c'])/span if span>0 else 1,
  'flow1':flow(i,1),'flow3':flow(i,3),
  'r3':100*(b[i]['c']/b[i-3]['c']-1)}
def entry_pass(m,origin):
 return (m['body']>=CONFIG['bull_body_to_range_min']
  and m['retrace']<=CONFIG['upper_retrace_to_range_max']
  and m['flow1']>=CONFIG['one_minute_taker_signed_flow_min']
  and m['flow3']>=origin['flow3']+CONFIG['flow_3m_improvement_over_origin_min']
  and m['r3']>=origin['r3']+CONFIG['price_3m_return_improvement_percentage_points_min']
  and m['r3']>0 and m['flow3']>0)
def outcomes(entryidx,policy):
 entry=b[entryidx]['o'];tp=entry*(1+1.25/300);stop=entry*(1-2.99/100)
 state=LockState()
 for j in range(entryidx,entryidx+60):
  candle=b[j]
  # Stop-first with pessimistic full-minute OHLC; gap exits at true open.
  if candle['o']<=stop:return j,'STOP_GAP',round(300*(candle['o']/entry-1)-.24,5)
  if candle['o']>=tp:return j,'TP_GAP',round(300*(candle['o']/entry-1)-.24,5)
  if candle['l']<=stop:return j,'SL_FIRST',-9.21
  if candle['h']>=tp:return j,'TP_FIRST',1.01
  if policy=='hybrid':
   result=update(state,300*(candle['c']/entry-1),closes[j])
   if result['state']=='SHADOW_TRAIL_TRIGGER':
    nxt=b[j+1]['o']
    return j+1,'TRAIL_NEXT_OPEN',round(300*(nxt/entry-1)-.24,5)
 j=entryidx+59
 return j,'TIMEOUT',round(300*(b[j]['c']/entry-1)-.24,5)
records=[]
for ts,m in sorted(model.items()):
 c=context[ts];t=int(datetime.fromisoformat(ts).timestamp()*1000)
 origin_idx=bisect_right(closes,t)-1
 origin=feat(origin_idx)
 a={'model_time_tr':ts,'label':m['research_label'],'proxy_origin_contra':c['origin_proxy_contra'],
    'model_score_pass':m['model_score']>=m['actual_rolling_threshold'],
    'actual_new_intent_verified':False,'partial_1m_entry_verified':False,
    'true_whale_market_context_reproduced':False,'actual_trade_authorized':False}
 if conflict(t):
  a['decision']='CONFLICT_ORIGIN';records.append(a);continue
 if not a['model_score_pass']:
  a['decision']='MODEL_GATE';records.append(a);continue
 if c['origin_proxy_contra'] and not c['research_full_closed_recovery_found']:
  a['decision']='CONTRA_WAIT_30M';records.append(a);continue
 # Only try after 3m+5m fully closed recovery. This 30m waiting is a
 # research window, NEVER reuse of a real pending attempt.
 ready_ms=(c['research_recovery']['last_full_1m_close_ms']
           if c['origin_proxy_contra'] else closes[origin_idx])
 assert ready_ms>=closes[origin_idx]
 start_idx=bisect_right(closes,ready_ms)
 assert 0<=start_idx<len(b)
 found=None;count=0
 for i in range(start_idx,start_idx+CONFIG['max_completed_1m_rechecks']):
  assert i+65<len(b)
  count+=1
  if entry_pass(feat(i),origin):
   found=i;break
 a['proxy_1m_rechecks']=count
 a['contra_recovery_first_asof_ms']=ready_ms
 if found is None:
  a['decision']='ENTRY_PENDING_EXPIRED';records.append(a);continue
 entryidx=found+1
 assert b[entryidx]['t']==closes[found]
 if conflict(closes[found]) or conflict(b[entryidx]['t']):
  a['decision']='CONFLICT_AT_ENTRY';records.append(a);continue
 a.update(decision='RESEARCH_READY_NO_REAL_INTENT',research_entry_ms=b[entryidx]['t'],
          entry_price=b[entryidx]['o'],entry_idx=entryidx,
          candidate_1m_features={k:round(v,6) for k,v in feat(found).items()},
          closed_1m_decision_ms=closes[found],
          closed_3m_5m_recovery_from_archive=c['origin_proxy_contra'],
          overlaps_real_broker_long=any(lo<=datetime.fromtimestamp(b[entryidx]['t']/1000,TR)<hi for lo,hi in brok))
 for policy in ('fixed','hybrid'):
  j,why,roi=outcomes(entryidx,policy)
  a[policy]={'exit_idx':j,'exit_reason':why,'net_roi_points':roi}
 records.append(a)
assert len(records)==103
summary={}
for policy in ('fixed','hybrid'):
 booked=[];busy=-1;brok_book=[];brok_busy=-1
 for a in records:
  if a['decision']!='RESEARCH_READY_NO_REAL_INTENT':continue
  if a['entry_idx']>busy:
   booked.append(a);busy=a[policy]['exit_idx']
  if a['entry_idx']>brok_busy and not a['overlaps_real_broker_long']:
   brok_book.append(a);brok_busy=a[policy]['exit_idx']
 def summarize(items):
  return {'opens':len(items),
   'cohorts':dict(Counter(z['label'] for z in items)),
   'exits':dict(Counter(z[policy]['exit_reason'] for z in items)),
   'net_roi_points_total':round(sum(z[policy]['net_roi_points'] for z in items),4),
   'net_roi_points_by_cohort':{k:round(sum(z[policy]['net_roi_points'] for z in items if z['label']==k),4)
          for k in ('LONG_TARGET','LONG_AVOID','UNLABELLED')},
   'model_times':[z['model_time_tr'] for z in items]}
 summary[policy]={'pure_synthetic_single_position':summarize(booked),
                 'real_broker_occupancy_sensitivity':summarize(brok_book)}
decisions=Counter(z['decision'] for z in records)
out={'schema':'long1_stage13_closed_3m5m_then_frozen_1m_103_asof_v1',
 'model_events':103,'date_basis':'2026-11-11_to_2026-11-15_TRT',
 'candidate_settings':'research/staging/long1_research_only_settings_v2.json',
 '3m5m_recovery_can_delay_up_to_30m':True,
 '1m_entry_max_completed_bar_rechecks':CONFIG['max_completed_1m_rechecks'],
 'user_labels_not_used_as_trade_whitelist':True,
 'conflicting_origins_and_entries_hard_rejected':True,
 'actual_fresh_model_or_intent_not_reproduced':True,
 'original_native_pending_may_expire_before_recovery':True,
 'historic_full_partial_minute_entry_unavailable':True,
 'true_live_whale_market_context_unavailable':True,
 'simulated_entry_at_next_open_after_closed_bar':True,
 'fixed_exit_gross_roi_tp':1.25,'hybrid_uses_six_tiers':True,
 'fixed_price_stop_pct':2.99,'max_hold_minutes':60,
 'fee_3x_roi_points_assumed':.24,'native_stop_spread_funding_slippage_not_modeled':True,
 'not_portfolio_equity_return':True,'real_exchange_orders':0,'prod_redis_writes':0,
 'decisions':dict(decisions),
 'ready_by_reference':dict(Counter(z['label'] for z in records if z['decision']=='RESEARCH_READY_NO_REAL_INTENT')),
 'exit_comparison':summary,'events':records}
dst=BASE/'LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json'
dst.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'result':'PASS','decision_counts':out['decisions'],
 'ready_by_label':out['ready_by_reference'],
 'exit_books':summary,'no_real_orders':True},sort_keys=True))
