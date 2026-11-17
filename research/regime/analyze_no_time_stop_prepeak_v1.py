"""Research only: peak ROI before first STOP for prior no-time-exit single-position model replay.

Do not include high of STOP bar because high/low order within minute is unknown.
No execution, lifecycle calls, account or Redis writes. Public Binance GET only.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from bisect import bisect_left
from pathlib import Path
from statistics import mean,median
import requests,json,math,csv
root=Path('/home/kasm920/binance1-pro')
src=root/'research/results/LONG1_MODEL_LONG_NO_TIME_EXIT_FIRST_HIT_20261111_15.json'
base=json.loads(src.read_text())
sims=base['result']['ALL_MODEL_LONGS']['hypothetical_trades']
stops=[z for z in sims if z['status'] in ('SL_FIRST','SAME_MINUTE_AMBIGUOUS_SL_FIRST')]
assert len(stops)==8
tz=timezone(timedelta(hours=3))
def stamp_ms(s):return int(datetime.fromisoformat(s).timestamp()*1000)
start=min(stamp_ms(z['ref_entry_time_tr']) for z in stops)-60000
end=max(stamp_ms(z['exit_time_tr']) for z in stops)+60000
candles=[];cursor=start;req=0
while cursor<end:
 response=requests.get('https://fapi.binance.com/fapi/v1/klines',params=dict(
  symbol='NEARUSDT',interval='1m',startTime=cursor,endTime=end-1,limit=1000),timeout=15)
 response.raise_for_status()
 page=response.json()
 if not isinstance(page,list) or not page or not isinstance(page[0],list):
  raise ValueError('Unexpected Binance OHLC response')
 candles.extend(page)
 new=int(page[-1][0])+60000
 if new<=cursor:raise ValueError('Non-progressive Binance pagination')
 cursor=new;req+=1
 if req>10:raise ValueError('Excess query volume')
bars=sorted({int(x[6]):dict(t=int(x[6]),o=float(x[1]),h=float(x[2]),
 l=float(x[3]),c=float(x[4])) for x in candles}.values(),key=lambda a:a['t'])
times=[b['t'] for b in bars]
res=[]
for z in stops:
 ref=stamp_ms(z['ref_entry_time_tr']);sl=stamp_ms(z['exit_time_tr'])
 i=bisect_left(times,ref);j=bisect_left(times,sl)
 assert i<len(bars) and j<len(bars) and times[i]==ref and times[j]==sl, (z['signal_time_tr'],i,j)
 assert j>i
 pre=bars[i+1:j] # STRICT before first stop bar; NO unknown intra-minute high
 assert all(pre[k+1]['t']-pre[k]['t']==60000 for k in range(len(pre)-1))
 entry=float(z['ref_entry_price'])
 # entry close is known, zero unrealized ROI at that instant
 highest=max(pre,key=lambda a:a['h']) if pre else None
 highest_close=max(pre,key=lambda a:a['c']) if pre else None
 peak_high=float(highest['h']) if highest else entry
 peak_close=float(highest_close['c']) if highest_close else entry
 best_roi=100*3*(peak_high/entry-1)
 best_close_roi=100*3*(peak_close/entry-1)
 shortfall=1.25-best_roi
 reached_be=peak_high>=entry
 def pretty(ms):return datetime.fromtimestamp(ms/1000,tz).strftime('%d Kas %H:%M:%S') if ms else None
 res.append(dict(signal_time_tr=z['signal_time_tr'],reference_entry_time_tr=z['ref_entry_time_tr'],
  entry_price=entry,
  first_stop_time_tr=z['exit_time_tr'],
  holding_minutes=z['holding_minutes'],
  minutes_eligible_before_stop=len(pre),
  highest_before_stop_price=peak_high,
  highest_before_stop_roi_pct=round(best_roi,4),
  time_of_max_high_before_stop_tr=pretty(highest['t']) if highest else None,
  minutes_from_entry_to_peak=round((highest['t']-ref)/60000,2) if highest else 0,
  minutes_from_peak_to_stop=round((sl-highest['t'])/60000,2) if highest else z['holding_minutes'],
  highest_completed_close_before_stop=peak_close,
  highest_close_roi_pct=round(best_close_roi,4),
  time_of_highest_close_tr=pretty(highest_close['t']) if highest_close else None,
  roi_target_pct=1.25,
  shortfall_roi_pp=round(shortfall,4),
  target_approach_ratio_pct=round(max(0,best_roi)/1.25*100,2),
  roi_0p5_touched=best_roi>=0.5,
  roi_0p75_touched=best_roi>=0.75,
  roi_1p0_touched=best_roi>=1,
  roi_1p25_touched=best_roi>=1.25,
  best_price_above_entry=peak_high>entry,
  last_candle_high_excluded=True,
  research_only=True))
res.sort(key=lambda z:z['signal_time_tr'])
out=root/'research/results/LONG1_NO_TIME_STOP_PREPEAK_8_TRADES_20261115.json'
out.write_text(json.dumps(dict(schema='long1_no_time_stop_prepeak_v1',
 source=str(src),research_only=True,no_order_authority=True,
 selected_stop_trades=len(stops),price_bars=len(bars),kline_get_requests=req,
 no_intrabar_order_claim=True,stop_bar_high_excluded=True,
 entry_price_is_hypothetical_first_post_signal_closed_1m=True,
 observation='highest 1m candle HIGH strictly after reference candle and strictly before first STOP-touch candle',
 results=res),ensure_ascii=False,indent=2)+'\n')
csv_path=root/'research/results/LONG1_NO_TIME_STOP_PREPEAK_8_TRADES_20261115.csv'
with csv_path.open('w',newline='') as f:
 w=csv.writer(f)
 w.writerow(['signal_tr','stop_tr','wait_to_stop_min','peak_ROI_pct','peak_time_tr',
  'entry_to_peak_min','peak_to_stop_min','remaining_to_1p25_ROI_pp',
  'max_close_ROI_pct','approach_target_pct'])
 for x in res:
  w.writerow([x['signal_time_tr'],x['first_stop_time_tr'],x['holding_minutes'],
  x['highest_before_stop_roi_pct'],x['time_of_max_high_before_stop_tr'],
  x['minutes_from_entry_to_peak'],x['minutes_from_peak_to_stop'],
  x['shortfall_roi_pp'],x['highest_close_roi_pct'],x['target_approach_ratio_pct']])
print('SIGNALS',len(res),'CANDLES',len(bars),'GETS',req)
for x in res:
 print(x['signal_time_tr'][5:16],'STOP',x['holding_minutes'],'BEST_ROI',x['highest_before_stop_roi_pct'],
 'MAX_CLOSE_ROI',x['highest_close_roi_pct'],'PEAK_TIME',x['time_of_max_high_before_stop_tr'],
 'PEAK_AT_MIN',x['minutes_from_entry_to_peak'],'SHORTFALL_PP',x['shortfall_roi_pp'],
 'APPROACH_PCT',x['target_approach_ratio_pct'])
print('SUMMARY','POSITIVE_PEAK',sum(x['best_price_above_entry'] for x in res),
 'ROI>=0.5',sum(x['roi_0p5_touched'] for x in res),
 'ROI>=0.75',sum(x['roi_0p75_touched'] for x in res),
 'ROI>=1.0',sum(x['roi_1p0_touched'] for x in res),
 'ROI>=1.25',sum(x['roi_1p25_touched'] for x in res),
 'mean_peak_roi',round(mean(x['highest_before_stop_roi_pct'] for x in res),4),
 'median_peak_roi',round(median(x['highest_before_stop_roi_pct'] for x in res),4))
print('OUTPUT',out,csv_path)
