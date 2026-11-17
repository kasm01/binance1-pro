"""Research-only one-position LONG model-signal TP/SL first-hit, NO time exit.

Every MODEL LONG event is HYPOTHETICALLY executable (not true). Enter at the
close of first fully closed 1m candle after signal observed. From the NEXT
1m candle, exit at whichever touches first: +0.41667% price TP (3x => gross
ROI +1.25%) or -2.99% price SL. No time exit, no trailing/dynamic stop, no
interest in user labels for execution. End-of-data -> STILL_OPEN/CENSORED.
No forced close of open positions; unrealized mark from last fully closed 1m
is shown separately. Use single NEARUSDT position concurrently.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from bisect import bisect_left
from collections import Counter
from statistics import mean,median
import json,requests,hashlib
ROOT=Path('/home/kasm920/binance1-pro')
source=ROOT/'research/results/LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json'
src=json.loads(source.read_text())
events=sorted(src['events'],key=lambda x:x['model_ts_tr'])
assert len(events)==103
TZ=timezone(timedelta(hours=3)); UTC=timezone.utc
start_ms=int(datetime(2026,11,11,8,tzinfo=UTC).timestamp()*1000)
# Request only already-completed candles as of remote VM's current UTC time.
now=datetime.now(UTC)
end_ms=min(int(now.timestamp()*1000)-120000,
  int(datetime(2026,11,16,0,tzinfo=UTC).timestamp()*1000))
candles=[];cursor=start_ms;nreq=0
while cursor<end_ms:
 response=requests.get('https://fapi.binance.com/fapi/v1/klines',
  params={'symbol':'NEARUSDT','interval':'1m','startTime':cursor,
  'endTime':end_ms-1,'limit':1000},timeout=15)
 response.raise_for_status()
 page=response.json()
 if not isinstance(page,list):raise ValueError('binance unexpected data')
 if not page:break
 if not isinstance(page[0],list):raise ValueError('binance unexpected candle shape')
 candles+=page
 new_cursor=int(page[-1][0])+60000
 if new_cursor<=cursor:raise ValueError('nonmonotonic pagination')
 cursor=new_cursor;nreq+=1
 if nreq>9:raise RuntimeError('unexpected API pagination volume')
bars=sorted({int(x[6]):dict(t=int(x[6]),h=float(x[2]),l=float(x[3]),
  c=float(x[4])) for x in candles if int(x[6])<end_ms}.values(),key=lambda z:z['t'])
times=[z['t'] for z in bars]
assert len(bars)>=5000,(len(bars),nreq)
leverage=3;tp_roi=1.25;stop_price=2.99
fee_per_leg_notional_pct=0.04
fee_roundtrip_roi_pp=(2*fee_per_leg_notional_pct)*leverage
def stamp(t):
 return datetime.fromtimestamp(t/1000,TZ).isoformat()
def run(label_filter=None):
 done=[];busy=[];open_position=None
 free_after_ms=start_ms
 for e in events:
  if label_filter and e['research_label'] not in label_filter:continue
  observed=int(datetime.fromisoformat(e['model_ts_tr']).timestamp()*1000)
  if observed<free_after_ms:
   busy.append(e['model_ts_tr']);continue
  if open_position is not None:
   busy.append(e['model_ts_tr']);continue
  i=bisect_left(times,observed)
  if i>=len(bars):continue
  ref=bars[i]
  if not(0<ref['t']-observed<=60000):
   continue
  if ref['t']<free_after_ms:
   busy.append(e['model_ts_tr']);continue
  entry=ref['c'];hi_target=entry*(1+tp_roi/100/leverage)
  lo_stop=entry*(1-stop_price/100)
  after=bars[i+1:]
  if not after:continue
  # Verify entire history range contiguous, otherwise censor on gap.
  hit=None;elapsed_min=None;last_visited=ref;previous=ref
  for b in after:
   if b['t']-previous['t']!=60000:
    hit='CENSORED_GAP';break
   previous=b;last_visited=b
   top=b['h']>=hi_target;bottom=b['l']<=lo_stop
   if top or bottom:
    # Exact 1m intrabar order unknown -> conservatively stop first.
    hit='SAME_MINUTE_AMBIGUOUS_SL_FIRST' if top and bottom else 'TP_FIRST' if top else 'SL_FIRST'
    elapsed_min=round((b['t']-ref['t'])/60000,2)
    break
  if hit is None:hit='OPEN_AT_DATA_END'
  realized=hit in ('TP_FIRST','SL_FIRST','SAME_MINUTE_AMBIGUOUS_SL_FIRST')
  gross_roi=tp_roi if hit=='TP_FIRST' else -stop_price*leverage if realized else None
  net_roi=round(gross_roi-fee_roundtrip_roi_pp,4) if realized else None
  unrealized_roi=(last_visited['c']/entry-1)*100*leverage if not realized else None
  trade=dict(signal_time_tr=e['model_ts_tr'],reference_label=e['research_label'],
   market_regime=e.get('market_regime'),score=e['model_score'],
   ref_entry_time_tr=stamp(ref['t']),ref_entry_price=entry,
   tp_price=round(hi_target,8),stop_price=round(lo_stop,8),
   status=hit,exit_time_tr=stamp(last_visited['t']) if realized else None,
   last_observed_time_tr=stamp(last_visited['t']),
   holding_minutes=(elapsed_min if elapsed_min is not None else
       round((last_visited['t']-ref['t'])/60000,2)),
   gross_roi_pct=gross_roi,fee_adjusted_net_roi_pct_est=net_roi,
   indicative_unrealized_roi_pct=round(unrealized_roi,4) if unrealized_roi is not None else None,
   actual_exchange_trade=False)
  done.append(trade)
  if realized:
   # Following MODEL timestamps after approximate exit bar close can generate candidate.
   free_after_ms=last_visited['t']
  else:
   open_position=trade
   free_after_ms=last_visited['t']+10**12
   break
 states=Counter(z['status'] for z in done)
 realized=[x for x in done if x['fee_adjusted_net_roi_pct_est'] is not None]
 wins=[x for x in done if x['status']=='TP_FIRST']
 losses=[x for x in done if x['status'] in ('SL_FIRST','SAME_MINUTE_AMBIGUOUS_SL_FIRST')]
 return dict(hypothetical_entries=len(done),model_signals_skipped_while_occupied=len(busy),
   first_barrier_counts=dict(states),realized_n=len(realized),
   mean_fee_adjusted_roi_pct=round(mean(x['fee_adjusted_net_roi_pct_est'] for x in realized),4) if realized else None,
   sum_fee_adjusted_roi_pct=round(sum(x['fee_adjusted_net_roi_pct_est'] for x in realized),4),
   median_tp_holding_minutes=round(median(x['holding_minutes'] for x in wins),2) if wins else None,
   median_sl_holding_minutes=round(median(x['holding_minutes'] for x in losses),2) if losses else None,
   max_holding_minutes=max((x['holding_minutes'] for x in done),default=None),
   still_open=bool(open_position),closed_winners=len(wins),closed_losers=len(losses),
   hypothetical_trades=done)
result={}
for name,filterset in [('ALL_MODEL_LONGS',None),('LONG_AVOID_ONLY',{'LONG_AVOID'}),
                       ('LONG_TARGET_ONLY',{'LONG_TARGET'})]:
 x=run(filterset);result[name]=x
 print('\nGROUP',name,'ENTRIES',x['hypothetical_entries'],'SKIP_BUSY',x['model_signals_skipped_while_occupied'],
  'STATES',x['first_barrier_counts'],'AVG_EST_NET_ROI',x['mean_fee_adjusted_roi_pct'],
  'STILL_OPEN',x['still_open'],'MEDIAN_WIN_WAIT_MIN',x['median_tp_holding_minutes'],
  'MEDIAN_STOP_WAIT_MIN',x['median_sl_holding_minutes'])
 for t in x['hypothetical_trades']:
  print('SIM',t['signal_time_tr'],t['reference_label'],t['status'],
        'HOLD_MIN',t['holding_minutes'],'NET_ROI',t['fee_adjusted_net_roi_pct_est'],
        'UNREALIZED_ROI',t['indicative_unrealized_roi_pct'])
report=dict(schema='long1_model_longs_no_time_exit_first_hit_v1',
 research_only=True,order_authorized=False,
 active_60minute_timeout=False,first_post_signal_closed_bar_reference=True,
 last_closed_bar_tr=stamp(bars[-1]['t']),pricedata_n=len(bars),
 read_only_public_get_calls=nreq,
 fee_illustration=dict(notional_pct_each_leg=fee_per_leg_notional_pct,
 round_trip_roi_pct=fee_roundtrip_roi_pp),
 model_assumptions='All 103 model side=long events assumed eligible for execution. Cannot establish actual fills or past full entry/stop behavior. Keep open if no touch by data end.',
 no_dynamic_stop=True,no_mark_price_stop=True,no_funding=True,
 no_spread_or_slippage=True,no_actual_sniper_or_entry_confirmation=True,
 original_user_windows_not_used_to_filter_all_run=True,
 earlier_comparator='research/results/LONG1_MODEL_LONG_SINGLE_POSITION_60M_SENSITIVITY_20261111_15.json',
 result=result)
dst=ROOT/'research/results/LONG1_MODEL_LONG_NO_TIME_EXIT_FIRST_HIT_20261111_15.json'
dst.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('\nSAVED',dst,'last',report['last_closed_bar_tr'])
