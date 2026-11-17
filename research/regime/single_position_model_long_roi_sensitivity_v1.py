"""Single-position counterfactual on MODEL LONG timestamps, research only.

One concurrent NEARUSDT position. 60m time exit if no TP/SL. Entry at the close
of the first fully closed 1m candle after model timestamp; fee model 0.04%
per leg of NOTIONAL; 3x ROI. Exact order/fill, dynamic 30 sec stop, funding,
spread, execution safety ignored. All candidates assumed executable (NOT true).
"""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from collections import Counter
import json,csv
ROOT=Path('/home/kasm920/binance1-pro')
src=json.loads((ROOT/'research/results/LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json').read_text())
events=sorted(src['events'],key=lambda z:z['model_ts_tr'])
TZ=timezone(timedelta(hours=3))
FEE_ROI_PCT=0.08*3
LEVERAGE=3
def sim(label_filter=None):
 active_until=datetime.min.replace(tzinfo=TZ)
 executed=[];skipped=[]
 for z in events:
  if label_filter and z['research_label'] not in label_filter:continue
  event_time=datetime.fromisoformat(z['model_ts_tr'])
  if event_time<active_until:
   skipped.append(z);continue
  h=z['horizons']['60']
  if h['status']=='CENSORED_INCOMPLETE_FORWARD_WINDOW':continue
  entry_t=datetime.strptime(z['reference_candle_closed_tr'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ)
  if entry_t<active_until:skipped.append(z);continue
  state=h['status']
  if state=='TP_FIRST':
   close_t=datetime.strptime(h['tp_touched_tr'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ)
   gross_roi=1.25
  elif state in ('SL_FIRST','SAME_MINUTE_AMBIGUOUS_SL_FIRST'):
   close_t=datetime.strptime(h['sl_touched_tr'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ)
   gross_roi=-2.99*LEVERAGE
  else:
   close_t=entry_t+timedelta(minutes=60)
   gross_roi=LEVERAGE*h['horizon_end_change_price_pct']
  active_until=close_t
  executed.append(dict(signal_ts_tr=z['model_ts_tr'],label=z['research_label'],state=state,
    assumed_entry_t=entry_t.isoformat(),assumed_exit_t=close_t.isoformat(),
    gross_roi_pct=round(gross_roi,4),net_roi_pct_est=round(gross_roi-FEE_ROI_PCT,4),
    actual_trade=False))
 return executed,skipped
result={}
for title,filters in [('ALL_MODEL_LONGS',None),('LONG_AVOID_ONLY',{'LONG_AVOID'}),
                      ('LONG_TARGET_ONLY',{'LONG_TARGET'})]:
 tx,skips=sim(filters)
 by=Counter(z['state'] for z in tx)
 label=Counter(z['label'] for z in tx)
 result[title]=dict(n=len(tx),skipped_busy=len(skips),states=dict(by),labels=dict(label),
   sum_gross_roi_pct=round(sum(z['gross_roi_pct'] for z in tx),4),
   sum_fee_adjusted_roi_pct_est=round(sum(z['net_roi_pct_est'] for z in tx),4),
   mean_fee_adjusted_roi_pct_est=round(sum(z['net_roi_pct_est'] for z in tx)/len(tx),4) if tx else None,
   assumed_trades=tx)
 print(title,'N',len(tx),'BUSY_SKIP',len(skips),'STATES',dict(by),'LABELS',dict(label),
       'MEAN_NET_ROI',result[title]['mean_fee_adjusted_roi_pct_est'])
 for x in tx:
  print(' SEQUENTIAL',x['signal_ts_tr'],x['label'],x['state'],x['net_roi_pct_est'])
out=ROOT/'research/results/LONG1_MODEL_LONG_SINGLE_POSITION_60M_SENSITIVITY_20261111_15.json'
out.write_text(json.dumps(dict(schema='long1_model_long_one_position_v1',research_only=True,
 no_order_authority=True,
 assumptions=dict(gross_tp_roi_pct=1.25,stop_price_pct=2.99,
 leverage=3,fee_per_leg_notional_pct=0.04,roundtrip_fee_roi_pct=FEE_ROI_PCT,
 maximum_holding_minutes=60,one_symbol_one_open=True,
 all_model_signals_assumed_executable=True,no_dynamic_stop_confirmation=True,
 no_actual_sniper_entry_or_fill=True,no_spread_funding_slippage=True),
 note='SUM ROI across hypothetical, non-overlap candidate episodes is NOT a real equity return and not supported as live PnL.',
 result=result),ensure_ascii=False,indent=2)+'\n')
print('SAVED',out)
