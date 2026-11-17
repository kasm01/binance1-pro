"""Retrospective LONG1 decision funnel correlation, READ-ONLY.

Logs do not consistently attach MODEL close_id to entry decisions / order opens.
Score/time matching is APPROXIMATE. Store approximate trace links separately
from exact exchange ID / model close_id evidence and never claim causal linkage.
No live changes, no Redis writes, no secret material exported.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import Counter,defaultdict
from bisect import bisect_right
import json,re,hashlib
ROOT=Path('/home/kasm920/binance1-pro')
target=json.load(open(ROOT/'research/results/LONG1_MARKET_CONTEXT_V2_103_ASOF_20261111_15.json'))
assert len(target['full_results'])==103
model=sorted(target['full_results'],key=lambda z:z['ts_tr'])
utc=timezone.utc;tr=timezone(timedelta(hours=3))
lo=int(datetime(2026,11,11,0,tzinfo=tr).timestamp()*1000)
hi=int(datetime(2026,11,16,0,tzinfo=tr).timestamp()*1000)
files=[ROOT/f for f in ('logs/main.log.3','logs/main.log.2','logs/main.log.1','logs/main.log')]
pat=re.compile(r'(?:score|resolved_score)=([-+0-9.eE]+)')
events=[]
for file in files:
 if not file.is_file():continue
 for line in file.open(errors='replace'):
  if not ('[EXEC][ENTRY-DECISION]' in line or
       '[EXEC][OPEN][SCORE]' in line or
       '[EXEC][PENDING-RECHECK]' in line or
       '[EXEC][CONTRA-GUARD]' in line or
       '[EXEC][ORDER] OPEN OK' in line or
       '[EXEC][ORDER][POLL]' in line or
       '[EXEC][OPEN][COMMIT]' in line or
       '[EXEC][ORDER][PREP]' in line):
   continue
  has_explicit_symbol='symbol=NEARUSDT' in line
  if not has_explicit_symbol and '[EXEC][ENTRY-DECISION]' not in line:continue
  try:dt=datetime.strptime(line[:19],'%Y-%m-%d %H:%M:%S').replace(tzinfo=utc)
  except ValueError:continue
  ms=int(dt.timestamp()*1000)
  if not lo<=ms<hi:continue
  k='ENTRY_DECISION' if '[EXEC][ENTRY-DECISION]' in line else (
    'OPEN_SCORE' if '[EXEC][OPEN][SCORE]' in line else
    'PENDING_RECHECK' if '[EXEC][PENDING-RECHECK]' in line else
    'CONTRA_GUARD' if '[EXEC][CONTRA-GUARD]' in line else
    'ORDER_OPEN_SUBMITTED' if '[EXEC][ORDER] OPEN OK' in line else
    'ORDER_POLL' if '[EXEC][ORDER][POLL]' in line else
    'OPEN_COMMIT' if '[EXEC][OPEN][COMMIT]' in line else 'ORDER_PREP')
  score=None; match=pat.search(line)
  if match:
   try:score=float(match[1])
   except ValueError:pass
  action=re.search(r'action=(\w+)',line)
  reason=re.search(r'reason=([^\s]+)',line)
  status=re.search(r'status=(\w+)',line)
  order_id=re.search(r'\"orderId\"\s*:\s*(\d+)',line)
  out=dict(kind=k,ts_ms=ms,ts_tr=dt.astimezone(tr).isoformat(),
       source_symbol_explicit=has_explicit_symbol,
       score=score,action=action[1] if action else None,
       reason=reason[1] if reason else None,status=status[1] if status else None,
       order_id=order_id[1] if order_id else None)
  events.append(out)
events.sort(key=lambda a:a['ts_ms'])
models=[]
for z in model:
 models.append(dict(close_id=z['close_id'],ts_ms=int(datetime.fromisoformat(z['ts_tr']).timestamp()*1000),
  score=None,reference_label=z['reference_label'],market_decision=z['decision'],
  market_regime=z['regime']))
# only same MODEL LONG scored signals are present; look up exact p_used from source file,
# not only V2 summary
score_index={int(x['cid']):float(x['score']) for x in json.load(open(
 ROOT/'research/results/LONG1_TRUE_MODEL_LONG_REGIME_SHADOW_V1_20261111_15.json'))['full_results']}
for m in models:m['score']=score_index[m['close_id']]
mts=[z['ts_ms'] for z in models]
approx={}
unlinked=[]
for ev in events:
 # 3m model LONG score can be held for a couple of minutes across retry loops.
 # match only prior model within 15m and a narrow score delta; no causal proof.
 i=bisect_right(mts,ev['ts_ms'])-1
 if ev['score'] is None:
  unlinked.append(ev);continue
 candidates=[]
 for j in range(max(0,i-8),i+1):
  m=models[j]
  age_sec=(ev['ts_ms']-m['ts_ms'])/1000
  if 0<=age_sec<=900:
   delta=abs(ev['score']-m['score'])
   if delta<=0.00015:
    candidates.append((delta,age_sec,m))
 if not candidates:
  unlinked.append(ev);continue
 candidates.sort(key=lambda x:(x[0],x[1]))
 best=candidates[0]
 matched=best[2]['close_id']
 ev=dict(ev,match_quality='HEURISTIC_SCORE_AND_TIME_NOT_PROVEN',
   model_close_id_candidate=matched,
   score_difference=round(best[0],8),lag_seconds=round(best[1],1),
   competing_model_matches=len(candidates))
 approx.setdefault(matched,[]).append(ev)
summary=[]
for m in models:
 es=approx.get(m['close_id'],[])
 ed=[z for z in es if z['kind']=='ENTRY_DECISION']
 kinds=Counter(z['kind'] for z in es)
 status=Counter((z['action'],z['reason']) for z in ed)
 summary.append(dict(**m,approx_events=len(es),
  approximate_entry_actions=dict(Counter(z['action'] or 'UNKNOWN' for z in ed)),
  approximate_entry_reasons=[dict(action=k[0],reason=k[1],n=v) for k,v in status.most_common()],
  approx_event_kinds=dict(kinds),
  attribution='MODEL_ONLY' if not es else 'HEURISTIC_SCORE_TIME',
  linked_entry_log_events=ed[:20],
  # WARNING: OPEN_COMMIT has no score so not included here
  actual_fill_verified_for_this_close_id=False))
kinds_all=Counter(z['kind'] for z in events)
pairs=Counter(z['action'] for z in events if z['kind']=='ENTRY_DECISION')
known_order_ids=sorted({e['order_id'] for e in events if e['order_id'] is not None})
report=dict(schema='long1_funnel_trace_readonly_v1',
 read_only=True,model_long_event_count=len(model),
 models_with_heuristic_score_link=sum(z['approx_events']>0 for z in summary),
 model_events_with_no_entry_trace=sum(z['approx_events']==0 for z in summary),
 log_event_counts=dict(kinds_all),
 entry_action_counts=dict(pairs),
 log_events_without_heuristic_model_match=len(unlinked),
 note='Only MODEL_SCORE has close_id. ENTRY_DECISION lacks symbol field so candidate source attribution is tentative from LONG1 executor log.  ENTRY_DECISION has score but no close_id; mapping by lag and score is probabilistic. ORDER/POLL/COMMIT are independently counted and not assigned to a model close_id. No reliable linkage from model to fill without adding correlation fields in future telemetry.',
 distinct_open_order_ids_in_logs=len(known_order_ids),
 model_event_trace=summary,
 unmatched_log_events=unlinked[:100])
out=ROOT/'research/results/LONG1_FUNNEL_TRACE_READONLY_V1_20261111_15.json'
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('MODEL_LONGS',len(model),'HEURISTIC_LINKED',report['models_with_heuristic_score_link'],'NO_LINK',report['model_events_with_no_entry_trace'])
print('LOG_KINDS',dict(kinds_all),'ENTRY_ACTIONS',dict(pairs),'UNLINKED_LOG',len(unlinked))
print('MATCHED_SCORE_SAMPLE')
for item in summary:
 if item['approx_events']:
  print(item['ts_ms'],item['close_id'],item['market_decision'],item['approx_events'],
   item['approximate_entry_actions'],item['approximate_entry_reasons'][:2])
print('FILE',out)
