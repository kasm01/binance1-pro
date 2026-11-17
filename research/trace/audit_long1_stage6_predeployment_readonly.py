"""Before-service-restart read-only source/provenance coverage check.

Reads no more than 3000 signal / 2000 candidate JSON rows; aggregates only.
Old records MUST NOT be retroactively assigned newly introduced model IDs.
"""
from __future__ import annotations
import json,redis
from research.trace.long1_model_candidate_lineage_verifier_v2 import verify
r=redis.Redis(host='127.0.0.1',port=6379,decode_responses=True,
              socket_connect_timeout=2,socket_timeout=5)
signals={}
for mid,fields in r.xrevrange('signals_stream_long1',count=3000):
    try:
        row=json.loads(fields.get('json') or '{}')
        if isinstance(row,dict):signals[mid]=row
    except (ValueError,TypeError):pass
candidates=[]
for mid,fields in r.xrevrange('candidates_stream_long1',count=2000):
    try:
        row=json.loads(fields.get('json') or '{}')
        if isinstance(row,dict):candidates.append((mid,row))
    except (ValueError,TypeError):pass
out={"schema":"long1_stage6_predeployment_readonly",
     "production_redis_writes":0,"signals_sampled":len(signals),
     "candidates_sampled":len(candidates),"exact_new_lineage":0,
     "candidate_records_with_explicit_source_stream":0,
     "candidate_records_with_explicit_model_evaluation":0,
     "candidate_records_unlinked_in_sample":0,
     "live_order_authorized":False}
for _,c in candidates:
    if 'source_signal_stream_id' in c:out['candidate_records_with_explicit_source_stream']+=1
    if 'model_evaluation_id' in c:out['candidate_records_with_explicit_model_evaluation']+=1
    parent_id=c.get('source_signal_stream_id')
    signal=signals.get(parent_id)
    if signal:
        proof=verify(signal_stream='signals_stream_long1',
                     signal_stream_id=parent_id,signal=signal,candidate=c)
        if proof['state']=='EXACT_SOURCE_AND_EVALUATION':
            out['exact_new_lineage']+=1
        else:out['candidate_records_unlinked_in_sample']+=1
print(json.dumps(out,sort_keys=True))
