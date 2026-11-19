"""Offline LONG1 shadow profile sweep, isolated from live risk and .env.

Only 11 selected LONG_TARGET historical model events plus single conflict
MODEL event are considered; user labels are RETROSPECTIVE cohort selection,
never permitted as production time-of-day open whitelist.
One-pod position control; no baseline service controls, model prediction,
sniper, whale or entry confirmation authorization simulated.
Fees illustrative 0.08% of roundtrip notional * 3x = 0.24 ROI pts.
1m OHLC stop-first on same-minute TP and SL, no stop/native fill claim.
"""
from __future__ import annotations
from datetime import datetime,timedelta
from bisect import bisect_left
from pathlib import Path
from collections import Counter
import json,requests

ROOT=Path(__file__).resolve().parents[2]
SRC=json.loads((ROOT/'research/results/LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json').read_text())
BASE=json.loads((ROOT/'research/results/LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())
events=sorted((x for x in SRC['events'] if x['research_label'] in ('LONG_TARGET','CONFLICT_NO_TRADE')),key=lambda x:x['model_ts_tr'])
assert len(events)==12 and sum(x['research_label']=='LONG_TARGET' for x in events)==11
assert all(x['model_score']>=x['actual_rolling_threshold'] for x in events)
assert BASE['opened_positions']==10

first=datetime.fromisoformat(events[0]['model_ts_tr']).replace(second=0,microsecond=0)-timedelta(minutes=2)
last=datetime.fromisoformat(events[-1]['model_ts_tr'])+timedelta(hours=5)
def collect():
 t=int(first.timestamp()*1000);end=int(last.timestamp()*1000);rows=[];requests_n=0
 while t<end:
  response=requests.get('https://fapi.binance.com/fapi/v1/klines',
     params={'symbol':'NEARUSDT','interval':'1m','startTime':t,'endTime':end-1,'limit':1000},
     timeout=14,allow_redirects=False)
  response.raise_for_status()
  page=response.json()
  if not isinstance(page,list):raise RuntimeError('invalid price response')
  if not page:break
  rows.extend(page);new=int(page[-1][0])+60000
  assert new>t
  t=new;requests_n+=1;assert requests_n<=8
 return {int(x[6]):{'t':int(x[6]),'open':float(x[1]),'high':float(x[2]),
                    'low':float(x[3]),'close':float(x[4])} for x in rows},requests_n
bars,nreq=collect()
times=sorted(bars)
assert len(times)>4500
TR=events[0]['model_ts_tr'][-6:]
def fmt(ms):
 return datetime.fromtimestamp(ms/1000,datetime.fromisoformat(events[0]['model_ts_tr']).tzinfo).isoformat(timespec='seconds')
def one(e,*,fixed_tp_roi=1.25,delay_full_minutes=0,maximum_minutes=60,stop_price_pct=2.99):
 ts=int(datetime.fromisoformat(e['model_ts_tr']).timestamp()*1000)
 i=bisect_left(times,ts)
 if i>=len(times):return {'status':'CENSORED_REF_MISSING'}
 # the first complete 1m candle CLOSE after model log is the reference.
 # add explicit full candle delays for signal latency sensitivity.
 refi=i+delay_full_minutes
 if refi>=len(times) or not (0<times[i]-ts<=60000):return {'status':'CENSORED_REF_MISSING'}
 entry_bar=bars[times[refi]]
 if times[refi]-ts>60000*(delay_full_minutes+1):return {'status':'CENSORED_REF_GAP'}
 price=entry_bar['close'];entry_t=entry_bar['t']
 high_target=price*(1+fixed_tp_roi/300)
 low_stop=price*(1-stop_price_pct/100)
 close_i=refi+maximum_minutes
 if close_i>=len(times):return {'status':'CENSORED_FWD_MISSING'}
 position=[]
 for j in range(refi+1,close_i+1):
  if times[j]-times[j-1]!=60000:
   return {'status':'CENSORED_FWD_GAP'}
  b=bars[times[j]]
  position.append(b)
  win=b['high']>=high_target;lose=b['low']<=low_stop
  if win and lose:status='SAME_MINUTE_AMBIGUOUS_STOP_FIRST'
  elif lose:status='STOP_FIRST'
  elif win:status='TP_FIRST'
  else:continue
  exit_price=low_stop if status!='TP_FIRST' else high_target
  gross=(exit_price/price-1)*300
  return {'status':status,'entry_time_tr':fmt(entry_t),
   'entry_price':round(price,6),'exit_time_tr':fmt(b['t']),
   'exit_price_price_barrier':round(exit_price,6),
   'holding_minutes':j-refi,'gross_roi_pct':round(gross,4),
   'net_roi_pct_fee_illustration':round(gross-.24,4),
   'hypothetical_exchange_fill':False}
 lastbar=position[-1]
 gross=(lastbar['close']/price-1)*300
 return {'status':'TIMEOUT_60M_CLOSE','entry_time_tr':fmt(entry_t),
    'entry_price':round(price,6),'exit_time_tr':fmt(lastbar['t']),
    'exit_price_price_barrier':round(lastbar['close'],6),
    'holding_minutes':maximum_minutes,'gross_roi_pct':round(gross,4),
    'net_roi_pct_fee_illustration':round(gross-.24,4),
    'hypothetical_exchange_fill':False}
profiles=[
 {'id':'reference_fixed125_1m','tp_roi':1.25,'delay':0},
 {'id':'shadow_fixed095_1m','tp_roi':.95,'delay':0},
 {'id':'shadow_fixed060_1m','tp_roi':.60,'delay':0},
 {'id':'reference_fixed125_delayed_1bar','tp_roi':1.25,'delay':1},
 {'id':'reference_fixed125_delayed_2bar','tp_roi':1.25,'delay':2},
]
comparison={}
for conf in profiles:
 rows=[]
 for e in events:
  res=one(e,fixed_tp_roi=conf['tp_roi'],delay_full_minutes=conf['delay'])
  rows.append(dict(model_time_tr=e['model_ts_tr'],label=e['research_label'],
        rolling_gate_passed=True,**res))
 isolated=[r for r in rows if r['label']=='LONG_TARGET']
 assert len(isolated)==11
 bystatus=Counter(r['status'] for r in isolated)
 assert all(r['status'] in ('TP_FIRST','STOP_FIRST','SAME_MINUTE_AMBIGUOUS_STOP_FIRST','TIMEOUT_60M_CLOSE')
     for r in isolated)
 # one-position shadow amongst wanted only (isolated comparison, does
 # NOT combine with observed historical actual positions).
 busy_until=0;sequential=[];skipped=[]
 for r in isolated:
  ms=int(datetime.fromisoformat(r['entry_time_tr']).timestamp()*1000)
  if ms<=busy_until:
   skipped.append(r['model_time_tr']);continue
  sequential.append(r)
  busy_until=int(datetime.fromisoformat(r['exit_time_tr']).timestamp()*1000)
 comparison[conf['id']]={
   'profile':conf,
   'isolated_11_by_status':dict(bystatus),
   'isolated_net_roi_pp_sum_not_capital_return':round(sum(r['net_roi_pct_fee_illustration'] for r in isolated),4),
   'isolated_net_roi_pp_mean':round(sum(r['net_roi_pct_fee_illustration'] for r in isolated)/11,4),
   'sequential_single_position_opened':len(sequential),
   'sequential_skipped_busy':len(skipped),
   'sequential_net_roi_pp_sum_not_capital_return':round(sum(r['net_roi_pct_fee_illustration'] for r in sequential),4),
   'sequential_statuses':dict(Counter(r['status'] for r in sequential)),
   'skipped_event_times':skipped,'individual_events':rows}
# conflict ONE model event; prohibit in simulated portfolio, even if
# in isolation price goes TP FIRST. Observed actual was already open.
conflict=next(x for x in events if x['research_label']=='CONFLICT_NO_TRADE')
c=one(conflict)
opened_overlap=[x for x in BASE['trades'] if
 datetime.fromisoformat(x['open_tr'])<=datetime.fromisoformat(conflict['model_ts_tr'])<
 datetime.fromisoformat(x['close_tr'])]
assert len(opened_overlap)==1
assert c['status']=='TP_FIRST'
shadow_profile={
 'schema':'LONG1_RESEARCH_ONLY_CANDIDATES_NOT_LIVE_ENV',
 'hard_no_trade_when_common_user_reference_conflicts':True,
 'reference_current_settings':{
   'LONG_ROLLING_MODEL_GATE_ENABLE':1,
   'LONG_ROLLING_MODEL_GATE_QUANTILE':.965,
   'LONG_ROLLING_MODEL_GATE_MIN':.491,
   'MASTER_DROP_WHALE_CONTRA':1,
   'MASTER_WHALE_BOOST_THR':.45,
   'SNIPER_ENTRY_MIN_CANDLE_PROGRESS':.05,
   'SNIPER_ENTRY_MAX_CANDLE_PROGRESS':.60,
   'ENTRY_CONFIRM_MIN_QUALITY':.52,
   'ENTRY_CONFIRM_MIN_BODY_RATIO':.15,
   'ENTRY_CONFIRM_MAX_RETRACE_RATIO':.50,
   'ENTRY_CONFIRM_REJECT_RETRACE_RATIO':.75,
   'LONG_CONTRA_GUARD_ENABLE':1,
   'LONG_CONTEXT_ADAPTIVE_GATE_ENABLE':1,
   'LONG_DYNAMIC_STOP_ENABLE':1,
   'LONG_SCALE_IN_ENABLE':0,
   'MASTER_MAX_POS':1
 },
 'candidate_shadow_not_released':{
   'MASTER_DROP_WHALE_CONTRA':1,
   'MASTER_WHALE_BOOST_THR':.55,
   'SNIPER_ENTRY_MAX_CANDLE_PROGRESS':.75,
   'ENTRY_CONFIRM_MIN_QUALITY':.48,
   'ENTRY_CONFIRM_MAX_RETRACE_RATIO':.60,
   'ENTRY_CONFIRM_REJECT_RETRACE_RATIO':.75
 },
 'unchanged_safety':['LONG_ROLLING_MODEL_GATE_ENABLE',
   'LONG_ROLLING_MODEL_GATE_MIN','LONG_CONTRA_GUARD_ENABLE',
   'LONG_DYNAMIC_STOP_ENABLE','MASTER_MAX_POS',
   'LONG_SCALE_IN_ENABLE','shared_joint_risk_live_guard',
   'native_exchange_stop','fresh_broker_position_snapshot'],
 'parameter_changes_not_validated_by_replay':[
   'MASTER_WHALE_BOOST_THR','SNIPER_ENTRY_MAX_CANDLE_PROGRESS',
   'ENTRY_CONFIRM_MIN_QUALITY','ENTRY_CONFIRM_MAX_RETRACE_RATIO'],
 'production_env_modified':False,'live_authority':False,
 'selection_from_historical_user_labels_is_evaluation_only':True
}
result={
 'schema':'long1_target_conflict_no_lookahead_fixed_barrier_profiles_v1',
 'symbol':'NEARUSDT','leverage':3,
 'wanted_events':11,'conflict_model_events':1,
 'public_candle_requests':nreq,
 'price_1m_complete_candles':len(bars),
 'fees_round_trip_notional_pct_assumed':.08,
 'fees_round_trip_roi_pp_estimate':.24,
 'dynamic_stop_or_native_stop_reproduced':False,
 'real_whale_sniper_entry_gates_reproduced':False,
 'actual_fill_price_or_slippage_reproduced':False,
 'actual_order_pnl_calculated_from_synthetic_entries':False,
 'simulation_lookahead_for_selection':True,
 'simulation_entry_candle_after_model':True,
 'live_order_permission':False,'production_redis_writes':0,
 'profiles':comparison,
 'conflict_isolated_fictitious_long':dict(model_time_tr=conflict['model_ts_tr'],**c),
 'conflict_observed_long_already_open':True,
 'conflict_policy':'HARD_REJECT',
 'conflict_portfolio_new_orders':0,
 'shadow_profile':shadow_profile
}
out=ROOT/'research/results/LONG1_TARGET_CONFLICT_SHADOW_PROFILE_SWEEP_20261119.json'
out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
p=ROOT/'research/staging/long1_research_only_settings_v1.json'
p.parent.mkdir(exist_ok=True,parents=True)
p.write_text(json.dumps(shadow_profile,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'result':'PASS','profiles':{k:{
 'isolated_statuses':v['isolated_11_by_status'],
 'single_position_opened':v['sequential_single_position_opened'],
 'skipped_busy':v['sequential_skipped_busy'],
 'sum_roi_pp':v['sequential_net_roi_pp_sum_not_capital_return']}
 for k,v in comparison.items()},
 'conflict_counterfactual_status':c['status'],
 'conflict_counterfactual_net_roi_pp':c['net_roi_pct_fee_illustration'],
 'conflict_actual_position_already_open':True,
 'live_changes':False},sort_keys=True))
