"""Untouched frozen LONG1 recovery v1 run on preregistered 6-hour blocks.

No trading side effects, source: existing timestamped shadow context + public
Binance completed klines. Training date Nov 15 excluded.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, timedelta, time as dt_time, date
import requests, redis,json,bisect,hashlib,collections
from research.long1_recovery_regime_frozen_v1 import assess
ROOT=Path('research/results')
TZ=timezone(timedelta(hours=3))
first=date(2026,11,3);last=date(2026,11,13)
def utc_ms(dt):return int(dt.timestamp()*1000)
# Pre-register all 44 windows, not chosen based on price or labels.
blocks=[]
current=first
while current<=last:
 for hour in (0,6,12,18):
  a=datetime.combine(current,dt_time(hour),tzinfo=TZ)
  b=a+timedelta(hours=6)
  blocks.append(dict(date=current.isoformat(),label=f'{hour:02}:00-{(hour+6):02}:00',
        start_ms=utc_ms(a),end_ms=utc_ms(b)))
 current+=timedelta(days=1)
r=redis.Redis(decode_responses=True,socket_timeout=6)
lo=min(v['start_ms'] for v in blocks)
hi=max(v['end_ms'] for v in blocks)
rr=r.xrange('telemetry:long1:context_adaptive_gate:v1',f'{lo}-0',f'{hi-1}-99999')
events=[]
for sid,fields in rr:
 try:
  z=json.loads(fields['json'])
  cid=int(z['close_id'])
  observed_ms=int(sid.split('-')[0])
  events.append(dict(close_id=cid,observed_ms=observed_ms,score=z.get('score'),
   flow15=z.get('t15_signed_ratio'),one_min_support=z.get('live1m_long_direction_support'),
   shadow_record_present=True,all_shadow_checks=z.get('checks'),
   shadow_pass=z.get('pass')))
 except Exception:pass
# Evaluate on UTC November 10 18:00 to Nov 14 00:00. All data fetched
# in bounded paged public read-only calls; no response retained permanently.
start=utc_ms(datetime(2026,11,10,18,tzinfo=timezone.utc))
end=utc_ms(datetime(2026,11,14,0,tzinfo=timezone.utc))
def fetch_klines(tf,step_ms):
 out=[];at=start
 while at<end:
  resp=requests.get('https://fapi.binance.com/fapi/v1/klines',
      params={'symbol':'NEARUSDT','interval':tf,'startTime':at,
      'endTime':end-1,'limit':1000},timeout=12)
  resp.raise_for_status()
  got=resp.json()
  if not isinstance(got,list) or not got or not isinstance(got[0],list):
   raise ValueError(f'invalid Binance {tf} history at {at}')
  out+=got
  nxt=int(got[-1][0])+step_ms
  if nxt<=at:raise ValueError('non-monotonic pagination')
  at=nxt
 d={int(z[6]):dict(close_ms=int(z[6]),o=float(z[1]),c=float(z[4]),
   h=float(z[2]),l=float(z[3])) for z in out}
 return sorted(d.values(),key=lambda v:v['close_ms'])
bars={tf:fetch_klines(tf,ms) for tf,ms in
 [('3m',180000),('5m',300000),('15m',900000)]}
closes={tf:[x['close_ms'] for x in v] for tf,v in bars.items()}
def getprior(tf,ts):
 arr=bars[tf]; idx=bisect.bisect_left(closes[tf],ts)
 return arr[:idx]
def features(ts):
 z3=getprior('3m',ts);z5=getprior('5m',ts);z15=getprior('15m',ts)
 if len(z3)<4 or len(z5)<3 or len(z15)<3:return None
 if ts-z3[-1]['close_ms']>183000 or ts-z5[-1]['close_ms']>303000:
  return None
 return dict(return_3m=z3[-1]['c']/z3[-2]['c']-1,
  return_9m=z3[-1]['c']/z3[-4]['c']-1,
  return_5m=z5[-1]['c']/z5[-2]['c']-1,
  return_15m=z15[-1]['c']/z15[-2]['c']-1,
  three_m_higher_low=z3[-1]['l']>z3[-2]['l'],
  five_m_higher_low=z5[-1]['l']>z5[-2]['l'])
# Require actual shadow source observed at/after candle close, not future.
detail=[]
for item in events:
 t=item['observed_ms']
 if not start<=t<end:continue
 feature=features(t)
 result=assess(dict(item,price_features=feature))
 detail.append(dict(ts_tr=datetime.fromtimestamp(t/1000,TZ).isoformat(),
  observed_ms=t,close_id=item['close_id'],score=item['score'],
  recovery_status=result['status'],reason=result['reason'],
  source_available=feature is not None,
  context_shadow_pass=item['shadow_pass'],
  order_authorized=False))
summary=[]
for row in blocks:
 curr=[z for z in detail if row['start_ms']<=z['observed_ms']<row['end_ms']]
 ready=[z for z in curr if z['recovery_status']=='SHADOW_READY_CANDIDATE']
 # Missing entire 6h block != zero signals.
 status='NOT_TESTABLE_MISSING_CONTEXT' if len(curr)==0 else (
   'PARTIAL_CONTEXT_COVERAGE' if len(curr)<90 else 'TESTED_SHADOW_ONLY')
 summary.append(dict(date=row['date'],time_tr=row['label'],
    status=status,observed_shadow_candles=len(curr),
    recovery_shadow_candidates=len(ready),
    candidate_times_tr=[z['ts_tr'][11:19] for z in ready],
    score_floor_candidates=sum(isinstance(z['score'],(float,int)) and z['score']>=.495 for z in curr),
    no_order_authority=True))
dst=ROOT/'LONG1_RECOVERY_PROFILE_C_PREREGISTERED_WINDOWS_NOV03_13_20261115.json'
payload=dict(schema='LONG1_FROZEN_HOLDOUT_V1',profile_sha256=hashlib.sha256(
 Path('research/long1_recovery_regime_frozen_v1.py').read_bytes()).hexdigest(),
 source='binance_futures_public_klines_and_redis_existing_shadow',
 source_note='Historical 3m 5m 15m closed candles and existing recorded 1m/flow/whale shadow, no source replay when absent',
 training_labels_used=False,live_authority=False,research_only=True,
 selected_windows=summary,
 evidence_total=len(detail),source_kline_counts={k:len(v) for k,v in bars.items()})
dst.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
for z in summary:print(z['date'],z['time_tr'],z['status'],'source3m',z['observed_shadow_candles'],'score>=.495',z['score_floor_candidates'],'frozen_ready',z['recovery_shadow_candidates'],'times',','.join(z['candidate_times_tr']))
print('OVERALL',len(summary),'WINDOWS',collections.Counter(z['status'] for z in summary),
 'TOTAL_RECOVERY_SHADOW',sum(z['recovery_shadow_candidates'] for z in summary),'OUTPUT',str(dst))
