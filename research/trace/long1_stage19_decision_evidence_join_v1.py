"""Stage19 opt-in READ-ONLY evidence joining Stage18 exact parent audit + entry trace.

Does NOT confer order authority. Stage11 trace records lack independent
candle close identity, even when source/intent identifiers match.
An exact source chain + trace action=open is still NOT a live OPEN proof.
No inference from clock, score, or price. No background jobs.
"""
from __future__ import annotations
import argparse,json
from collections import Counter,defaultdict
from pathlib import Path
from collections.abc import Mapping
from research.trace.long1_stage18_forward_only_source_audit_v1 import (
    audit_since,load,CURSOR)
from research.trace.audit_long1_stage17_readonly_source_chain_v1 import STREAMS
from orchestration.trace.long1_fresh_intent_source_chain_v1 import exact_new_chain
ROOT=Path(__file__).resolve().parents[2]
TRACE='telemetry:long1:entry_decision_trace:v1'
STAGES=frozenset(('sniper','entry_confirmation','pending_store','pending_recheck','contra_trend'))
STATUSES=frozenset(('open','block','pending','ready','wait','blocked','cleared','expired','invalid'))
def decode(rows):
    out=[]
    for sid,fields in rows:
        try:
            v=json.loads(fields.get('json','{}'))
        except (TypeError,ValueError,AttributeError):
            continue
        if isinstance(v,dict):out.append((sid,v))
    return out
def classify(*,source_exact,record,expected_intent_id,source_stream_id=None):
    """Pure proof ordering. Mismatched/untrusted trace never upgrades source."""
    if not source_exact:
        return 'NO_EXACT_SOURCE_PARENT'
    if not isinstance(record,Mapping):
        return 'TRACE_MISSING'
    if record.get('schema')!='long1_entry_decision_audit.v1':
        return 'TRACE_SCHEMA_INVALID'
    if record.get('symbol')!='NEARUSDT' or record.get('side')!='long':
        return 'TRACE_SCOPE_INVALID'
    if record.get('source')!='ACTUAL_EXECUTOR_DECISION':
        return 'TRACE_SOURCE_INVALID'
    if record.get('advisory_only') is not True or record.get('order_authority') is not False:
        return 'TRACE_PRIVILEGE_INVALID'
    if str(record.get('intent_id') or '')!=str(expected_intent_id or '') or not expected_intent_id:
        return 'TRACE_INTENT_NOT_EXACT'
    if record.get('stage') not in STAGES or record.get('action') not in STATUSES:
        return 'TRACE_DECISION_INVALID'
    # A trace can be correlated to an exact intent by identifier, yet could
    # be stale, belong to a different attempt, or lack a source-candle ID.
    # The transport payload does not currently independently prove the candle.
    if record.get('decision_candle_identity_verified') is not True:
        return 'TRACE_INTENT_EXACT_CANDLE_UNPROVEN'
    if record.get('stage')=='contra_trend':
        if record.get('action')=='ready' and record.get('market_context_3m_5m_recovery_verified') is not True:
            return 'RECOVERY_NOT_PROVEN'
    # Stage11 has NO original exchange source candle independently checked;
    # even if record self-reports True, reject promotion until separate evidence.
    return 'TRACE_INTENT_EXACT_INDEPENDENT_CANDLE_PROOF_MISSING'
def correlate(*,exact_intents,trace_rows,limit=2500):
    """exact_intents must come from Stage17 source identity resolver, not guesses."""
    if limit<1 or limit>5000:raise ValueError('invalid_limit')
    ids={str(x) for x in exact_intents if isinstance(x,str) and x}
    indexed=defaultdict(list)
    invalid=Counter()
    for sid,obj in trace_rows[:limit]:
        iid=obj.get('intent_id') if isinstance(obj,Mapping) else None
        if not isinstance(iid,str) or not iid:
            invalid['TRACE_MISSING_INTENT_ID']+=1;continue
        if iid not in ids:
            invalid['TRACE_INTENT_NOT_IN_EXACT_SOURCE_SET']+=1;continue
        indexed[iid].append((sid,obj))
    by_intent=[]
    for iid in sorted(ids):
        seq=indexed.get(iid,[])
        reasons=Counter(classify(source_exact=True,record=r,expected_intent_id=iid) for _,r in seq)
        by_intent.append({'intent_id':iid,
            'observed_trace_records':len(seq),
            'reason_counts':dict(reasons),
            'full_order_authority_proven':False,
            'native_market_3m5m_candle_independently_proven':False,
            'risk_master_final_safety_order_ack_proven':False})
    return {'schema':'long1_stage19_entry_evidence_join.v1',
        'exact_source_intent_count':len(ids),
        'trace_records_read':len(trace_rows[:limit]),
        'trace_records_discarded_reason':dict(invalid),
        'intents_with_trace':sum(x['observed_trace_records']>0 for x in by_intent),
        'intents_without_trace':sum(x['observed_trace_records']==0 for x in by_intent),
        'intent_reason_counts':dict(sum((Counter(x['reason_counts']) for x in by_intent),Counter())),
        'full_order_authority_proven':0,
        'real_orders':0,'redis_writes':0,
        'no_timestamp_score_price_join':True,
        'future_event_candle_independent_proof_required':True,
        'trace_zero_not_equivalent_to_zero_model_events':True,
        'samples_no_sensitive_intent_values':[
           {'trace_count':z['observed_trace_records'],'reasons':z['reason_counts']}
             for z in by_intent[:5]]}
