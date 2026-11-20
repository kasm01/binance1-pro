"""Stage18 LONG1 one-shot forward-only, bounded, opt-in, read-only audit.

Initialize cursor with latest IDs while services are OFF. Any subsequent
audit only counts NEW intent batches (XRANGE exclusive), resolving exact
source parents from bounded retained signal and candidate streams. No
heuristic timestamp/score/price matching. No new orders, Redis writes,
services, third-party API, subscriptions or background polling.
By default all CLI actions are disabled. Cursor advances only with
explicit --advance, and after a successful output.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from collections import Counter
from research.trace.audit_long1_stage17_readonly_source_chain_v1 import (
    STREAMS,decode,audit
)
ROOT=Path(__file__).resolve().parents[2]
LOCAL=ROOT/'research/local_market_data/long1_stage18'
CURSOR=LOCAL/'forward_cursor.json'
RESULTS=ROOT/'research/results'
SCHEMA='long1_stage18_forward_cursor.v1'
def _stream_id(v):
    if not isinstance(v,str):raise ValueError('bad_stream_id')
    p=v.split('-')
    if len(p)!=2 or any(not x.isdigit() for x in p):
        raise ValueError('bad_stream_id')
    return v
def _key(v):
    return tuple(int(x) for x in _stream_id(v).split('-'))
def latest_ids(reader):
    result={}
    for stream in STREAMS:
        one=reader.xrevrange(stream,count=1)
        result[stream]=_stream_id(one[0][0] if one else '0-0')
    return result
def initial_state(ids):
    return {'schema':SCHEMA,'start_from_stream_ids':{
        k:_stream_id(ids[k]) for k in STREAMS},
        'last_seen_intent_id':_stream_id(ids[STREAMS[2]]),
        'not_production_redis_state':True,'no_orders_authorized':True}
def audit_since(reader,state,limit=3000):
    if state.get('schema')!=SCHEMA:raise ValueError('cursor_wrong_schema')
    if limit<100 or limit>5000:raise ValueError('invalid_limit')
    baseline=state['start_from_stream_ids']
    for s in STREAMS:_stream_id(baseline[s])
    start=_stream_id(state['last_seen_intent_id'])
    if _key(start)<_key(baseline[STREAMS[2]]):
        raise ValueError('cursor_before_baseline')
    # Read only strictly newer intent batch records, never old ones.
    new=reader.xrange(STREAMS[2],min='('+start,max='+',count=limit+1)
    truncated=len(new)>limit
    if truncated:new=new[:limit]
    # Avoid scanning thousands of old parent events when no new Intent.
    # All 3 stream lengths still checked cheaply for basic coverage.
    lengths={s:reader.xlen(s) for s in STREAMS}
    if new:
        # Need fully retained parents even if published before the intent.
        # Bound upstream data; no inference for missing/trimmed ancestors.
        sources={STREAMS[0]:decode(reader.xrevrange(STREAMS[0],count=limit)),
                 STREAMS[1]:decode(reader.xrevrange(STREAMS[1],count=limit)),
                 STREAMS[2]:decode(new)}
    else:
        sources={s:[] for s in STREAMS}
    result=audit(sources,lengths,limit=limit)
    new_last=start
    if new:new_last=_stream_id(new[-1][0])
    result.update({'schema':'long1_stage18_forward_only_readonly_audit.v1',
        'cursor_before_intent_id':start,
        'cursor_after_intent_id':new_last,
        'new_intent_batch_records':len(new),
        'max_records_exceeded':truncated,
        'baseline_stream_ids':baseline,
        'no_historical_intent_recount':True,
        'upstream_parent_retention_limit':limit,
        'forward_only_new_intents':True,'production_redis_writes':0,
        'live_order_authorized':False,
        'no_start_of_services':True})
    updated=dict(state,last_seen_intent_id=new_last)
    return result,updated
def load(path):
    if not path.is_file():raise ValueError('cursor_missing_init_required')
    return json.loads(path.read_text())
def atomic_write(path,obj):
    # Explicit local cursor/report only. Same-volume atomic replacement.
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    temp.replace(path)
def main():
    p=argparse.ArgumentParser()
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--initialize-cursor',action='store_true')
    modes.add_argument('--audit-forward',action='store_true')
    p.add_argument('--advance',action='store_true')
    p.add_argument('--max-records',type=int,default=3000)
    a=p.parse_args()
    if not a.initialize_cursor and not a.audit_forward:
        print('DISABLED: explicit --initialize-cursor or --audit-forward required');return 0
    if a.advance and not a.audit_forward:
        p.error('--advance only with --audit-forward')
    if a.max_records<100 or a.max_records>5000:p.error('max-records invalid')
    if a.initialize_cursor and CURSOR.exists():
        p.error('cursor already exists; never silently erase forward history')
    import redis
    r=redis.Redis(host='127.0.0.1',port=6379,decode_responses=True,
                  socket_timeout=4,socket_connect_timeout=3)
    if a.initialize_cursor:
        state=initial_state(latest_ids(r))
        atomic_write(CURSOR,state)
        print(json.dumps({'status':'INITIALIZED','cursor':state['last_seen_intent_id'],
           'streams':state['start_from_stream_ids'],
           'redis_writes':0,'exchange_orders':0},sort_keys=True))
        return 0
    state=load(CURSOR)
    report,updated=audit_since(r,state,limit=a.max_records)
    if a.advance and report['max_records_exceeded']:
        p.error('batch truncated; cannot advance')
    if a.advance:
        # Never move cursor before successful local report persistence.
        atomic_write(RESULTS/'LONG1_STAGE18_FORWARD_ONLY_LAST_AUDIT_20261120.json',report)
        atomic_write(CURSOR,updated)
    print(json.dumps({k:v for k,v in report.items() if k not in
       ('sample_only_no_personal_payload','missing_reason_counts')},sort_keys=True))
    return 0
if __name__=='__main__':raise SystemExit(main())
