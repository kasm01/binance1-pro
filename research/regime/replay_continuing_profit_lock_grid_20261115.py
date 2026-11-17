"""Offline, no-order LONG1 trailing ROI grid.

All historical MODEL LONG signals are assumed eligible -- not the actual
execution gate. First fully closed 1m bar after MODEL event is hypothetical
entry; later 1m CLOSE samples are used to arm/update trailing ROI; exiting
on a 1m close is optimistic (no next trade fill/latency). Hard stop if intra-
bar LOW reaches -2.99% entry first; if at once trailing would exit and low
reaches stop, stop wins. No fixed TP or time stop for trailing variants.
No profit-lock in production is changed.
"""
import json,requests,bisect
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import Counter,defaultdict
from statistics import mean,median
ROOT=Path('/home/kasm920/binance1-pro')
events=sorted(json.load(open(ROOT/'research/results/LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json'))['events'],key=lambda z:z['model_ts_tr'])
assert len(events)==103
TR=timezone(timedelta(hours=3));UTC=timezone.utc
start=int(datetime(2026,11,11,8,tzinfo=UTC).timestamp()*1000)
end=min(int(datetime.now(UTC).timestamp()*1000)-120000,
        int(datetime(2026,11,16,0,tzinfo=UTC).timestamp()*1000))
data=[];cur=start
while cur<end:
 r=requests.get('https://fapi.binance.com/fapi/v1/klines',params=dict(symbol='NEARUSDT',interval='1m',startTime=cur,endTime=end-1,limit=1000),timeout=12)
 r.raise_for_status();p=r.json()
 if not isinstance(p,list):raise ValueError('bad kline response')
 if not p:break
 data+=p
 new=int(p[-1][0])+60000
 if new<=cur:raise ValueError('pagination error')
 cur=new
bars=sorted({int(z[6]):{'t':int(z[6]),'high':float(z[2]),'low':float(z[3]),'close':float(z[4])} for z in data if int(z[6])<end}.values(),key=lambda z:z['t'])
ts=[z['t'] for z in bars]
assert len(bars)>5000
LEVERAGE=3.;TARGET=1.25;SLPRICE=-2.99;FEE_ROI=0.24
def stamp(ms):return datetime.fromtimestamp(ms/1000,TR).isoformat()
def run(arm,gb,method='close',direct=False,filter_label=None):
 free_after=start;out=[];skipped=0;noentry=0
 for e in events:
  if filter_label is not None and e['research_label']!=filter_label:continue
  observed=int(datetime.fromisoformat(e['model_ts_tr']).timestamp()*1000)
  if observed<free_after:skipped+=1;continue
  i=bisect.bisect_left(ts,observed)
  if i>=len(ts) or not 0<ts[i]-observed<=60000:
   noentry+=1;continue
  ref=bars[i];en=ref['close']
  if ref['t']<free_after:skipped+=1;continue
  peak=0.0;armed=False;prev=ref;hit=None;exit_roi=None;exitbar=None;first_arm_t=None
  for b in bars[i+1:]:
   if b['t']-prev['t']!=60000:
    hit='CENSORED_GAP';exitbar=prev;break
   prev=b
   gross_close=(b['close']/en-1)*100*LEVERAGE
   gross_high=(b['high']/en-1)*100*LEVERAGE
   gross_low=(b['low']/en-1)*100*LEVERAGE
   # Exact 1m high-low order unknown; for hard SL always adverse first
   if gross_low<=SLPRICE*LEVERAGE:
    hit='SL_FIRST';exit_roi=SLPRICE*LEVERAGE;exitbar=b;break
   if direct:
    if gross_high>=TARGET:
     hit='FIXED_TP';exit_roi=TARGET;exitbar=b;break
   elif method=='close':
    if gross_close>=arm and not armed:
     armed=True;first_arm_t=b['t']
    if armed:
     peak=max(peak,gross_close)
     # after arming, trailing only if a later candle closes below watermark minus giveback
     if b['t']>first_arm_t and gross_close<=peak-gb:
      hit='TRAIL_CLOSE';exit_roi=gross_close;exitbar=b;break
   else:raise ValueError(method)
  if hit is None:
   hit='OPEN_END';exitbar=bars[-1]
  realized=exit_roi is not None
  item=dict(signal_time_tr=e['model_ts_tr'],reference_label=e['research_label'],
    status=hit,entry_t=stamp(ref['t']),exit_t=stamp(exitbar['t']) if realized else None,
    minutes_held=round((exitbar['t']-ref['t'])/60000,2),
    arm_reached=armed,peak_close_roi=round(peak,4),
    first_arm_t=stamp(first_arm_t) if first_arm_t else None,
    gross_roi_pct=round(exit_roi,4) if realized else None,
    estimated_net_roi_pct=round(exit_roi-FEE_ROI,4) if realized else None)
  out.append(item)
  if realized:free_after=exitbar['t']
  else:break
 completed=[x for x in out if x['estimated_net_roi_pct'] is not None]
 pnl=[x['estimated_net_roi_pct'] for x in completed]
 states=Counter(x['status'] for x in out)
 return dict(arm_roi_pct=arm,giveback_roi_pp=gb,method=method,
   direct_fixed_tp=direct,total=len(out),skipped_busy=skipped,noentry=noentry,
   states=dict(states),positive_closed=sum(v>0 for v in pnl),
   negative_closed=sum(v<=0 for v in pnl),
   closed_n=len(completed),roi_mean=round(mean(pnl),4) if pnl else None,
   roi_sum_not_equity_return=round(sum(pnl),4),
   win_rate=round(sum(v>0 for v in pnl)/len(pnl),4) if pnl else None,
   median_holding_min=round(median(x['minutes_held'] for x in completed),2) if completed else None,
   still_open=len(out)>len(completed),results=out)
baseline=run(None,None,direct=True)
results={}
for arm in (.50,.65,.75,1.0):
 for gb in (.10,.15,.20,.25,.35):
  results[f'arm{arm:.2f}_giveback{gb:.2f}']=run(arm,gb)
print('BASELINE','n',baseline['total'],'pos',baseline['positive_closed'],'neg',baseline['negative_closed'],'mean_roi',baseline['roi_mean'],'states',baseline['states'])
for k,v in results.items():
 print('GRID',k,'n',v['total'],'pos',v['positive_closed'],'neg',v['negative_closed'],'mean_roi',v['roi_mean'],'armed',sum(z['arm_reached'] for z in v['results']),'states',v['states'])
p=ROOT/'research/results/LONG1_CONTINUING_PROFIT_LOCK_GRID_20261115.json'
p.write_text(json.dumps(dict(schema='long1_model_trailing_close_grid_v1',production_changes=False,
  no_order_authority=True,source_events=103,candle_count=len(bars),
  start_tr=stamp(bars[0]['t']),end_tr=stamp(bars[-1]['t']),
  scenario='hypothetical model executable, no fixed TP, trail on closed 1m ROI, hard SL from 1m low first',
  caveats='Close-based trailing does not reflect live fill after bar close, mark price, stop confirmations, entry delay, fees/BNB, funding, slippage or intra-minute peaks. Price stop alone; no dynamic stop or stall. Clock labels evaluation only.',
  fee_assumed_roundtrip_roi_pp=FEE_ROI,
  fixed_baseline=baseline,profiles=results),ensure_ascii=False,indent=2)+'\n')
print('SAVED',p)
