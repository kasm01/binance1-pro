"""Stage22: forward-only exact pending origin/recheck decision chronology audit.

Read-only, default-disabled. Existing Stage11 trace has no independently
verified candle identity; origin+recheck trace pair is diagnostic, NEVER
evidence of actual exchange order authority.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from collections.abc import Mapping
from pathlib import Path
import argparse,json
from research.trace.long1_stage19_decision_evidence_join_v1 import (
  TRACE,STAGES,STATUSES,decode,resolve_new_exact_intents)
from research.trace.long1_stage18_forward_only_source_audit_v1 import load,CURSOR
ROOT=Path(__file__).resolve().parents[2]
VALID_ACTIONS={'pending_store':{'pending','wait','blocked'},
 'pending_recheck':{'pending','ready','open','wait','blocked','expired','invalid'},
 'contra_trend':{'pending','ready','block'}}
def valid_trace(z):
 return (isinstance(z,Mapping) and z.get('schema')=='long1_entry_decision_audit.v1'
  and z.get('source')=='ACTUAL_EXECUTOR_DECISION' and z.get('symbol')=='NEARUSDT'
  and z.get('side')=='long' and z.get('advisory_only') is True
  and z.get('order_authority') is False and z.get('stage') in STAGES
  and z.get('action') in STATUSES and type(z.get('ts_ms')) is int
  and z['ts_ms']>0)
def audit_pairs(*,trace_rows,exact_new_intents):
 """Never infer a parent from shared timestamps or matching scores."""
 exact={x for x in exact_new_intents if isinstance(x,str) and x}
 pairs=defaultdict(lambda:{'origins':[],'rechecks':[],'contra':[]})
 issues=Counter()
 for sid,z in trace_rows:
  if not valid_trace(z):
   issues['INVALID_TRACE_SCHEMA_OR_PROVENANCE']+=1;continue
  stage=z['stage'];aid=z.get('pending_attempt_id')
  if stage not in ('pending_store','pending_recheck','contra_trend'):
   continue
  if stage in VALID_ACTIONS and z['action'] not in VALID_ACTIONS[stage]:
   issues['INCOMPATIBLE_STAGE_ACTION']+=1;continue
  if not isinstance(aid,str) or not aid.startswith('pending-') or len(aid)>160:
   issues['MISSING_ATTEMPT_ID']+=1;continue
  obj={'sid':sid,'ts_ms':z['ts_ms'],'intent_id':z.get('intent_id'),
       'origin':z.get('pending_origin_intent_id'),
       'recheck':z.get('pending_recheck_intent_id'),
       'count':z.get('pending_recheck_count'),
       'action':z['action'],'stage':stage,
       'native_candle_verified':z.get('decision_candle_identity_verified') is True,
       'market_recovered':z.get('market_context_3m_5m_recovery_verified') is True}
  kind='origins' if stage=='pending_store' else 'rechecks' if stage=='pending_recheck' else 'contra'
  pairs[aid][kind].append(obj)
 classified=[]
 for aid,parts in sorted(pairs.items()):
  errs=[]
  origin=parts['origins']
  rechecks=parts['rechecks']
  if len(origin)!=1:errs.append('ORIGIN_MISSING_OR_AMBIGUOUS')
  if not rechecks:errs.append('RECHECK_MISSING')
  original=origin[0] if len(origin)==1 else None
  if original and (not isinstance(original['intent_id'],str) or
                   original['intent_id'] not in exact):
   errs.append('ORIGIN_INTENT_NOT_EXACT')
  if original and original['origin'] not in ('',None,original['intent_id']):
   errs.append('ORIGIN_INTENT_CONFLICT')
  for recheck in rechecks:
   if not original:continue
   if not isinstance(recheck['intent_id'],str) or recheck['intent_id'] not in exact:
    errs.append('RECHECK_INTENT_NOT_EXACT')
   if recheck['origin']!=original['intent_id']:
    errs.append('PENDING_ORIGIN_CHANGED')
   if recheck['recheck']!=recheck['intent_id']:
    errs.append('RECHECK_INTENT_FIELD_MISMATCH')
   if recheck['intent_id']==original['intent_id']:
    errs.append('OLD_INTENT_REUSED')
   if recheck['ts_ms']<=original['ts_ms']:
    errs.append('NOT_FRESH_AFTER_ORIGIN')
   if type(recheck['count']) is not int or recheck['count']<1:
    errs.append('INVALID_RECHECK_COUNT')
  counts=[r['count'] for r in rechecks]
  if len(set(counts))!=len(rechecks):
   errs.append('DUPLICATE_RECHECK_COUNT')
  if rechecks and (any(type(v) is not int for v in counts) or
      [r['count'] for r in sorted(rechecks,key=lambda a:a['ts_ms'])]!=sorted(counts)):
   errs.append('RECHECK_COUNT_NOT_MONOTONIC')
  # Even perfect Stage11 trace does not prove a completed exchange candle.
  if not all(a['native_candle_verified'] for a in origin+rechecks):
   errs.append('NATIVE_CANDLE_IDENTITY_NOT_PROVEN')
  if any(a['action'] in ('ready','open') for a in rechecks) and not any(
     a['market_recovered'] and a['action']=='ready' for a in parts['contra']):
   errs.append('CONTRA_RECOVERY_EVIDENCE_NOT_PROVEN')
  # Stage11 trace never carries Risk Master / broker-flat FINAL SAFETY.
  errs.append('RISK_MASTER_FINAL_SAFETY_NOT_PROVEN')
  errs=list(dict.fromkeys(errs))
  issues.update(errs)
  classified.append({'attempt_present':True,
    'origin_records':len(origin),'recheck_records':len(rechecks),
    'contra_records':len(parts['contra']),
    'reason_codes':errs,'pair_identity_diagnostic_ok':not any(
      x in errs for x in ('ORIGIN_MISSING_OR_AMBIGUOUS','RECHECK_MISSING',
      'ORIGIN_INTENT_NOT_EXACT','RECHECK_INTENT_NOT_EXACT',
      'PENDING_ORIGIN_CHANGED','RECHECK_INTENT_FIELD_MISMATCH',
      'OLD_INTENT_REUSED','NOT_FRESH_AFTER_ORIGIN','INVALID_RECHECK_COUNT',
      'DUPLICATE_RECHECK_COUNT','RECHECK_COUNT_NOT_MONOTONIC')),
    'live_order_authority':False})
 return {'schema':'long1_stage22_pending_provenance_audit.v1',
  'trace_records_evaluated':len(trace_rows),'pending_attempts_seen':len(pairs),
  'exact_new_intent_count':len(exact),'reason_counts':dict(issues),
  'pairs_with_diagnostic_identity_only':sum(z['pair_identity_diagnostic_ok'] for z in classified),
  'native_closed3m5m_independent_proof_count':0,
  'risk_master_live_order_authority_count':0,'real_orders':0,
  'prod_redis_writes':0,'time_price_score_heuristic_join':False,
  'samples_no_identifiers':classified[:8]}
def observe(reader,state,limit=2500):
 exact,proof=resolve_new_exact_intents(reader,state,limit=limit)
 raw=reader.xrevrange(TRACE,count=limit)
 rows=decode(raw)
 result=audit_pairs(trace_rows=rows,exact_new_intents=exact)
 return {'schema':'long1_stage22_forward_only_pending_decision_snapshot.v1',
  'stage19_source_proof':proof,
  'stage11_entry_trace_len':reader.xlen(TRACE),
  'pending':result,'live_order_authorized':False,
  'cursor_advanced':False,'redis_writes':0,'real_orders':0}
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--audit-readonly',action='store_true')
 ap.add_argument('--max-rows',type=int,default=2500)
 args=ap.parse_args()
 if not args.audit_readonly:
  print('DISABLED: --audit-readonly required');return 0
 if not 100<=args.max_rows<=3000:ap.error('max-rows out of range')
 state=load(CURSOR)
 import redis
 reader=redis.Redis(decode_responses=True,socket_timeout=4,socket_connect_timeout=3)
 print(json.dumps(observe(reader,state,limit=args.max_rows),sort_keys=True))
 return 0
if __name__=='__main__':raise SystemExit(main())
