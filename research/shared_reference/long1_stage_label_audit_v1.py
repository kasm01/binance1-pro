"""Read-only 11–15 Nov LONG1 model/entry funnel vs human research intervals.

The labels are used for diagnostics only, not model input or live authorization.
Model score records from append-only logs, shadow market-context Redis only.
"""
from __future__ import annotations
import bisect,collections,datetime,json,re
from pathlib import Path
import redis
from research.shared_reference.window_reference_reader_v1 import load_reference,lookup
ROOT=Path('/home/kasm920/binance1-pro')
REF=load_reference();TZ=datetime.timezone(datetime.timedelta(hours=3))
r=redis.Redis(decode_responses=True,socket_timeout=4)
lower=int(datetime.datetime(2026,11,10,21,tzinfo=datetime.timezone.utc).timestamp()*1000)
upper=int(datetime.datetime(2026,11,15,21,tzinfo=datetime.timezone.utc).timestamp()*1000)
shadow={}
for sid,fields in r.xrange('telemetry:long1:context_adaptive_gate:v1',f'{lower}-0',f'{upper}-99999'):
 try:
  z=json.loads(fields.get('json') or '{}')
  cid=int(z['close_id'])
  shadow[cid]=dict(
   pass_shadow=z.get('pass') is True,
   routing_changed=z.get('routing_changed') is True,
   signed_flow=z.get('t15_signed_ratio'),
   score=z.get('score'),
   threshold=z.get('normal_threshold'),
   oi_direction=z.get('oi_direction'))
 except (ValueError,TypeError,KeyError):pass
candles={}
event_counts=collections.Counter()
score_pattern=re.compile(r'close_id=(\d+) p_used=([\d.]+) long_thr=([\d.]+) side=(\w+)')
for filename in ('logs/main.log.3','logs/main.log.2','logs/main.log.1','logs/main.log'):
 path=ROOT/filename
 if not path.exists():continue
 for line in path.open(errors='replace'):
  try:
   utc=datetime.datetime.strptime(line[:19],'%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
  except ValueError:continue
  tr=utc.astimezone(TZ)
  if tr<datetime.datetime(2026,11,11,tzinfo=TZ) or tr>=datetime.datetime(2026,11,16,tzinfo=TZ):
   continue
  tag=lookup(tr,dataset=REF)['long']
  event_counts[(tr.date().isoformat(),tag,'LOG_ALL')]+=1
  if '[MODEL-SCORE]' in line:
   m=score_pattern.search(line)
   if m:
    cid=int(m[1]);candles[cid]=dict(time_tr=tr.isoformat(),score=float(m[2]),
       rolling_threshold=float(m[3]),live_model_long=(m[4]=='long'),label=tag,
       close_id=cid)
  if '[EXEC][ENTRY-DECISION]' in line:
   m=re.search(r'action=(\w+) reason=([^\s]+)',line)
   if m:event_counts[(tr.date().isoformat(),tag,'ENTRY_'+m[1].upper())]+=1
  if '[EXEC][CONTRA-GUARD]' in line:
   m=re.search(r'action=(\w+)',line)
   event_counts[(tr.date().isoformat(),tag,'CONTRA_'+(m[1].upper() if m else 'UNKNOWN'))]+=1
  if '[EXEC][PENDING-RECHECK]' in line:
   m=re.search(r'status=(\w+)',line)
   event_counts[(tr.date().isoformat(),tag,'PENDING_'+(m[1].upper() if m else 'UNKNOWN'))]+=1
groups=collections.defaultdict(list)
for cid,v in candles.items():
 x=dict(v)
 x['shadow_available']=cid in shadow
 x['shadow_pass']=shadow[cid]['pass_shadow'] if cid in shadow else None
 x['shadow_routing_changed']=shadow[cid]['routing_changed'] if cid in shadow else None
 groups[(v['time_tr'][:10],v['label'])].append(x)
daily=[]
for day in ('2026-11-11','2026-11-12','2026-11-13','2026-11-14','2026-11-15'):
 for label in ('LONG_TARGET','LONG_AVOID','CONFLICT_NO_TRADE','UNLABELLED'):
  rows=groups[(day,label)]
  daily.append(dict(day=day,reference_label=label,scored_3m_bars=len(rows),
   live_model_long=sum(z['live_model_long'] for z in rows),
   fixed_0495_candidate=sum(z['score']>=.495 for z in rows),
   shadow_market_context_available=sum(z['shadow_available'] for z in rows),
   shadow_context_pass=sum(z['shadow_pass'] is True for z in rows),
   entry_open_decisions=event_counts[(day,label,'ENTRY_OPEN')],
   entry_block_decisions=event_counts[(day,label,'ENTRY_BLOCK')],
   entry_pending_decisions=event_counts[(day,label,'ENTRY_PENDING')],
   contra_pending=event_counts[(day,label,'CONTRA_PENDING')],
   pending_cleared=event_counts[(day,label,'PENDING_CLEARED')]))
out=ROOT/'research/results/LONG1_SHARED_REFERENCE_STAGE_COUNTS_20261111_15_V1.json'
out.write_text(json.dumps(dict(schema='long1_stage_counts_shared_reference_v1',
    no_order_authority=True,read_only=True,model_score_count_is_not_trade_count=True,
    notes='Model bars keyed by close_id, log event decisions may repeat across 1m retries; no as-of full execution replay',
    daily=daily),ensure_ascii=False,indent=2)+'\n')
for row in daily:
 if row['reference_label']=='UNLABELLED':continue
 print(row['day'],row['reference_label'],'bars',row['scored_3m_bars'],
 'live_model',row['live_model_long'],'p495',row['fixed_0495_candidate'],
 'shadow_pass',row['shadow_context_pass'],'entryOPEN',row['entry_open_decisions'],
 'entryBLOCK',row['entry_block_decisions'],'entryPENDING',row['entry_pending_decisions'],
 'contraPENDING',row['contra_pending'])
print('SAVED',out,'TOTAL_MODEL',len(candles))
