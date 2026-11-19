"""Paired and sequential LONG1 hybrid exit research against closed 1m archive.

Three entry profiles are frozen by prior as-of 103-model replay. For each
entry, compare fixed TP1.25 and six-tier close-trigger then next-bar open
fill HYBRID (TP1.25 cap retained), as well as uncapped runner.
All policies use hard 2.99% price SL, 60m max, stop-first in ambiguous bars.
Never assert 1m close-based trail is executable in the same bar: trigger
on bar CLOSE, assumed execute NEXT bar OPEN. If gap below hard stop
at next open it is filled at that gap price (not stop).
No production config/Redis, exchange POST, or other bot changes.
"""
from __future__ import annotations
import csv,gzip,json
from pathlib import Path
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
from research.regime.long1_six_tier_lock_shadow_v1 import LockState,update
R=Path(__file__).resolve().parents[2]
a=json.loads((R/'research/results/LONG1_NEW_BINANCE_103_ASOF_3PROFILE_REPLAY_20261119.json').read_text())
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 bars=[dict(t=int(x['open_time_ms']),o=float(x['open']),h=float(x['high']),
  l=float(x['low']),c=float(x['close'])) for x in csv.DictReader(f)]
assert len(bars)==8640
TR=ZoneInfo('Europe/Istanbul')
STOP_PRICE_PCT=2.99;HOLD=60;TP=1.25;COST_PP=.24;LEV=3
def roi(price,entry):return (price/entry-1)*100*LEV
def at_ms(ms):return datetime.fromtimestamp(ms/1000,TR).isoformat(timespec='seconds')
def position(e,policy):
 i=int(e['entry_replay_index']);entry=float(e['entry_price'])
 tp_px=entry*(1+TP/(LEV*100));stop_px=entry*(1-STOP_PRICE_PCT/100)
 state=LockState()
 # Next-open fills for signal+close-based trail. Starts with no peak at entry.
 for j in range(i,min(i+HOLD,len(bars))):
  b=bars[j]
  if j>i and bars[j]['t']-bars[j-1]['t']!=60000:raise AssertionError('price gap')
  if b['o']<=stop_px:
   return j,'STOP_GAP_OPEN',roi(b['o'],entry)-COST_PP,state.tier
  if policy!='six_tier_runner_next_open' and b['o']>=tp_px:
   return j,'TP_GAP_OPEN',roi(b['o'],entry)-COST_PP,state.tier
  # stop first on same candle high+low
  if b['l']<=stop_px:
   return j,'SL_FIRST',roi(stop_px,entry)-COST_PP,state.tier
  if policy!='six_tier_runner_next_open' and b['h']>=tp_px:
   return j,'TP_FIRST',roi(tp_px,entry)-COST_PP,state.tier
  if policy!='fixed_tp':
   outcome=update(state,roi(b['c'],entry),b['t']+60000)
   if outcome['state']=='SHADOW_TRAIL_TRIGGER':
    if j+1>=len(bars) or bars[j+1]['t']-b['t']!=60000:
     raise AssertionError('cannot fill following minute')
    exit_price=bars[j+1]['o']
    return j+1,'TRAIL_NEXT_OPEN',roi(exit_price,entry)-COST_PP,state.tier
 j=min(i+HOLD-1,len(bars)-1)
 return j,'TIMEOUT',roi(bars[j]['c'],entry)-COST_PP,state.tier
def summarize(rows):
 return {'opened':len(rows),'outcomes':dict(Counter(x['exit_reason'] for x in rows)),
  'positive':sum(x['net_roi_pp']>0 for x in rows),
  'negative':sum(x['net_roi_pp']<0 for x in rows),
  'roi_pp_sum_not_equity_growth':round(sum(x['net_roi_pp'] for x in rows),3),
  'by_reference':{v:{'count':sum(x['reference_label']==v for x in rows),
                   'roi_pp_sum':round(sum(x['net_roi_pp'] for x in rows if x['reference_label']==v),3)}
     for v in ['LONG_TARGET','LONG_AVOID','UNLABELLED']}}
policies=('fixed_tp','hybrid_six_tier_cap125_next_open','six_tier_runner_next_open')
out={}
for pname,v in a['comparisons'].items():
 entries=sorted([r for r in v['events'] if r['decision']=='RESEARCH_READY'],
  key=lambda x:x['entry_replay_index'])
 results={}
 # FROZEN paired candidates: compare all 32/59/81 same entries
 # even if policy exits differ
 for policy in policies:
  all_entries=[];single=[];book_until=-1
  for e in entries:
   j,reason,net,tier=position(e,policy)
   assert j>=int(e['entry_replay_index'])
   data={'source_model_time_tr':e['model_time_tr'],
      'reference_label':e['reference_label'],
      'entry_time_tr':e['price_entry_time_tr'],'entry_idx':e['entry_replay_index'],
      'exit_idx':j,'exit_time_tr':at_ms(bars[j]['t']),
      'exit_reason':reason,'max_tier_reached':tier+1,
      'net_roi_pp':round(net,4),'hypothetical_only':True}
   all_entries.append(data)
   if e['entry_replay_index']>book_until:
    single.append(data)
    book_until=j
  results[policy]={'paired_all_ready':summarize(all_entries),
                   'single_position':summarize(single),
                   'paired_events':all_entries,'single_events':single}
 assert len({z['source_model_time_tr'] for z in results['fixed_tp']['paired_events']})==len(entries)
 out[pname]=results
report={'schema':'LONG1_103_ASOF_ENTRIES_HYBRID_SIX_TIER_NEXT_OPEN_V1',
 'use_same_asof_preselected_model_entries':True,'no_new_entry_tuning':True,
 'market':'NEARUSDT','decision_data':'closed_m1_before_next_market_open',
 'tier_source':'research.regime.long1_six_tier_lock_shadow_v1',
 'tier_trigger_price':'complete_1m_candle_close',
 'trailing_fill':'following_1m_open_after_trigger',
 'sl_priority_within_bar':True,'risk_on_stop_gap':'fill_at_open',
 'fee_roundtrip_3x_roi_pp_estimate':COST_PP,
 'no_real_partial_m1_entry_sniper_whale':True,
 'no_real_native_stop_liquidation_slippage_funding':True,
 '60m_time_exit':True,
 'potential_fill_order_on_open_same_stop_bar':True,
 'not_real_account_pnl':True,'orders_sent':0,'prod_redis_writes':0,
 'results':out}
path=R/'research/results/LONG1_103_ASOF_HYBRID_SIX_TIER_REPLAY_20261119.json'
path.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'PASS':True,'summaries':{
 p:{policy:{'paired':r['paired_all_ready']['roi_pp_sum_not_equity_growth'],
           'book_n':r['single_position']['opened'],
           'book_roi':r['single_position']['roi_pp_sum_not_equity_growth'],
           'book_exits':r['single_position']['outcomes']}
    for policy,r in policiesmap.items()} for p,policiesmap in out.items()},
 'no_orders':True},sort_keys=True))
