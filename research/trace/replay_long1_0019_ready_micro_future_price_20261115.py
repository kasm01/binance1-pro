"""Price-only counterfactual after actual 1m micro snapshot READY.

Counterfactual fills at archived micro last trade price, NOT real execution.
M1 bars start following whole minute to prohibit data leak. Same-bar
TP/SL resolves stop first; fees illustrative only, no dynamic/native stop.
"""
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import json,requests
ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'research/results/LONG1_ACTUAL_ENTRY_GATE_MICRO_20261115_0018.json'
data=json.loads(P.read_text())
ready_times=set()
for p in data['profiles'].values():
 for e in p['evaluations']:
  if e['entry_action']=='open' and e['sniper_window_current_005_060']:
   ready_times.add(e['time_tr'])
assert len(ready_times)==2,ready_times
t0=min(datetime.fromisoformat(t) for t in ready_times)
start=t0.replace(second=0,microsecond=0)+timedelta(minutes=1)
end=start+timedelta(minutes=61)
r=requests.get('https://fapi.binance.com/fapi/v1/klines',
 params={'symbol':'NEARUSDT','interval':'1m','startTime':int(start.timestamp()*1000),
 'endTime':int(end.timestamp()*1000)-1,'limit':100},timeout=12,allow_redirects=False)
r.raise_for_status()
rows=r.json()
assert len(rows)==61,(len(rows),start,end)
for i,row in enumerate(rows):
 assert int(row[0])==int(start.timestamp()*1000)+i*60000
# fetch the original time-specific observed price from bounded source Redis
import redis
client=redis.Redis(decode_responses=True,socket_timeout=5)
out=[]
for t in sorted(ready_times):
 dt=datetime.fromisoformat(t)
 ms=int(dt.timestamp()*1000)
 source=client.xrange('shadow:telemetry:microstructure',min=str(ms-1200)+'-0',
                      max=str(ms+1200)+'-999999')
 assert source
 records=[json.loads(f.get('json') or '{}') for _,f in source]
 record=min(records,key=lambda x:abs(int(x['observed_at_ms'])-ms))
 px=float(record['live1m_close'])
 assert px>0
 threshold=px*(1+1.25/300)
 stop=px*(1-.0299)
 # entirely after actual observation minute: 00:20 onward.
 status='NO_BARRIER_IN_60M'
 exit_time=None
 for bar in rows[:60]:
  hit_tp=float(bar[2])>=threshold
  hit_sl=float(bar[3])<=stop
  if hit_tp or hit_sl:
   status='SAME_BAR_STOP_FIRST' if hit_tp and hit_sl else 'STOP_FIRST' if hit_sl else 'TP_FIRST'
   exit_time=datetime.fromtimestamp(int(bar[0])/1000,ZoneInfo('Europe/Istanbul')).isoformat(timespec='seconds')
   break
 close_last=float(rows[59][4])
 if status=='TP_FIRST':gross=1.25
 elif status in ('STOP_FIRST','SAME_BAR_STOP_FIRST'):gross=-8.97
 else:gross=(close_last/px-1)*300
 out.append({'micro_ready_timestamp_tr':t,'observed_micro_price':px,
             'hypothetical_tp_price':round(threshold,6),
             'hypothetical_stop_price':round(stop,6),
             'future_60m_barrier_status':status,
             'barrier_touch_time_tr':exit_time,
             'gross_roi_pct':round(gross,4),
             'net_roi_after_illustrative_0p08pct_notional_fees':round(gross-.24,4),
             'order_eligibility_not_established':True,
             'micro_price_execution_not_proven':True})
data['future_barrier_counterfactual_on_micro_ready']={
 'method':'no-entry-minute fully-completed next 60 1m candles',
 'tp_gross_roi_pct':1.25,
 'price_stop_pct':2.99,
 'fee_roundtrip_notional_pct_assumed':.08,
 'real_native_stop_or_market_slippage_not_included':True,
 'independent_intent_after_00_18_not_verified':True,
 'scenarios':out,
}
P.write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'status':'PASS','scenarios':out,
 'public_kline_requests':1,'orders_sent':0,'production_redis_writes':0},sort_keys=True))
