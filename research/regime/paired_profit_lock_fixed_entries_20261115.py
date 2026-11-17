"""Read-only paired 35 exact model-event entries, fixed TP vs ROI trailing.

Each trade independently simulates SAME historical signal and SAME hypothetical
entry price; no subsequent-signal/portfolio selection allowed in paired test.
Single-symbol occupancy is deliberately NOT modeled here because it changes
which starts are available and invalidates pairing. Portfolio simulation was
reported separately. All model signals are assumed executable (false in live).

Entry: close of first 1m candle completely closed AFTER model log observation.
Fixed: first 1m HIGH touches TP +1.25% gross ROI, or LOW hits entry -2.99%;
same minute both -> STOP first. Fixed exits at TP barrier price on touch.
Trailing: arm at >=0.65% gross ROI 1m CLOSE, track close peak, exit on
subsequent 1m CLOSE <= peak - giveback, or hard stop on intrabar LOW.
Exit alternatives:
* signal_close: optimistically fill at 1m CLOSE triggering trailing exit
* next_open: fill at NEXT 1m OPEN (and respect next candle opening gap).
No funding, dynamic/30s stop, exchange mark price, spread, tick rounding, exact
commission; static 0.04% notional each side for illustrative 3x ROI cost.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import Counter,defaultdict
from statistics import mean,median
from bisect import bisect_left
import requests,json,csv
ROOT=Path('/home/kasm920/binance1-pro')
old=json.load(open(ROOT/'research/results/LONG1_MODEL_LONG_NO_TIME_EXIT_FIRST_HIT_20261111_15.json'))
base=old['result']['ALL_MODEL_LONGS']['hypothetical_trades']
assert len(base)==35
TR=timezone(timedelta(hours=3));UTC=timezone.utc
first=int(datetime(2026,11,11,8,0,tzinfo=UTC).timestamp()*1000)
last=min(int(datetime.now(UTC).timestamp()*1000)-120000,
         int(datetime(2026,11,16,0,tzinfo=UTC).timestamp()*1000))
raw=[];cursor=first;calls=0
while cursor<last:
 res=requests.get('https://fapi.binance.com/fapi/v1/klines',
 params=dict(symbol='NEARUSDT',interval='1m',startTime=cursor,endTime=last-1,limit=1000),timeout=12)
 res.raise_for_status()
 page=res.json()
 if not isinstance(page,list):raise ValueError(f'bad API {str(page)[:80]}')
 if not page:break
 raw.extend(page)
 nxt=int(page[-1][0])+60000
 if nxt<=cursor:raise RuntimeError('non advancing request')
 cursor=nxt;calls+=1
 if calls>9:raise RuntimeError('unexpected excessive calls')
bars=sorted({int(b[6]):dict(t=int(b[6]),o=float(b[1]),c=float(b[4]),
 h=float(b[2]),l=float(b[3])) for b in raw if int(b[6])<last}.values(),key=lambda x:x['t'])
times=[b['t'] for b in bars]
FEE=0.24;L=3.;TP=1.25;STOP_PRICE=2.99
def stamp(x):return datetime.fromtimestamp(x/1000,TR).isoformat()
def calc_roi(price,entry):return (price/entry-1)*100*L
def simulate(z,arm,gb,mode):
 observed=int(datetime.fromisoformat(z['signal_time_tr']).timestamp()*1000)
 idx=bisect_left(times,observed)
 if idx>=len(bars) or not 0<bars[idx]['t']-observed<=60000:
  return dict(status='CENSORED_NO_ENTRY')
 ref=bars[idx]
 entry=ref['c']
 assert abs(entry-z['ref_entry_price'])<1e-9,(entry,z['ref_entry_price'])
 peak_roi=0.;armed=False;first_arm=None
 lastbar=ref
 for i in range(idx+1,len(bars)):
  b=bars[i]
  if b['t']-lastbar['t']!=60000:
   return dict(status='CENSORED_GAP',exit_time=None)
  lastbar=b
  roi_low=calc_roi(b['l'],entry)
  if roi_low<=-STOP_PRICE*L:
   return dict(status='SL_FIRST',roi_gross=-STOP_PRICE*L,
      roi_net=-STOP_PRICE*L-FEE,exit_t=stamp(b['t']),
      held_minutes=(b['t']-ref['t'])/60000,ever_armed=armed,
      peak_close_roi=peak_roi,exit_mode=mode)
  if mode=='fixed':
   if calc_roi(b['h'],entry)>=TP:
    return dict(status='FIXED_TP',roi_gross=TP,roi_net=TP-FEE,
      exit_t=stamp(b['t']),held_minutes=(b['t']-ref['t'])/60000,
      ever_armed=False,peak_close_roi=0,exit_mode=mode)
  else:
   close_roi=calc_roi(b['c'],entry)
   if close_roi>=arm and not armed:
    armed=True;first_arm=b['t']
   if armed:
    peak_roi=max(peak_roi,close_roi)
    if b['t']>first_arm and close_roi<=peak_roi-gb:
     if mode=='trail_next_open':
      if i+1>=len(bars):return dict(status='CENSORED_NO_NEXT_OPEN')
      nextbar=bars[i+1]
      if nextbar['t']-b['t']!=60000:return dict(status='CENSORED_GAP_NEXT_OPEN')
      exit_roi=calc_roi(nextbar['o'],entry)
      t_exit=nextbar['t']
     elif mode=='trail_close':
      exit_roi=close_roi;t_exit=b['t']
     else:raise ValueError(mode)
     # If the next open already gaps beyond stop, loss can exceed stop.
     return dict(status='TRAIL',roi_gross=exit_roi,roi_net=exit_roi-FEE,
      exit_t=stamp(t_exit),held_minutes=(t_exit-ref['t'])/60000,
      ever_armed=True,peak_close_roi=peak_roi,exit_mode=mode,
      trigger_close_roi=close_roi)
 return dict(status='OPEN_DATA_END',last_mark_roi=calc_roi(bars[-1]['c'],entry),
  ever_armed=armed,peak_close_roi=peak_roi)
pairs=[]
for z in base:
 f=simulate(z,.65,.15,'fixed')
 t=simulate(z,.65,.15,'trail_close')
 n=simulate(z,.65,.15,'trail_next_open')
 record=dict(signal_time_tr=z['signal_time_tr'],label=z['reference_label'],
  fixed=f,trailing_close=t,trailing_next_open=n)
 pairs.append(record)
def summarized(key):
 done=[z for z in pairs if z[key].get('roi_net') is not None]
 result=[z[key]['roi_net'] for z in done]
 return dict(n=len(done),status_counts=dict(Counter(z[key]['status'] for z in pairs)),
   wins=sum(x>0 for x in result),losses=sum(x<=0 for x in result),
   avg_net_roi=round(mean(result),4) if result else None,
   sum_roi_not_account_return=round(sum(result),4),
   median_minutes=round(median(z[key]['held_minutes'] for z in done),2) if done else None,
   arm_reached=sum(z[key].get('ever_armed') is True for z in pairs))
report=dict(schema='long1_roi_lock_paired_35_v1',research_only=True,
 no_order_authority=True,signal_count=103,paired_fixed_entry_count=len(pairs),
 dataset_end_tr=stamp(bars[-1]['t']),binance_gets=calls,
 fixed_tp_gross_roi_pct=TP,arm_gross_roi_pct=.65,giveback_roi_percentage_points=.15,
 price_stop_pct=STOP_PRICE,leverage=L,
 illustrative_taker_fee_0p04pct_per_side=True,fee_margin_roi_pp=FEE,
 same_signal_and_same_reference_entry=True,independent_episode_pairing=True,
 caveats='Portfolio occupancy differs by exit. Next-open trailing still idealized and does not model live order latency, mark-price native stop, dynamic 30sec stop, pending, sniper, spread, funding or varying taker fees.',
 summaries={k:summarized(k) for k in ('fixed','trailing_close','trailing_next_open')},
 pairs=pairs)
out=ROOT/'research/results/LONG1_PAIRED_35_FIXED_VS_TRAIL_065_015_20261115.json'
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
with (ROOT/'research/results/LONG1_PAIRED_35_FIXED_VS_TRAIL_065_015_20261115.csv').open('w',newline='') as fh:
 writer=csv.writer(fh);writer.writerow(['model_ts_tr','user_label','fixed_status','fixed_net_roi_pct','trail_close_status','trail_close_net_roi_pct','trail_next_open_status','trail_next_open_net_roi_pct','fixed_holding_min','trail_holding_min'])
 for z in pairs:
  writer.writerow([z['signal_time_tr'],z['label'],z['fixed']['status'],z['fixed'].get('roi_net'),z['trailing_close']['status'],z['trailing_close'].get('roi_net'),z['trailing_next_open']['status'],z['trailing_next_open'].get('roi_net'),z['fixed'].get('held_minutes'),z['trailing_close'].get('held_minutes')])
for key,s in report['summaries'].items():print(key,s)
for z in pairs:
 if z['fixed']['status']=='SL_FIRST':
  print('PRIOR_STOP',z['signal_time_tr'], 'fixed',z['fixed']['roi_net'],
   'trail_close',z['trailing_close'].get('roi_net'),z['trailing_close']['status'],
   'next_open',z['trailing_next_open'].get('roi_net'),z['trailing_next_open']['status'])
print('SAVED',out,'CANDLES',len(bars),'CALLS',calls)
