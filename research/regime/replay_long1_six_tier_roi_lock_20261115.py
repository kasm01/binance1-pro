"""Read-only 6-tier ROI ratchet grid on 35 SAME historical MODEL entry refs.

Two policy variants:
(A) full runner: no fixed TP, arm six tiers, trailing close or following 1m
open, plus price SL at -2.99% from entry.
(B) hybrid cap: same ratchet, plus *existing* fixed +1.25 gross ROI TP.
Both avoid time exit. Original 35 reference episodes are held fixed to allow
paired comparisons, do not represent production entry selection.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from bisect import bisect_left
from collections import Counter
from statistics import mean,median
import requests,json,csv
from research.regime.long1_six_tier_lock_shadow_v1 import LockState,update,TIERS
ROOT=Path('/home/kasm920/binance1-pro')
paired=json.load(open(ROOT/'research/results/LONG1_PAIRED_35_FIXED_VS_TRAIL_065_015_20261115.json'))['pairs']
assert len(paired)==35
TR=timezone(timedelta(hours=3));UTC=timezone.utc
start=int(datetime(2026,11,11,8,tzinfo=UTC).timestamp()*1000)
end=int(datetime(2026,11,16,0,tzinfo=UTC).timestamp()*1000)
raw=[];cursor=start;requests_n=0
while cursor<end:
 response=requests.get('https://fapi.binance.com/fapi/v1/klines',
  params=dict(symbol='NEARUSDT',interval='1m',startTime=cursor,endTime=end-1,limit=1000),timeout=14)
 response.raise_for_status();page=response.json()
 if not isinstance(page,list):raise ValueError('bad data')
 if not page:break
 raw+=page;next_cursor=int(page[-1][0])+60000
 if next_cursor<=cursor:raise ValueError('pagination')
 cursor=next_cursor;requests_n+=1
 if requests_n>9:raise ValueError('excessive calls')
bars=sorted({int(x[6]):dict(t=int(x[6]),o=float(x[1]),h=float(x[2]),l=float(x[3]),c=float(x[4]))
 for x in raw}.values(),key=lambda z:z['t'])
ts=[z['t'] for z in bars]
assert len(bars)>6000
LEVERAGE=3;STOP_ROI=-8.97;TP_ROI=1.25;FEE_ROI_PP=.24
def roi(price,entry):return (price/entry-1)*100*LEVERAGE
def tr(ms):return datetime.fromtimestamp(ms/1000,TR).isoformat()
def simulate(model_ts,cap_tp=False,fill='close'):
 ms=int(datetime.fromisoformat(model_ts).timestamp()*1000)
 idx=bisect_left(ts,ms)
 assert 0<ts[idx]-ms<=60000
 ref=bars[idx];entry=ref['c'];state=LockState()
 previous=ref;status='OPEN_END';exit_px=None;exit_ms=None;decision_ms=None;at_max_tier=0
 for j in range(idx+1,len(bars)):
  b=bars[j]
  if b['t']-previous['t']!=60000:status='CENSORED_GAP';break
  previous=b
  # stop first where 1m ordering is ambiguous
  if roi(b['l'],entry)<=STOP_ROI:
   status='STOP';exit_px=entry*(1+STOP_ROI/(LEVERAGE*100));exit_ms=b['t'];break
  if cap_tp and roi(b['h'],entry)>=TP_ROI:
   status='DIRECT_TP';exit_px=entry*(1+TP_ROI/(LEVERAGE*100));exit_ms=b['t'];break
  response=update(state,roi(b['c'],entry),b['t'])
  at_max_tier=max(at_max_tier,response['active_tier'])
  if response['state']=='SHADOW_TRAIL_TRIGGER':
   decision_ms=b['t']
   if fill=='close':
    status='TRAIL_CLOSE';exit_px=b['c'];exit_ms=b['t']
   elif fill=='next_open':
    if j+1>=len(bars):status='CENSORED_NEXT_OPEN';break
    following=bars[j+1]
    if following['t']-b['t']!=60000:status='CENSORED_NEXT_GAP';break
    status='TRAIL_NEXT_OPEN';exit_px=following['o'];exit_ms=following['t']
   else:raise ValueError(fill)
   break
 if exit_px is None:
  return dict(signal_time_tr=model_ts,status=status,tier=at_max_tier,
    reached_tiers=at_max_tier,exit_time_tr=None,net_roi=None,gross_roi=None)
 gross=roi(exit_px,entry);net=gross-FEE_ROI_PP
 return dict(signal_time_tr=model_ts,status=status,
  entry_time_tr=tr(ref['t']),exit_time_tr=tr(exit_ms),decision_time_tr=tr(decision_ms) if decision_ms else None,
  entry_price=entry,exit_assumed_price=exit_px,
  peak_roi_close=round(state.peak,4),locked_floor_roi=round(state.floor,4) if state.floor is not None else None,
  reached_tiers=at_max_tier,
  holding_minutes=round((exit_ms-ref['t'])/60000,2),
  gross_roi=round(gross,4),net_roi=round(net,4),
  assumed_fill_type=fill,actual_exchange_fill=False)
def summarize(results):
 completed=[z for z in results if z['net_roi'] is not None]
 vals=[z['net_roi'] for z in completed]
 return dict(total=len(results),complete=len(completed),win=sum(v>0 for v in vals),
    nonpositive=sum(v<=0 for v in vals),stops=sum(z['status']=='STOP' for z in results),
    exits=dict(Counter(z['status'] for z in results)),
    mean_net_roi=round(mean(vals),4) if vals else None,
    median_net_roi=round(median(vals),4) if vals else None,
    sum_net_roi_not_account_return=round(sum(vals),4),
    reached_tier_counts=dict(Counter(z['reached_tiers'] for z in results)),
    max_net_roi=round(max(vals),4) if vals else None)
policies={
'baseline_fixed':[dict(signal_time_tr=x['signal_time_tr'],
 status=x['fixed']['status'],net_roi=round(x['fixed']['roi_net'],4),
 reached_tiers=0) for x in paired],
'six_tier_runner_close':[simulate(x['signal_time_tr'],cap_tp=False,fill='close') for x in paired],
'six_tier_runner_next_open':[simulate(x['signal_time_tr'],cap_tp=False,fill='next_open') for x in paired],
'six_tier_with_fixed125_close':[simulate(x['signal_time_tr'],cap_tp=True,fill='close') for x in paired],
'six_tier_with_fixed125_next_open':[simulate(x['signal_time_tr'],cap_tp=True,fill='next_open') for x in paired],
}
summary={k:summarize(v) for k,v in policies.items()}
for key,z in summary.items():
 print('SUMMARY',key,z)
print('EIGHT_BASELINE_STOP_SIGNAL_COMPARISON')
ref=dict((x['signal_time_tr'],x) for x in paired)
for s in paired:
 if s['fixed']['status']=='SL_FIRST':
  when=s['signal_time_tr']
  a=next(z for z in policies['six_tier_runner_close'] if z['signal_time_tr']==when)
  b=next(z for z in policies['six_tier_with_fixed125_close'] if z['signal_time_tr']==when)
  print('STOP_CASE',when,'base',s['fixed']['roi_net'],
        'runner',a['status'],a['net_roi'],a['reached_tiers'],
        'cap',b['status'],b['net_roi'],b['reached_tiers'])
out=ROOT/'research/results/LONG1_SIX_TIER_ROI_RATCHET_PAIRED_35_20261115.json'
out.write_text(json.dumps(dict(schema='long1_six_tier_roi_paired35_v1',
  orders_authorized=False,production_changed=False,
  start_tr=tr(bars[0]['t']),last_tr=tr(bars[-1]['t']),
  market_symbol='NEARUSDT',candle_count=len(bars),requests_n=requests_n,
  tiers=[dict(arm_gross_roi_pct=a,giveback_roi_percentage_points=b) for a,b in TIERS],
  no_time_exit=True,one_position_assumed_in_baseline_selection_only=True,
  same_signal_same_assumed_entry_in_all_paired_policies=True,
  fees_assumption_roi_pp=FEE_ROI_PP,hard_price_stop_pct=-2.99,
  note='Research model-based entries, NOT actual orders; all risk/entry gates ignored. Paired entries; real one-coin-one-position sequence must be run separately. Unknown tick path; 1m stop first; next_open fill heuristic, not guaranteed. Real native stop/dynamic 30s stop ignored.',
  summaries=summary,policies=policies),ensure_ascii=False,indent=2)+'\n')
print('SAVED',out)
