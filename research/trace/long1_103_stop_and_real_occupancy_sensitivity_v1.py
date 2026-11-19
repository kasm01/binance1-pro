"""Post-entry sensitivity on fixed, already as-of selected 103-model candidates.

Stop levels are hypothetical (not exchange native stop or executable).
Recalculates sequential single-position book at each stop; does not tune
candidate selection, compare other direction, or claim live win rates.
Also vetoes collision with HISTORIC actual broker positions in separate
analysis (not a replay of what would truly happen with new entries).
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import csv,gzip,json
from collections import Counter
R=Path(__file__).resolve().parents[2]
a=json.loads((R/'research/results/LONG1_NEW_BINANCE_103_ASOF_3PROFILE_REPLAY_20261119.json').read_text())
b=json.loads((R/'research/results/LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 candles=[dict(t=int(x['open_time_ms']),o=float(x['open']),h=float(x['high']),
  l=float(x['low']),c=float(x['close'])) for x in csv.DictReader(f)]
actual=[(datetime.fromisoformat(x['open_tr']),datetime.fromisoformat(x['close_tr'])) for x in b['trades']]
from datetime import datetime
def closepath(e,sl_price_pct):
 j0=int(e['entry_replay_index'])
 price=float(e['entry_price'])
 tp=price*(1+1.25/300)
 stop=price*(1-sl_price_pct/100)
 for j in range(j0,j0+60):
  c=candles[j]
  hit_tp=c['h']>=tp;hit_sl=c['l']<=stop
  if hit_tp or hit_sl:
   status='SAME_BAR_STOP_FIRST' if hit_tp and hit_sl else 'SL_FIRST' if hit_sl else 'TP_FIRST'
   sale=stop if hit_sl else tp
   return j,status,round((sale/price-1)*300-.24,4)
 j=j0+59
 return j,'TIMEOUT',round((candles[j]['c']/price-1)*300-.24,4)

scenarios={}
for pname,profile in a['comparisons'].items():
 ready=[x for x in profile['events'] if x['decision']=='RESEARCH_READY']
 ready.sort(key=lambda x:x['entry_replay_index'])
 stop_results={}
 for stop_pct in (0.65,1.0,1.5,2.99):
  book=[];busy_thru=-1;busy_broker=-1;book_broker=[]
  for e in ready:
   idx=e['entry_replay_index']
   exit_idx,status,net=closepath(e,stop_pct)
   if idx>busy_thru:
    book.append((e,exit_idx,status,net))
    busy_thru=exit_idx
   dt=datetime.fromisoformat(e['price_entry_time_tr'])
   if not any(lo<=dt<hi for lo,hi in actual) and idx>busy_broker:
    book_broker.append((e,exit_idx,status,net))
    busy_broker=exit_idx
  def agg(book):
   return dict(n=len(book),win=sum(x[3]>0 for x in book),
     loss=sum(x[3]<0 for x in book),outcomes=dict(Counter(x[2] for x in book)),
     roi_pp_sum=round(sum(x[3] for x in book),3),
     labels=dict(Counter(x[0]['reference_label'] for x in book)),
     by_label_roi_pp={label:round(sum(x[3] for x in book if x[0]['reference_label']==label),3)
       for label in ['LONG_TARGET','LONG_AVOID','UNLABELLED']})
  stop_results[str(stop_pct)]={'simulation_only_book':agg(book),
     'with_historic_broker_occupancy_veto':agg(book_broker),
     'stop_price_pct':stop_pct,'no_native_stop_fill_proof':True}
 scenarios[pname]=stop_results
res={'schema':'long1_103_asof_entry_fixed_tp_stop_sensitivity_v1',
 'public_closed_bar_input':True,'profile_selection_prior_stop_test':True,
 'not_validated_profit_lock_or_native_stop':True,
 'fee_notional_roundtrip_assumption_pct':.08,
 'portfolio_roi_points_not_account_return':True,
 'book_with_existing_trades_is_overlap_sensitivity_only':True,
 'historical_user_label_not_used_as_trade_permission':True,
 'real_executed_orders':0,'production_redis_writes':0,
 'stop_price_pct_values':[.65,1.0,1.5,2.99],
 'profiles':scenarios}
dest=R/'research/results/LONG1_NEW_BINANCE_103_STOP_SENSITIVITY_20261119.json'
dest.write_text(json.dumps(res,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','results':{name:{sl:row['simulation_only_book']
 for sl,row in values.items()} for name,values in scenarios.items()},
 'real_orders':0},sort_keys=True))
