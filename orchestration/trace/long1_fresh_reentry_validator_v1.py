"""LONG1 prospective provenance validator for expired PENDING reentry.

Pure, offline/advisory. Not a trading gateway; no I/O, no invented model
parentage, no clock/score-based matching. Both intent and model IDs must
be fresh; the original origin identity remains immutable. All timestamps
must be externally attested exchange full-candle closes, not wall-clock
approximations. A verified provenance result is NEVER an ORDER grant.
"""
from __future__ import annotations
from collections.abc import Mapping
import re
_ID=re.compile(r'^[A-Za-z0-9_:.|/-]{1,160}$')
def _valid(v):return isinstance(v,str) and bool(_ID.fullmatch(v))
def _ms(v):
    return v if type(v) is int and v>0 else None
def verify_fresh_reentry(*,origin,recheck,evidence):
    reason=[]
    a=origin if isinstance(origin,Mapping) else {}
    b=recheck if isinstance(recheck,Mapping) else {}
    c=evidence if isinstance(evidence,Mapping) else {}
    if a.get('symbol')!='NEARUSDT' or b.get('symbol')!='NEARUSDT':
        reason.append('wrong_symbol')
    if a.get('side')!='long' or b.get('side')!='long':
        reason.append('wrong_side')
    origin_intent=a.get('intent_id')
    new_intent=b.get('intent_id')
    if not _valid(origin_intent):reason.append('origin_intent_missing')
    if not _valid(new_intent):reason.append('fresh_intent_missing')
    if _valid(origin_intent) and new_intent==origin_intent:reason.append('intent_reused')
    orig_model=a.get('model_evaluation_id')
    new_model=b.get('model_evaluation_id')
    if not _valid(orig_model):reason.append('origin_model_missing')
    if not _valid(new_model):reason.append('fresh_model_missing')
    if _valid(orig_model) and new_model==orig_model:reason.append('model_reused')
    origin_attempt=a.get('pending_attempt_id')
    recheck_attempt=b.get('pending_attempt_id')
    if not _valid(origin_attempt) or not str(origin_attempt).startswith('pending-'):
        reason.append('pending_origin_id_missing')
    if recheck_attempt != origin_attempt:reason.append('pending_attempt_not_preserved')
    if b.get('pending_origin_intent_id')!=origin_intent:
        reason.append('pending_origin_intent_changed')
    if b.get('pending_recheck_intent_id')!=new_intent:
        reason.append('pending_recheck_intent_mismatch')
    # Exact ancestry must be derived from fully validated Stage6-7
    # source metadata; a string alone is not proof of integrity.
    if c.get('exact_model_signal_candidate_intent_chain') is not True:
        reason.append('exact_parent_chain_not_attested')
    if c.get('fresh_model_evaluation_attested') is not True:
        reason.append('fresh_model_not_attested')
    origin_close=_ms(c.get('origin_closed_3m_ms'))
    later3=_ms(c.get('new_closed_3m_ms'))
    later5=_ms(c.get('new_closed_5m_ms'))
    observed=_ms(c.get('observed_at_ms'))
    if not all((origin_close,later3,later5,observed)):
        reason.append('candle_time_missing')
    elif not (origin_close<later3<=observed and origin_close<later5<=observed):
        reason.append('candle_not_fresh_asof')
    if c.get('closed_3m_source_verified') is not True:
        reason.append('closed_3m_unverified')
    if c.get('closed_5m_source_verified') is not True:
        reason.append('closed_5m_unverified')
    if c.get('contra_recovery_3m5m_confirmed') is not True:
        reason.append('contra_recovery_unverified')
    if c.get('new_1m_sniper_pass') is not True:
        reason.append('new_sniper_unverified')
    if c.get('new_1m_entry_confirmation_pass') is not True:
        reason.append('new_entry_unverified')
    if c.get('original_pending_expired') is not True:
        reason.append('original_pending_not_expired')
    if c.get('no_conflicting_window') is not True:
        reason.append('conflict_not_excluded')
    if c.get('broker_position_flat_verified') is not True:
        reason.append('broker_flat_unverified')
    if c.get('shared_risk_permission') is not True:
        reason.append('shared_risk_unverified')
    # This is a requirement checklist only. It cannot, by design,
    # grant exchange authority even if all attestations are supplied.
    return {'status':'RESEARCH_PROVENANCE_COMPLETE' if not reason else 'NO_GO',
            'provenance_complete':not reason,'missing_or_invalid':tuple(reason),
            'live_order_authorized':False,'execution_risk_authorized':False,
            'new_model_id':new_model if _valid(new_model) else None,
            'new_intent_id':new_intent if _valid(new_intent) else None}
