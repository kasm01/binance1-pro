"""Observed *future* OHLC excursions for four user-specified MODEL times.

Diagnostic only: hypothetical next 1m OPEN entry following model event,
not actual fill. The first candle can contain both high and low in unknown
order. Every horizon reports maxima/minima, NOT realizable trade PnL.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from bisect import bisect_left
import csv,gzip,json
R=Path(__file__).resolve().parents[2]
p=json.loads((R/'research/results/LONG1_70_USER_WINDOWS_ASOF_SIMULATION_20261120.json').read_text())
f=R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz'
with gzip.open(f,'rt') as q:
 bars=[{'t':int(x['open_time_ms']),'o':float(x['open']),
     'h':float(x['high']),'l':float(x['low']),'c':float(x['close'])}
     for x in csv.DictReader(q)]
open_ms=[z['t'] for z in bars]
result=[]
for point in p['pinpoints']:
 event=point['same_minute_model_events']
 assert len(event)==1
 ts=event[0]['model_time_tr']
 origin=int(datetime.fromisoformat(ts).timestamp()*1000)
 # Cannot know minute OHLC after event timestamp: wait for next full 1m OPEN
 idx=bisect_left(open_ms,origin)
 assert open_ms[idx]>=origin and open_ms[idx]-origin<60000
 entry=bars[idx]['o']
 horizons={}
 for minutes in (1,3,5,15,30,60):
  block=bars[idx:idx+minutes]
  hi=max(z['h'] for z in block);lo=min(z['l'] for z in block)
  horizons[str(minutes)]={
   'max_gross_long_roi_pp':round(300*(hi/entry-1),4),
   'min_gross_long_roi_pp':round(300*(lo/entry-1),4),
   'max_net_long_roi_pp_if_perfect_exit_minus_fee':round(300*(hi/entry-1)-.24,4),
   'range_high_price':hi,'range_low_price':lo}
 result.append({'model_time_tr':ts,'decision':event[0]['stage13_decision'],
   'reference_label':event[0]['stage13_model_label'],
   'hypothetical_next_1m_open_time_tr':datetime.fromtimestamp(open_ms[idx]/1000,
      ZoneInfo('Europe/Istanbul')).isoformat(),
   'hypothetical_open_price':entry,
   'future_horizon_minutes':horizons,
   'this_is_ex_post_excursion_not_achievable_roi':True,
   'real_model_intent_entry_attested':False,
   'actual_order_or_fill':False})
out={'schema':'long1_four_reversal_model_clock_expost_excursion_v1',
 'symbol':'NEARUSDT','leverage':3,'total_events':len(result),
 'fee_roundtrip_roi_pp_assumed':.24,
 'entry_assumption':'NEXT_1M_OPEN_AFTER_MODEL_EVENT_TIME',
 'intrabar_high_low_order_unknown':True,
 'no_lookahead_trading_entry':True,
 'expost_future_range_not_entry_approval':True,
 'actual_order_authority':False,'real_orders':0,'production_redis_writes':0,
 'events':result}
dst=R/'research/results/LONG1_FOUR_FAST_REVERSAL_1M_60M_EXCURSIONS_20261120.json'
dst.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','events':[{'time':a['model_time_tr'],
 'decision':a['decision'],'entry':a['hypothetical_open_price'],
 'horizons':{m:{k:v for k,v in a['future_horizon_minutes'][m].items()
  if k in ('max_gross_long_roi_pp','min_gross_long_roi_pp')}
  for m in ('1','3','5','15')}} for a in result]},sort_keys=True))
