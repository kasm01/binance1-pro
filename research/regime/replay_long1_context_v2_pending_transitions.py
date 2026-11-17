"""Research-only delayed MODEL revalidation of all 103 LONG model events.

For each adverse/unknown signal, later independent MODEL LONG within 30min,
with completely CLOSED post-origin 3m AND 5m rising price returns and positive
AS-OF archived flow, counts as a RECHECK-ELIGIBLE SHADOW event only.
No Sniper, 1m Entry Confirmation, Risk or Final Safety authority; never READY
for a trade. This gives an upper bound on easy recoveries under strict model
renewal, not profitability.
"""
import json
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path('/home/kasm920/binance1-pro')
p=ROOT/'research/results/LONG1_MARKET_CONTEXT_V2_103_ASOF_20261111_15.json'
rows=json.loads(p.read_text())['full_results']
from datetime import datetime
x=sorted(rows,key=lambda z:z['ts_tr'])
output=[]
for i,origin in enumerate(x):
 now=datetime.fromisoformat(origin['ts_tr'])
 subsequent=[]
 for z in x[i+1:]:
  elapsed=(datetime.fromisoformat(z['ts_tr'])-now).total_seconds()
  if elapsed>1800:break
  if elapsed<=0 or z['close_id']<=origin['close_id']:continue
  f=z['features']
  if f is None:continue
  if (f['flow15'] is not None and f['flow15']>=0 and
       f['return_3m']>0 and f['return_5m']>0):
   subsequent.append(dict(ts_tr=z['ts_tr'],close_id=z['close_id'],elapsed_minutes=round(elapsed/60,2),
     flow15=f['flow15'],return_3m=f['return_3m'],return_5m=f['return_5m']))
 record=dict(origin_tr=origin['ts_tr'],label=origin['reference_label'],
  origin_decision=origin['decision'],origin_reason=origin['reason'],
  found_independent_model_with_recovery=bool(subsequent),
  first_proof=subsequent[0] if subsequent else None,
  missing_1m_entry_confirmation=True,orders_authorized=False)
 output.append(record)
print('ALL',len(output),'RECHECK_ELIGIBLE',sum(z['found_independent_model_with_recovery'] for z in output))
print('BY_LABEL_AND_DECISION')
counter=Counter((z['label'],z['origin_decision'],z['found_independent_model_with_recovery']) for z in output)
for name,count in sorted(counter.items()):print(name,count)
for z in output:
 if z['found_independent_model_with_recovery']:
  print('RECHECK',z['origin_tr'],z['label'],z['origin_decision'],z['first_proof'])
dest=ROOT/'research/results/LONG1_MARKET_CONTEXT_V2_PENDING_RECHECK_103_20261111_15.json'
dest.write_text(json.dumps(dict(schema='long1_v2_pending_recheck_future_model_shadownly',
 research_only=True,origin_model_events=len(output),no_real_order_authority=True,
 new_complete_3m_5m_after_origin_NOT_verified=True,
 note='This code tests future model timestamp and positive returns measured as-of the future; it DOES NOT guarantee the completed 3m or 5m bars happened after original origin. Must check candle close IDs before further use. 1m confirmation missing. Do not promote.',
 rows=output),ensure_ascii=False,indent=2)+'\n')
print('SAVED',dest)
