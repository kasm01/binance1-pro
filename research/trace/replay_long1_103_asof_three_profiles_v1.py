"""LONG1 public Binance archive counterfactual. No future input at decision.

Uses 103 MODEL events, 8640 fully closed m1 bars, event-agnostic entry rules.
Historical user windows only for AFTER-decision evaluation and mandated
conflict no-trade. Not actual executor/whale/partial-m1 confirmation.
Trade at NEXT 1m open after approved close; OHLC stop-first, 60m max.
Single-position simulated book, parallel collision with actual broker
positions as separate sensitivity, no exchange access, no Redis writes.
"""
from __future__ import annotations
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from bisect import bisect_left,bisect_right
from collections import Counter,defaultdict
import csv,gzip,json,math
R=Path(__file__).resolve().parents[2]
BASE=R/'research/results'
TR=ZoneInfo('Europe/Istanbul')
source=json.loads((BASE/'LONG1_BINANCE_ARCHIVE_ASOF_FLOW_103_MODEL_EVENTS_20261119.json').read_text())['events']
first_hit=json.loads((BASE/'LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json').read_text())['events']
modelmap={x['model_ts_tr']:x for x in first_hit}
assert len(source)==len(modelmap)==103
reference=json.loads((R/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json').read_text())
real=json.loads((BASE/'LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 rows=list(csv.DictReader(f))
assert len(rows)==8640
bars=[dict(t=int(x['open_time_ms']),o=float(x['open']),h=float(x['high']),l=float(x['low']),
 c=float(x['close']),quote=float(x['quote_volume']),
 buy=float(x['taker_buy_quote_volume'])) for x in rows]
opens=[x['t'] for x in bars]
closes=[x+60000 for x in opens]
assert all(opens[k]==opens[k-1]+60000 for k in range(1,len(opens)))
intervals=[(datetime.fromisoformat(x['start_tr']),datetime.fromisoformat(x['end_tr']),x['user_label'])
  for x in reference['user_intervals']]
real_busy=[(datetime.fromisoformat(x['open_tr']),datetime.fromisoformat(x['close_tr'])) for x in real['trades']]
def label(dt):
 flags={name for lo,hi,name in intervals if lo<=dt<hi}
 if len(flags)>1:return 'CONFLICT_NO_TRADE'
 if 'LONG_WANTED' in flags:return 'LONG_TARGET'
 if 'LONG_AVOID' in flags:return 'LONG_AVOID'
 return 'UNLABELLED'
def flow(a,b):
 seq=bars[a:b+1]
 q=sum(x['quote'] for x in seq);buy=sum(x['buy'] for x in seq)
 return (2*buy/q-1) if q>0 else 0
def ret(i,n):
 return 100*(bars[i]['c']/bars[i-n]['c']-1)
def metrics(i):
 b=bars[i];span=max(0,b['h']-b['l'])
 body=max(0,b['c']-b['o'])/span if span>0 else 0
 retr=(b['h']-b['c'])/span if span>0 else 1
 return dict(body=body,retrace=retr,
   flow1=flow(i,i),flow3=flow(i-2,i),flow5=flow(i-4,i),
   flow15=flow(i-14,i),r3=ret(i,3),r5=ret(i,5),
   c=b['c'],h=b['h'],l=b['l'])
profiles={
 'strict_recovery':dict(n_rechecks=5,body=.22,retrace=.35,flow1=.03,
        delta_flow3=.08,delta_r3=.10,require_price3_positive=True,
        require_flow3_positive=True,require_price5_positive=False),
 'balanced_pending':dict(n_rechecks=5,body=.15,retrace=.50,flow1=-.03,
        delta_flow3=.04,delta_r3=.05,require_price3_positive=False,
        require_flow3_positive=False,require_price5_positive=False),
 'cautious_relaxation':dict(n_rechecks=5,body=.10,retrace=.60,flow1=-.15,
        delta_flow3=-.03,delta_r3=-.05,require_price3_positive=False,
        require_flow3_positive=False,require_price5_positive=False),
}
# Every parameter independent of user retrospective label.
def qualify(m,origin,config):
 issues=[]
 if m['body']<config['body']:issues.append('body')
 if m['retrace']>config['retrace']:issues.append('retrace')
 if m['flow1']<config['flow1']:issues.append('flow1')
 if m['flow3']<origin['flow3']+config['delta_flow3']:issues.append('flow_recovery')
 if m['r3']<origin['r3']+config['delta_r3']:issues.append('momentum_recovery')
 if config['require_price3_positive'] and m['r3']<=0:issues.append('r3_not_positive')
 if config['require_flow3_positive'] and m['flow3']<=0:issues.append('flow3_not_positive')
 if config['require_price5_positive'] and m['r5']<=0:issues.append('r5_not_positive')
 return issues
def exit_path(entryidx,entryprice,tp_roi=1.25,sl_price_pct=2.99,max_minutes=60):
 # Earliest market fill NEXT bar OPEN, so its whole OHLC can follow fill.
 # If opening minute BOTH barriers touch then choose SL first.
 tp=entryprice*(1+tp_roi/300)
 sl=entryprice*(1-sl_price_pct/100)
 for j in range(entryidx,min(entryidx+max_minutes,len(bars))):
  b=bars[j]
  hit_tp=b['h']>=tp
  hit_sl=b['l']<=sl
  if hit_tp or hit_sl:
   status='SAME_BAR_STOP_FIRST' if hit_tp and hit_sl else 'SL_FIRST' if hit_sl else 'TP_FIRST'
   exit_price=sl if hit_sl else tp
   gross=(exit_price/entryprice-1)*300
   return status,j,round(gross,4),round(gross-.24,4)
 j=min(entryidx+max_minutes-1,len(bars)-1)
 gross=100*3*(bars[j]['c']/entryprice-1)
 return 'TIMEOUT',j,round(gross,4),round(gross-.24,4)

scenarios={}
for pname,config in profiles.items():
 result=[]
 for e in sorted(source,key=lambda x:x['model_event_tr']):
  t=datetime.fromisoformat(e['model_event_tr'])
  ts=int(t.timestamp()*1000)
  origin_index=bisect_right(closes,ts)-1
  assert origin_index>=60
  # start from NEXT fully closed bar after the original model,
  # and recheck up to 5 completed minutes with no intrabar sneak.
  origin=metrics(origin_index)
  qualifying=[]
  reasons=Counter()
  for step in range(1,config['n_rechecks']+1):
   i=origin_index+step
   assert i+62<len(bars)
   m=metrics(i)
   issues=qualify(m,origin,config)
   if issues:
    reasons.update(issues);continue
   qualifying.append((i,m))
   break
  record={
   'model_time_tr':e['model_event_tr'],'model_close_id':e['model_close_id'],
   'reference_label':e['user_reference'],
   'rolling_score_passed':modelmap[e['model_event_tr']]['model_score']>=modelmap[e['model_event_tr']]['actual_rolling_threshold'],
   'revalidation_recheck_max':config['n_rechecks'],
   'source_preclosed_1m_only':True,
   'model_to_entry_trace_observed':False,
   'exact_partial_m1_entry_reproduced':False,
   'pending_reason_counts':dict(reasons),
  }
  if label(t)=='CONFLICT_NO_TRADE':
   # Explicit original-time no-trade: do not open later by revalidating a
   # signal whose originating user reference is contradictory.
   record.update(decision='REJECT_CONFLICT_ORIGIN',simulated_order=False)
  elif not record['rolling_score_passed']:
   record.update(decision='MODEL_GATE_REJECT',simulated_order=False)
  elif not qualifying:
   record.update(decision='EXPIRED_NO_RECOVERY',simulated_order=False)
  else:
   i,m=qualifying[0]
   dt=datetime.fromtimestamp(closes[i]/1000,TR)
   # next bar open is after fully known decision candle
   enter_index=i+1
   entrydt=datetime.fromtimestamp(opens[enter_index]/1000,TR)
   assert entrydt==dt
   if label(dt)=='CONFLICT_NO_TRADE' or label(entrydt)=='CONFLICT_NO_TRADE':
    record.update(decision='REJECT_CONFLICT',simulated_order=False,
                  opportunity_detected=True,decision_time_tr=dt.isoformat())
   else:
    status,exit_idx,gross,net=exit_path(enter_index,bars[enter_index]['o'])
    record.update(decision='RESEARCH_READY',simulated_order=False,
      opportunity_detected=True,decision_time_tr=dt.isoformat(),
      price_entry_time_tr=entrydt.isoformat(),entry_price=bars[enter_index]['o'],
      entry_replay_index=enter_index,exit_replay_index=exit_idx,
      exit_time_tr=datetime.fromtimestamp(opens[exit_idx]/1000,TR).isoformat(),
      exit_status=status,gross_3x_roi_pct=gross,net_3x_roi_pp_illustrative=net,
      entry_context={k:round(v,6) for k,v in m.items()})
  result.append(record)
 assert len(result)==103
 # portfolio with only THIS profile's synthetic positions
 book_until=-1;book=[]
 for r in result:
  if r['decision']!='RESEARCH_READY':continue
  idx=r['entry_replay_index']
  if idx<=book_until:
   r['portfolio_decision']='REJECT_SIMULATED_POSITION_BUSY'
   continue
  r['portfolio_decision']='SHADOW_OPEN'
  r['simulated_order']=True
  book_until=r['exit_replay_index']
  book.append(r)
 # sensitivity: actual historical broker occupancy for same periods,
 # WITHOUT merging synthetic book into actual book or claiming reality.
 for r in result:
  if r['decision']!='RESEARCH_READY':continue
  dt=datetime.fromisoformat(r['price_entry_time_tr'])
  r['overlaps_actual_broker_long']=any(lo<=dt<hi for lo,hi in real_busy)
 # static labels only for diagnostics, never signal filters except conflict
 bycohort={}
 for cohort in ('LONG_TARGET','LONG_AVOID','UNLABELLED','CONFLICT_NO_TRADE'):
  subset=[r for r in result if r['reference_label']==cohort]
  live=[r for r in book if r['reference_label']==cohort]
  bycohort[cohort]=dict(models=len(subset),
    ready=sum(r['decision']=='RESEARCH_READY' for r in subset),
    expired=sum(r['decision']=='EXPIRED_NO_RECOVERY' for r in subset),
    conflict_rejected=sum(r['decision'].startswith('REJECT_CONFLICT') for r in subset),
    portfolio_open=len(live),portfolio_outcomes=dict(Counter(r['exit_status'] for r in live)),
    net_3x_roi_points_sum=round(sum(r['net_3x_roi_pp_illustrative'] for r in live),3),
    total_entry_candidate_overlaps_real_long=sum(r.get('overlaps_actual_broker_long',False) for r in subset),
  )
 scenarios[pname]=dict(profile=config,by_label=bycohort,models=103,
     decisions=dict(Counter(r['decision'] for r in result)),
     all_ready=sum(r['decision']=='RESEARCH_READY' for r in result),
     single_position_shadow_opens=len(book),
     single_position_book_outcomes=dict(Counter(r['exit_status'] for r in book)),
     single_position_net_roi_pp_sum=round(sum(r['net_3x_roi_pp_illustrative'] for r in book),3),
     all_ready_overlaps_actual_broker_long=sum(r.get('overlaps_actual_broker_long',False) for r in result),
     events=result)
out={
 'schema':'long1_103_model_new_binance_archive_3_profile_asof_shadow_v1',
 'symbol':'NEARUSDT','date_period_tr':'2026-11-11_to_2026-11-15',
 'backfilled_archive_kline_minutes':8640,'model_events':103,
 'strategy_uses_hindsight_user_label_for_selection':False,
 'user_label_only_used_for_retrospective_conflict_veto_and_reporting':True,
 'real_entry_sniper_whale_and_pending_reproduced':False,
 'one_minute_partial_candle_observations_recovered':False,
 'simulated_price_entry_only_next_bar_open':True,
 'lookahead_data_used_in_entry_decision':False,
 'fees_roundtrip_notional_pct_estimate':.08,
 'fees_3x_roi_points_estimate':.24,
 'dynamic_profit_lock_native_stop_liquidation_funding_modeled':False,
 'all_hypothetical_orders_only':True,
 'production_config_modified':False,'production_redis_writes':0,'real_exchange_orders':0,
 'comparisons':scenarios,
}
dest=BASE/'LONG1_NEW_BINANCE_103_ASOF_3PROFILE_REPLAY_20261119.json'
dest.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'PASS':True,'n_model':103,'profiles':{
 n:dict(ready=v['all_ready'],opens=v['single_position_shadow_opens'],
 outcomes=v['single_position_book_outcomes'],
 net_roi_pp_sum=v['single_position_net_roi_pp_sum'],
 target=v['by_label']['LONG_TARGET'],
 avoid=v['by_label']['LONG_AVOID'],
 conflict=v['by_label']['CONFLICT_NO_TRADE'],
 over_actual=v['all_ready_overlaps_actual_broker_long'])
 for n,v in scenarios.items()},'real_orders':0},sort_keys=True))
