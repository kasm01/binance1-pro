"""Evaluate actual historical MODEL LONG events under shadow regime-v1.

For 11-15 Nov, as-of completed 3m/5m/15m public klines and EXISTING
microstructure Redis for at most 30s before MODEL-SCORE log timestamp.
No fabricated historic flow when Redis stream retention has evicted data.
"""
from __future__ import annotations
import requests,redis,json,re,bisect,collections,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
from research.regime.long1_market_regime_shadow_v1 import classify
from research.shared_reference.window_reference_reader_v1 import lookup,load_reference
ROOT=Path('/home/kasm920/binance1-pro');TR=timezone(timedelta(hours=3));UTC=timezone.utc
start=int(datetime(2026,11,10,20,tzinfo=UTC).timestamp()*1000)
end=int(datetime(2026,11,15,21,tzinfo=UTC).timestamp()*1000)
def getbars(tf,interval):
 out=[];cursor=start
 while cursor<end:
  res=requests.get('https://fapi.binance.com/fapi/v1/klines',params=dict(
   symbol='NEARUSDT',interval=tf,startTime=cursor,endTime=end-1,limit=1000),timeout=12)
  res.raise_for_status();got=res.json()
  if not isinstance(got,list):raise ValueError('binance returned error')
  if not got:break
  out.extend(got)
  nxt=int(got[-1][0])+interval
  if nxt<=cursor:raise ValueError('non-progressing data')
  cursor=nxt
 return sorted({int(z[6]):dict(t=int(z[6]),c=float(z[4]),h=float(z[2]),l=float(z[3])) for z in out}.values(),key=lambda z:z['t'])
bars={tf:getbars(tf,step) for tf,step in [('3m',180000),('5m',300000),('15m',900000)]}
times={tf:[z['t'] for z in group] for tf,group in bars.items()}
def past(tf,now,count):
 i=bisect.bisect_left(times[tf],now)
 return bars[tf][max(0,i-count):i]
def return_asof(now,flow):
 b3=past('3m',now,2);b5=past('5m',now,2);b15=past('15m',now,3)
 if len(b3)<2 or len(b5)<2 or len(b15)<3:return None
 if now-b3[-1]['t']>183000 or now-b5[-1]['t']>303000 or now-b15[-1]['t']>903000:return None
 return dict(return_3m=b3[-1]['c']/b3[-2]['c']-1,
 return_5m=b5[-1]['c']/b5[-2]['c']-1,
 return_15m=b15[-1]['c']/b15[-2]['c']-1,
 return_30m=b15[-1]['c']/b15[-3]['c']-1,
 flow15=flow,asof_complete=True)
r=redis.Redis(decode_responses=True,socket_timeout=5)
ms_micro=[];flow_micro=[]
for sid,ff in r.xrange('shadow:telemetry:microstructure'):
 try:
  at=int(sid.split('-')[0])
  if at<start or at>end:continue
  z=json.loads(ff.get('json') or '{}')
  observed=int(z.get('observed_at_ms') or at)
  if observed>at+1000 or observed<at-5000:continue
  val=float(z['t15_signed_ratio'])
  if -1<=val<=1:
   ms_micro.append(at);flow_micro.append(val)
 except (ValueError,TypeError,KeyError):pass
if ms_micro!=sorted(ms_micro):raise RuntimeError('micro stream not sorted')
models={}
pat=re.compile(r'close_id=(\d+) p_used=([\d.]+) long_thr=([\d.]+) side=(\w+)')
for p in ('logs/main.log.3','logs/main.log.2','logs/main.log.1','logs/main.log'):
 fp=ROOT/p
 if not fp.exists():continue
 for line in fp.open(errors='replace'):
  if '[MODEL-SCORE]' not in line:continue
  m=pat.search(line)
  if not m:continue
  try:
   t=datetime.strptime(line[:19],'%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
  except ValueError:continue
  now=int(t.timestamp()*1000)
  if now<start or now>=end:continue
  local=t.astimezone(TR)
  if not('2026-11-11'<=local.date().isoformat()<='2026-11-15'):continue
  cid=int(m[1])
  models[cid]=dict(cid=cid,ts_ms=now,ts_tr=local.isoformat(),
    score=float(m[2]),rolling=float(m[3]),model_long=(m[4]=='long'))
rows=[]
for cid,z in sorted(models.items()):
 if not z['model_long']:continue
 ms=z['ts_ms'];i=bisect.bisect_right(ms_micro,ms)-1
 age=(ms-ms_micro[i])/1000 if i>=0 else None
 flow=flow_micro[i] if age is not None and 0<=age<=30 else None
 p=return_asof(ms,flow) if flow is not None else None
 decision=classify(p)
 label=lookup(datetime.fromisoformat(z['ts_tr']))['long']
 rows.append(dict(**z,reference_label=label,flow_source='prior_micro_30sec' if flow is not None else 'MISSING',
  micro_age_seconds=age,price_asof_available=return_asof(ms,0) is not None,
  asof_price_flow=p,decision=decision))
out=ROOT/'research/results/LONG1_TRUE_MODEL_LONG_REGIME_SHADOW_V1_20261111_15.json'
out.write_text(json.dumps(dict(schema='long1_true_model_long_regime_v1',
 no_order_authority=True,no_user_time_labels_in_classifier=True,not_full_pipeline_or_pnl=True,
 micro_first_event=ms_micro[0] if ms_micro else None,
 model_long_count=len(rows),source_model_is_logs=True,
 model_plus_micro_coverage=sum(x['flow_source']!='MISSING' for x in rows),
 full_results=rows),ensure_ascii=False,indent=2)+'\n')
for day in ('2026-11-11','2026-11-12','2026-11-13','2026-11-14','2026-11-15'):
 for label in ('LONG_TARGET','LONG_AVOID','CONFLICT_NO_TRADE','UNLABELLED'):
  group=[x for x in rows if x['ts_tr'][:10]==day and x['reference_label']==label]
  if label=='UNLABELLED':continue
  cnt=collections.Counter(x['decision']['regime'] for x in group)
  print(day,label,'MODEL_LONG',len(group),'FLOW_AVAILABLE',sum(x['flow_source']!='MISSING' for x in group),
   'DECISIONS',dict(cnt))
print('TOTAL',len(rows),'FLOW_AVAILABLE',sum(x['flow_source']!='MISSING' for x in rows),
 'MICRO_EVENTS',len(ms_micro),'OUT',out)
