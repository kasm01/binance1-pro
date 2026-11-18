"""Exact legacy candidate->top5->intent join using retained Redis records.

No new-model trace invented. Uses source_top5_id, raw.candidate_id,
raw._source_stream_id and literal candidate Redis source. No score/time join.
READ-ONLY, bounded samples, no account/order APIs, no raw ID output.
"""
from __future__ import annotations
import json,redis
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

r=redis.Redis(host='127.0.0.1',port=6379,decode_responses=True,
              socket_connect_timeout=2,socket_timeout=4)
names=['candidates_stream_long1','top5_stream_long1','trade_intents_stream_long1',
       'exec_events_stream_long1']
records={}
for name in names:
    rows=r.xrevrange(name,count=3500)
    data={}
    for sid,fields in rows:
        try:
            entry=json.loads(fields.get('json') or '{}')
            if isinstance(entry,dict):data[sid]=entry
        except (ValueError,TypeError):pass
    records[name]=data
candidates,top_batches,intent_batches,exec_batches=(records[x] for x in names)
stats=Counter()
daily=Counter()
reason=Counter()
tr=ZoneInfo('Europe/Istanbul')
examples=[]
exact_intent_stream_ids={}
for intent_mid,pkg in intent_batches.items():
    top_mid=pkg.get('source_top5_id')
    top=top_batches.get(top_mid)
    for item in pkg.get('items') or []:
        if not isinstance(item,dict) or str(item.get('symbol','')).upper()!='NEARUSDT':
            continue
        stats['long1_intent_items']+=1
        time_str=item.get('ts_utc') or pkg.get('ts_utc') or ''
        try:
            day=datetime.fromisoformat(time_str.replace('Z','+00:00')).astimezone(tr).date().isoformat()
        except (ValueError,TypeError):day='UNKNOWN'
        in_window='2026-11-12'<=day<='2026-11-14'
        if in_window:stats['three_day_intent_items']+=1
        raw=item.get('raw')
        if not isinstance(raw,dict):
            reason['raw_missing']+=1;continue
        candidate_id=raw.get('candidate_id')
        cid=raw.get('_source_stream_id')
        if not isinstance(candidate_id,str) or not isinstance(cid,str):
            reason['raw_candidate_identity_missing']+=1;continue
        if not isinstance(top,dict):
            reason['source_top5_not_retained']+=1;continue
        matches=[x for x in (top.get('items') or [])
                 if isinstance(x,dict) and x.get('candidate_id')==candidate_id
                 and x.get('_source_stream_id')==cid]
        if len(matches)!=1:
            reason['top5_selected_candidate_not_unique']+=1;continue
        origin=candidates.get(cid)
        if not isinstance(origin,dict):
            reason['candidate_source_not_retained']+=1;continue
        if origin.get('candidate_id')!=candidate_id:
            reason['candidate_uuid_conflict']+=1;continue
        if (origin.get('symbol')!=item.get('symbol')
            or origin.get('side')!=item.get('side')
            or origin.get('interval')!=item.get('interval')):
            reason['candidate_identity_conflict']+=1;continue
        stats['exact_candidate_top5_intent']+=1
        exact_intent_stream_ids[(intent_mid,item.get('intent_id'))]=day
        if in_window:
            daily[day]+=1
            stats['three_day_exact_candidate_top5_intent']+=1
            if len(examples)<4:
                examples.append({'day':day,'status':'EXACT_CANDIDATE_TO_INTENT',
                  'model_parent':'UNLINKED_LEGACY','exchange_fill':'NOT_VERIFIED'})
        # Never infer producer model from absence or score/time.
        if origin.get('model_evaluation_id') and origin.get('parent_signal_event_id'):
            stats['source_candidate_with_model_fields']+=1
# Exact IntentBridge source_intents_id plus item.intent_id mapping.
# This is an execution INTENT, not authenticated exchange order/fill.
for _,batch in exec_batches.items():
    source=batch.get('source_intents_id')
    for exec_item in batch.get('items') or []:
        if not isinstance(exec_item,dict) or exec_item.get('symbol')!='NEARUSDT':
            continue
        stats['exec_intent_items']+=1
        matched_day=exact_intent_stream_ids.get((source,exec_item.get('intent_id')))
        if matched_day is not None:
            stats['exact_candidate_intent_exec_intent']+=1
            if '2026-11-12'<=matched_day<='2026-11-14':
                stats['three_day_exact_candidate_intent_exec_intent']+=1
result={
  'schema':'long1_legacy_candidate_top5_intent_exact_readonly.v1',
  'sampled_stream_records':{k:len(v) for k,v in records.items()},
  'long1_intent_items':stats['long1_intent_items'],
  'exact_candidate_top5_intent':stats['exact_candidate_top5_intent'],
  'three_day_intent_items':stats['three_day_intent_items'],
  'three_day_exact_candidate_top5_intent':stats['three_day_exact_candidate_top5_intent'],
  'three_day_exact_daily':dict(sorted(daily.items())),
  'exec_intent_items':stats['exec_intent_items'],
  'exact_candidate_intent_exec_intent':stats['exact_candidate_intent_exec_intent'],
  'three_day_exact_candidate_intent_exec_intent':
          stats['three_day_exact_candidate_intent_exec_intent'],
  'exchange_order_fills_verified':False,
  'unlinked_reasons':dict(reason),
  'model_parent_from_new_trace_available':stats['source_candidate_with_model_fields'],
  'example_links_anonymized':examples,
  'read_only':True,'no_heuristic_attribution':True,
  'no_production_redis_writes':True,'no_exchange_orders':True
}
print(json.dumps(result,sort_keys=True))
