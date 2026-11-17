"""Read-only V2 context prospective-as-of price/archived flow replay, all 103 MODEL LONGs.

Human labels and eventual TP/SL are JOINED only AFTER decisions are computed.
Zero order authority, no production changes.
"""
import json,requests,bisect
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter,defaultdict
from research.regime.long1_market_context_v2_shadow import classify,POLICY_ID
ROOT=Path('/home/kasm920/binance1-pro')
source=json.load(open(ROOT/'research/results/LONG1_TRUE_MODEL_LONG_REGIME_SHADOW_V1_20261111_15.json'))
events=source['full_results'];assert len(events)==103
results=json.load(open(ROOT/'research/results/LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json'))
by_event={z['model_ts_tr']:z for z in results['events']}
start=int(datetime(2026,11,10,20,tzinfo=timezone.utc).timestamp()*1000)
end=int(datetime(2026,11,15,21,tzinfo=timezone.utc).timestamp()*1000)
def get(tf,step):
 raw=[];t=start
 while t<end:
  res=requests.get('https://fapi.binance.com/fapi/v1/klines',params=dict(symbol='NEARUSDT',interval=tf,startTime=t,endTime=end-1,limit=1000),timeout=15)
  res.raise_for_status();rows=res.json()
  if not isinstance(rows,list):raise ValueError('invalid response')
  if not rows:break
  raw+=rows
  new=int(rows[-1][0])+step
  if new<=t:raise ValueError('pagination stalled')
  t=new
 return sorted({int(z[6]):dict(ms=int(z[6]),close=float(z[4])) for z in raw}.values(),key=lambda z:z['ms'])
data={tf:get(tf,step) for tf,step in [('3m',180000),('5m',300000),('15m',900000)]}
times={tf:[z['ms'] for z in a] for tf,a in data.items()}
def prior(tf,ms,n):
 i=bisect.bisect_left(times[tf],ms)
 return data[tf][max(0,i-n):i]
def context(ms,flow):
 a=prior('3m',ms,2);b=prior('5m',ms,2);c=prior('15m',ms,3)
 if len(a)<2 or len(b)<2 or len(c)<3:return None
 if ms-a[-1]['ms']>183000 or ms-b[-1]['ms']>303000 or ms-c[-1]['ms']>903000:return None
 return dict(return_3m=a[-1]['close']/a[-2]['close']-1,
 return_5m=b[-1]['close']/b[-2]['close']-1,
 return_15m=c[-1]['close']/c[-2]['close']-1,
 return_30m=c[-1]['close']/c[-3]['close']-1,
 flow15=flow,asof_complete=True)
rows=[]
for e in events:
 flow=e['asof_price_flow']['flow15'] if e['asof_price_flow'] is not None else None
 features=context(e['ts_ms'],flow)
 decision=classify(features)
 retrospect=by_event.get(e['ts_tr'])
 rows.append(dict(ts_tr=e['ts_tr'],close_id=e['cid'],reference_label=e['reference_label'],
  flow_available=flow is not None,
  features=features,regime=decision['regime'],
  decision=decision['decision'],reason=decision['reason'],
  first_hit_60m=retrospect['horizons']['60']['status'] if retrospect else None,
  stop_before_tp_60m=retrospect['horizons']['60']['status']=='SL_FIRST' if retrospect else None,
  orders_authorized=False))
by=defaultdict(list)
for x in rows:by[(x['reference_label'],x['decision'])].append(x)
print('TOTAL',len(rows))
for k,group in sorted(by.items()):
 c=Counter(x['first_hit_60m'] for x in group)
 print(k,'n',len(group),'first_hit',dict(c),'flow_covered',sum(x['flow_available'] for x in group))
print('FOUR_FAST_REVERSAL')
for when in ['2026-11-12T01:36','2026-11-14T17:06','2026-11-14T19:06','2026-11-14T23:57']:
 x=next(z for z in rows if z['ts_tr'].startswith(when))
 print(when,x['regime'],x['decision'],x['reason'],'flow_known',x['flow_available'],'first_hit_60',x['first_hit_60m'])
print('MODEL_35_BASELINE')
baseline=json.load(open(ROOT/'research/results/LONG1_MODEL_LONG_NO_TIME_EXIT_FIRST_HIT_20261111_15.json'))['result']['ALL_MODEL_LONGS']['hypothetical_trades']
chosen={z['signal_time_tr'] for z in baseline}
for decision in ['VETO_ADVISORY','PENDING','READY_CANDIDATE']:
 g=[x for x in rows if x['ts_tr'] in chosen and x['decision']==decision]
 status=Counter(next(z['status'] for z in baseline if z['signal_time_tr']==x['ts_tr']) for x in g)
 print(decision,'baseline_35_n',len(g),'outcomes',dict(status))
payload=dict(schema='long1_market_context_v2_on_103_v1',research_only=True,
 shadow_only=True,source='model score events with strictly prior fully completed public klines and prior Redis flow <=30sec when available',
 human_labels_used_for_decision=False,exits_used_for_decision=False,
 first_hit_is_retro_counterfactual_not_fill=True,baseline_35_fixed_entry_coverage=True,
 missing_flow_produces_no_ready=True,full_results=rows)
dest=ROOT/'research/results/LONG1_MARKET_CONTEXT_V2_103_ASOF_20261111_15.json'
dest.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
print('SAVED',dest)
