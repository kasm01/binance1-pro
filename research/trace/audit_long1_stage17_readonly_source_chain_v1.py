"""Bounded, one-shot, opt-in, read-only LONG1 SOURCE CHAIN research audit.

No production Redis writes, no service, no Binance calls, no on-chain orders.
No missing parent is guessed from time, price, score or Top5 stream IDs.
Does not authorize reentry. Trade intents are accounted only as observed
records, even if parent model is missing.
"""
from __future__ import annotations
import argparse,json,os
from collections import Counter
from pathlib import Path
from collections.abc import Mapping
from orchestration.trace.long1_fresh_intent_source_chain_v1 import exact_new_chain
ROOT=Path(__file__).resolve().parents[2]
STREAMS=('signals_stream_long1','candidates_stream_long1','trade_intents_stream_long1')
def decode(rows):
 result=[]
 for sid,fields in rows:
  try:
   p=json.loads(fields.get('json') or '{}')
   if isinstance(p,dict):result.append((sid,p))
  except (ValueError,TypeError,AttributeError):
   pass
 return result
def audit(records,source_lengths=None,limit=3000):
 """Pure as-of retained-stream cross-join by explicit IDs only."""
 signals=dict(records.get(STREAMS[0],()))
 candidates=dict(records.get(STREAMS[1],()))
 batches=list(records.get(STREAMS[2],()))
 verdicts=Counter();summary=Counter()
 missing=Counter();examples=[]
 for top_id,batch in batches:
  for it in batch.get('items',[]) if isinstance(batch.get('items'),list) else ():
   if not isinstance(it,Mapping) or it.get('symbol')!='NEARUSDT' or it.get('side')!='long':
    continue
   summary['trade_intents_observed']+=1
   iid=it.get('intent_id')
   cid=it.get('source_candidate_stream_id')
   sid=it.get('source_signal_stream_id')
   if not isinstance(iid,str) or not iid:
    missing['intent_id']+=1;continue
   if not isinstance(cid,str) or cid not in candidates:
    missing['candidate_source_stream_id_present_in_retention']+=1
    verdicts['NOT_PROVEN']+=1;continue
   if not isinstance(sid,str) or sid not in signals:
    missing['signal_source_stream_id_present_in_retention']+=1
    verdicts['NOT_PROVEN']+=1;continue
   sig=signals[sid];cand=candidates[cid]
   result=exact_new_chain(signal=sig,signal_stream=STREAMS[0],
       signal_stream_id=sid,candidate=cand,candidate_stream=STREAMS[1],
       candidate_stream_id=cid,intent=it)
   if result['source_chain_exact']:
    verdicts['EXACT_SOURCE_ONLY_NO_ORDER_AUTHORITY']+=1
   else:
    verdicts['NOT_PROVEN']+=1
    missing.update(result['source_chain_errors'])
   if len(examples)<5:
    examples.append({'source_chain_exact':result['source_chain_exact'],
      'reason_codes':list(result['source_chain_errors'])})
 assert verdicts['EXACT_SOURCE_ONLY_NO_ORDER_AUTHORITY']<=summary['trade_intents_observed']
 lengths=dict(source_lengths or {})
 return {'schema':'long1_stage17_readonly_source_chain_audit_v1',
   'scope':'retained_LONG1_streams_only','enabled_explicitly_by_cli':True,
   'read_streams':list(STREAMS),'max_rows_per_stream':limit,
   'source_stream_lengths':lengths,
   'potential_retention_truncation':any(v>limit for v in lengths.values()),
   'records_read':{k:len(records.get(k,())) for k in STREAMS},
   'trade_intents_long_observed':summary['trade_intents_observed'],
   'counts':dict(verdicts),'missing_reason_counts':dict(missing),
   'sample_only_no_personal_payload':examples,
   'cross_link_method':'exact_explicit_transport_id_only',
   'no_guess_by_timestamp_score_or_price':True,
   'historical_model_intent_join_not_proven_without_parents':True,
   'live_order_authorized':False,'real_orders_sent':0,
   'redis_writes':0,'stage15_compliance_not_proven':True}
def run_redis(*,limit):
 import redis
 r=redis.Redis(host='127.0.0.1',port=6379,decode_responses=True,
    socket_timeout=4,socket_connect_timeout=3)
 rows={};lengths={}
 for name in STREAMS:
  lengths[name]=r.xlen(name)
  rows[name]=decode(r.xrevrange(name,count=limit))
 return audit(rows,source_lengths=lengths,limit=limit)
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--audit-readonly',action='store_true')
 p.add_argument('--max-rows',type=int,default=3000)
 p.add_argument('--output',default='')
 args=p.parse_args()
 if not args.audit_readonly:
  print('DISABLED: pass --audit-readonly to read retained Redis streams')
  return 0
 if not 100<=args.max_rows<=5000:
  p.error('max rows must be from 100 to 5000')
 result=run_redis(limit=args.max_rows)
 if args.output:
  out=Path(args.output).resolve()
  safe=(ROOT/'research/results').resolve()
  if out.parent!=safe: p.error('output path must be research/results')
  out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ('sample_only_no_personal_payload',)},
                  ensure_ascii=False,sort_keys=True))
 return 0
if __name__=='__main__':raise SystemExit(main())