def resolve_new_exact_intents(reader,state,limit=2500):
    """Read strictly NEW intent batches plus limited explicit transport parents.

    Zero new intents -> zero parent-stream reads. Failure/trim -> no IDs.
    Duplicate intent_id across different batch rows is ambiguous -> reject it.
    """
    start=state['last_seen_intent_id']
    batch=decode(reader.xrange(STREAMS[2],min='('+start,max='+',count=limit+1))
    if len(batch)>limit:
        return set(),{'new_batch_count':len(batch),'source_limit_exceeded':True}
    if not batch:
        return set(),{'new_batch_count':0,'source_limit_exceeded':False,
                      'upstream_records_read':0}
    signals=dict(decode(reader.xrevrange(STREAMS[0],count=limit)))
    candidates=dict(decode(reader.xrevrange(STREAMS[1],count=limit)))
    if reader.xlen(STREAMS[0])>limit or reader.xlen(STREAMS[1])>limit:
        # Retention sample can omit older parents; valid explicit IDs
        # still proven against what IS retained, never 'fully covered'.
        pass
    valid=set();multiplicity=Counter();errors=Counter()
    for _,payload in batch:
        records=payload.get('items',[]) if isinstance(payload.get('items'),list) else ()
        for intent in records:
            if not isinstance(intent,Mapping) or intent.get('symbol')!='NEARUSDT' or intent.get('side')!='long':
                continue
            iid=intent.get('intent_id')
            if not isinstance(iid,str) or not iid:
                errors['MISSING_INTENT_ID']+=1;continue
            multiplicity[iid]+=1
            cs=intent.get('source_candidate_stream_id')
            ss=intent.get('source_signal_stream_id')
            if cs not in candidates or ss not in signals:
                errors['SOURCE_PARENT_NOT_RETAINED']+=1;continue
            try:
                result=exact_new_chain(
                    signal=signals[ss],signal_stream=STREAMS[0],signal_stream_id=ss,
                    candidate=candidates[cs],candidate_stream=STREAMS[1],
                    candidate_stream_id=cs,intent=intent)
            except (ValueError,TypeError,KeyError,AssertionError):
                errors['SOURCE_PARENT_VALIDATION_ERROR']+=1;continue
            if result['source_chain_exact']:
                valid.add(iid)
            else:
                errors['SOURCE_PARENT_NOT_EXACT']+=1
    ambiguous={k for k,v in multiplicity.items() if v>1}
    valid.difference_update(ambiguous)
    return valid,{'new_batch_count':len(batch),
        'source_limit_exceeded':False,'upstream_records_read':len(signals)+len(candidates),
        'exact_new_intent_count':len(valid),
        'ambiguous_duplicate_intent_ids_rejected':len(ambiguous),
        'failure_reason_counts':dict(errors)}

def observe(reader, state, limit=2500):
    # Stage18 audit strictly uses new Intent after cursor; no cursor mutation.
    report,_=audit_since(reader,state,limit=limit)
    # Intents exact only if independently re-derived from Stage6+Stage7
    # transport parents, NEVER from a timestamp or score.
    ids,parents=resolve_new_exact_intents(reader,state,limit=limit)
    raw=reader.xrevrange(TRACE,count=limit)
    traces=decode(raw)
    joined=correlate(exact_intents=ids,trace_rows=traces,limit=limit)
    # Gate off if Stage18 independently reported no proven parents.
    assert len(ids)<=report['counts'].get('EXACT_SOURCE_ONLY_NO_ORDER_AUTHORITY',0)
    return {'schema':'long1_stage19_forward_only_evidence_snapshot.v1',
      'stage18_source_chain_counts':report['counts'],
      'stage18_new_intent_batches':report['new_intent_batch_records'],
      'stage18_revalidated_intents':report['trade_intents_long_observed'],
      'stage19_exact_parent_resolution':parents,
      'stage18_canonical_parent_join_unexposed_as_ids':False,
      'entry_trace_stream_length':reader.xlen(TRACE),
      'trace':joined,
      'next_action':'NEED_EXACT_INTENT_SOURCE_PARENTS_AND_INDEPENDENT_CANDLE_ID',
      'order_authority':False,'real_orders':0,'redis_writes':0,
      'services_started':False,'cursor_advanced':False}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--audit-readonly',action='store_true')
    ap.add_argument('--max-rows',type=int,default=2500)
    a=ap.parse_args()
    if not a.audit_readonly:
        print('DISABLED: explicitly set --audit-readonly');return 0
    if not 100<=a.max_rows<=3000:ap.error('max-rows range 100..3000')
    state=load(CURSOR)
    import redis
    client=redis.Redis(decode_responses=True,socket_timeout=4,socket_connect_timeout=3)
    report=observe(client,state,limit=a.max_rows)
    print(json.dumps(report,sort_keys=True))
    return 0
if __name__=='__main__':raise SystemExit(main())
