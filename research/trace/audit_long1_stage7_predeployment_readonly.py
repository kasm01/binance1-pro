"""Predeployment coverage in current Redis retention, never infers from clock.

Read-only with bounded per-stream xrevrange and aggregate-only output.
"""
import json,redis
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
r=redis.Redis(host='127.0.0.1',port=6379,decode_responses=True,
    socket_connect_timeout=2,socket_timeout=4)
streams={
 'candidates_stream_long1':r.xrevrange('candidates_stream_long1',count=3000),
 'top5_stream_long1':r.xrevrange('top5_stream_long1',count=3000),
 'trade_intents_stream_long1':r.xrevrange('trade_intents_stream_long1',count=3000),
 'exec_events_stream_long1':r.xrevrange('exec_events_stream_long1',count=3000),
}
result={"schema":"long1_stage7_predeployment_current_retention",
        "read_only":True,"production_redis_writes":0,
        "sample_counts":{k:len(v) for k,v in streams.items()},
        "top5_items_with_original_candidate_id":0,
        "top5_items_with_original_candidate_stream_id":0,
        "intent_items_with_new_source_candidate_id":0,
        "intent_items_with_new_source_candidate_stream_id":0,
        "intent_items_with_new_model_evaluation_id":0,
        "exec_items_with_original_intent_id":0,
        "historic_exact_model_to_intent_verifiable":0,
        "no_live_orders":True}
TZ=ZoneInfo("Europe/Istanbul")
historical=Counter()
for stream,entries in streams.items():
 for _,data in entries:
  try:
   j=json.loads(data.get("json") or '{}')
   if not isinstance(j,dict):continue
  except (ValueError,TypeError):continue
  items=j.get("items")
  if not isinstance(items,list):continue
  for item in items:
   if not isinstance(item,dict):continue
   if stream=='top5_stream_long1':
    if item.get("candidate_id"):result['top5_items_with_original_candidate_id']+=1
    if item.get("_source_stream_id"):result['top5_items_with_original_candidate_stream_id']+=1
   elif stream=='trade_intents_stream_long1':
    if item.get("source_candidate_id"):result['intent_items_with_new_source_candidate_id']+=1
    if item.get("source_candidate_stream_id"):result['intent_items_with_new_source_candidate_stream_id']+=1
    if item.get("model_evaluation_id"):result['intent_items_with_new_model_evaluation_id']+=1
    if str(item.get('symbol','')).upper()=='NEARUSDT':
     text=str(item.get("ts_utc") or j.get("ts_utc") or "")
     try:
      day=datetime.fromisoformat(text.replace('Z','+00:00')).astimezone(TZ).date().isoformat()
      if '2026-11-12'<=day<='2026-11-14':historical[day]+=1
     except(ValueError,TypeError):pass
   elif stream=='exec_events_stream_long1':
    if item.get("intent_id"):result['exec_items_with_original_intent_id']+=1
result['historical_20261112_14_intent_items_in_current_sample']=dict(historical)
print(json.dumps(result,sort_keys=True))
