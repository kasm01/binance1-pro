"""LONG1 research-only strict evidence from actual signal/candidate/intent payloads.

No timestamp matching, no score matching and no Redis/Exchange I/O.
The candidate has to carry the EXACT verified signal parent.  The intent
has to carry EXACT candidate transport provenance and the full same
upstream identity; otherwise do not call a reentry source chain complete.
"""
from __future__ import annotations
from collections.abc import Mapping
from orchestration.trace.long1_lineage_v1 import candidate_parent
from orchestration.trace.long1_candidate_intent_lineage_v1 import candidate_intent_parent
from orchestration.trace.long1_fresh_reentry_validator_v1 import verify_fresh_reentry
REQUIRED=('source_candidate_id','source_candidate_stream',
 'source_candidate_stream_id','parent_signal_event_id','parent_trace_id',
 'source_signal_stream','source_signal_stream_id','model_evaluation_id',
 'model_close_id','model_close_id_kind')
def exact_new_chain(*,signal,signal_stream,signal_stream_id,
                    candidate,candidate_stream,candidate_stream_id,
                    intent,origin_model_evaluation_id=None,
                    origin_intent_id=None):
    errors=[]
    s=signal if isinstance(signal,Mapping) else {}
    c=candidate if isinstance(candidate,Mapping) else {}
    it=intent if isinstance(intent,Mapping) else {}
    if (s.get('symbol'),c.get('symbol'),it.get('symbol'))!=('NEARUSDT',)*3:
        errors.append('wrong_symbol')
    if (str(s.get('side_candidate')).lower(),str(c.get('side')).lower(),
        str(it.get('side')).lower())!=('long','long','long'):
        errors.append('wrong_side')
    if s.get('producer_id')!='heavy_engine':
        errors.append('not_real_model_producer')
    # Stage6 candidate_parent recomputes source transport hash.
    expected=candidate_parent(s,signal_stream,signal_stream_id)
    required_source=('parent_signal_event_id','parent_trace_id',
       'model_evaluation_id','model_close_id','model_close_id_kind',
       'source_signal_stream','source_signal_stream_id')
    if any(k not in expected or c.get(k)!=expected.get(k)
           for k in required_source):
        errors.append('signal_to_candidate_not_exact')
    # Stage7 provenance must start from actual source stream, not
    # the TOP5 stream's unrelated transport ID.
    normalized=dict(c,_source_stream_id=candidate_stream_id)
    expected_intent=candidate_intent_parent(
        candidate=normalized,candidate_stream=candidate_stream)
    if any(k not in expected_intent or it.get(k)!=expected_intent.get(k)
           for k in REQUIRED):
        errors.append('candidate_to_intent_not_exact')
    if not isinstance(it.get('intent_id'),str) or not it['intent_id']:
        errors.append('intent_id_missing')
    if s.get('model_evaluation_id')==origin_model_evaluation_id:
        errors.append('model_not_new')
    if it.get('intent_id')==origin_intent_id:
        errors.append('intent_not_new')
    # Object equality is checked for stream ID, candidate ID, event ID,
    # model eval ID and hash, but this DOES NOT prove raw source validity,
    # completed market candles, Entry, broker-flat or risk.
    return {'source_chain_exact':not errors,
      'source_chain_errors':tuple(errors),
      'model_evaluation_id':s.get('model_evaluation_id') if not errors else None,
      'intent_id':it.get('intent_id') if not errors else None,
      'real_order_authorized':False,'advisory_only':True}
def research_fresh_reentry(*,origin,recheck,evidence,signal,
     signal_stream,signal_stream_id,candidate,candidate_stream,
     candidate_stream_id,intent):
    result=exact_new_chain(signal=signal,signal_stream=signal_stream,
       signal_stream_id=signal_stream_id,candidate=candidate,
       candidate_stream=candidate_stream,candidate_stream_id=candidate_stream_id,
       intent=intent,origin_model_evaluation_id=(origin or {}).get('model_evaluation_id'),
       origin_intent_id=(origin or {}).get('intent_id'))
    # The only source chain attestation this research helper can derive.
    # Other source/market/risk attestations must still be provided and
    # are NOT produced here; never return order authorization.
    evidence0=dict(evidence) if isinstance(evidence,Mapping) else {}
    evidence0['exact_model_signal_candidate_intent_chain']=result['source_chain_exact']
    evidence0['fresh_model_evaluation_attested']=result['source_chain_exact']
    check=verify_fresh_reentry(origin=origin,recheck=recheck,evidence=evidence0)
    return {'source_chain':result,'reentry_provenance':check,
      'real_order_authorized':False,'advisory_only':True}
