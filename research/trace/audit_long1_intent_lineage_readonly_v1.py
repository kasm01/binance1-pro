"""Snapshot EXACT intent/exec/outcome lineage from existing Redis streams.
READ-ONLY, no added collectors, no signal->model extrapolation, bounded reads.
Reports only aggregate counts and a handful of anonymized examples.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,redis,hashlib
from research.trace.long1_trace_contract_v1 import event,VERSION
ROOT=Path('/home/kasm920/binance1-pro')
TR=timezone(timedelta(hours=3))
R=redis.Redis(host='127.0.0.1',port=6379,decode_responses=True,
 socket_timeout=3,socket_connect_timeout=3)
R.ping()
N=5000
sources=('signals_stream_long1','candidates_stream_long1','trade_intents_stream_long1',
'exec_events_stream_long1','shadow:telemetry:position_outcome')
sets={}
for key in sources:
 rows=R.xrevrange(key,count=N)
 records=[]
 for sid,fields in rows:
  try:
   j=json.loads(fields.get('json') or '{}')
   if isinstance(j,dict):records.append((sid,j))
  except(ValueError,TypeError):pass
 sets[key]=records
 print('SOURCE',key,'sampled',len(records),'length',R.xlen(key))
intent_stream={k:v for k,v in sets['trade_intents_stream_long1']}
# Intent occurrence by ID: source transport.
intents={}
for stream_id,payload in sets['trade_intents_stream_long1']:
 for item in payload.get('items',[]):
  if not isinstance(item,dict):continue
  iid=item.get('intent_id')
  if not isinstance(iid,str) or not iid:continue
  if str(item.get('symbol','')).upper()!='NEARUSDT':continue
  intents.setdefault(iid,[]).append((stream_id,item))
ex_list=[]
for stream_id,payload in sets['exec_events_stream_long1']:
 source_id=payload.get('source_intents_id')
 matching_source=source_id in intent_stream
 for item in payload.get('items',[]):
  if not isinstance(item,dict):continue
  iid=item.get('intent_id')
  if not isinstance(iid,str) or not iid:continue
  if str(item.get('symbol','')).upper()!='NEARUSDT':continue
  sources_for_id=intents.get(iid,[])
  exact=matching_source and any(sid==source_id for sid,_ in sources_for_id)
  at_ms=int(stream_id.split('-')[0])
  row=event(stream='exec_events_stream_long1',stream_id=stream_id,at_ms=at_ms,
      stage='EXECUTION_INTENT',state='OBSERVED',
      reason='exec_intent_observed_not_order',
      kind='EXACT_INTENT' if exact else 'UNLINKED',intent_id=iid)
  ex_list.append((iid,source_id,matching_source,exact,row))
# outcome is "shadow" but order_id and actual position-open metadata are present:
# NOT independently verified against Binance API.
outcome=[]
for stream_id,payload in sets['shadow:telemetry:position_outcome']:
 iid=payload.get('intent_id')
 if str(payload.get('symbol','')).upper()!='NEARUSDT' or not isinstance(iid,str) or not iid:continue
 order_id=payload.get('open_order_id')
 outcome.append((iid,stream_id,bool(order_id),payload.get('position_open_at_ms')))
exact_ids={iid for iid,_,_,x,_ in ex_list if x}
matched_outcomes=[x for x in outcome if x[0] in exact_ids]
# Do not equate model event_id to candidate_id without explicit upstream parent.
signals=sets['signals_stream_long1']
signal_event_ids={e.get('event_id') for _,e in signals if isinstance(e.get('event_id'),str)}
candidates=sets['candidates_stream_long1']
cand_upstream_explicit=0
for _,v in candidates:
 # Only the explicit raw/lineage parent if documented; incidental score equality not proof
 for k in ('source_event_id','parent_signal_event_id','parent_event_id'):
  if isinstance(v.get(k),str) and v[k] in signal_event_ids:
   cand_upstream_explicit+=1;break
stats=dict(schema='long1_intent_lineage_audit_v1',
 read_only=True,window='current_redis_retention_not_guaranteed_11_to_15_only',
 source_lengths={k:R.xlen(k) for k in sources},
 sampled_records={k:len(v) for k,v in sets.items()},
 unique_intent_ids=len(intents),exec_intent_items=len(ex_list),
 exec_intent_exact_source_id_and_intent_id=sum(x[3] for x in ex_list),
 exec_intent_unlinked=sum(not x[3] for x in ex_list),
 unique_verified_exec_intent_ids=len(exact_ids),
 outcome_records_with_intent=len(outcome),
 outcome_records_joining_exact_exec_intent=len(matched_outcomes),
 joined_outcomes_with_logged_order_id=sum(bool(x[2]) for x in matched_outcomes),
 signal_to_candidate_explicit_event_id_matches=cand_upstream_explicit,
 production_model_close_id_bridge_proven=False,
 order_fills_independently_exchange_verified=False,
 stream_data_truncated_by_count_limit=any(R.xlen(k)>N for k in sources),
 max_records_per_stream=N,
 notes=[
  'Exact exec->intent is based on source_intents_id pointing to a specific trade_intents stream id AND identical item intent_id.',
  'Outcome matching by intent_id is exact identifier correlation, NOT independently proven exchange fills; outcomes are shadow telemetry.',
  'No causal mapping from upstream model close_id to signal and candidate is established; no heuristic score/time promoted to exact identity.',
  'Stream retention differs from full 11-15 historical logs and must not be treated as comprehensive retrospective order accounting.'],
 aggregate_only=True)
dest=ROOT/'research/results/LONG1_INTENT_LINEAGE_READONLY_20261116.json'
dest.write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n')
print('COUNTS',json.dumps({k:v for k,v in stats.items() if k in (
  'unique_intent_ids','exec_intent_items','exec_intent_exact_source_id_and_intent_id',
  'exec_intent_unlinked','outcome_records_with_intent',
  'outcome_records_joining_exact_exec_intent',
  'joined_outcomes_with_logged_order_id',
  'signal_to_candidate_explicit_event_id_matches')},indent=2))
print('SAVED',dest)
