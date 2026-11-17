"""LONG1 proposed regime pending contract, research-only.

Historical model can qualify for pending but DOES NOT get reusable order permission.
Caller must supply a newly generated independent model signal and fresh, fully
closed 3m + 5m recovery after the original adverse observation. All data as-of.
"""
from __future__ import annotations
import math
PROFILE=dict(schema='long1_regime_pending_revalidation_shadow_v1',
    max_pending_ms=30*60*1000,flow15_recovery_min=0.0,
    source_max_age_ms=30000,orders_authorized=False,shadow_only=True)
def check(original,current):
    def decision(state,reason):
        return dict(state=state,reason=reason,orders_authorized=False)
    if not isinstance(original,dict) or not isinstance(current,dict):
        return decision('REJECT','missing_context')
    needed=('origin_ms','close_id')
    if any(k not in original for k in needed):
        return decision('REJECT','origin_identity_missing')
    for k in ('asof_ms','micro_observed_ms','completed_3m_close_ms',
         'completed_5m_close_ms','model_close_id','flow15','return_3m','return_5m'):
        if k not in current:return decision('PENDING','missing_revalidation_feature')
    try:
        origin=int(original['origin_ms']); now=int(current['asof_ms'])
        micro=int(current['micro_observed_ms'])
        c3=int(current['completed_3m_close_ms']);c5=int(current['completed_5m_close_ms'])
        new_id=int(current['model_close_id']);old_id=int(original['close_id'])
        flow=float(current['flow15']);r3=float(current['return_3m']);r5=float(current['return_5m'])
    except (TypeError,ValueError,OverflowError):
        return decision('REJECT','invalid_types')
    if not all(math.isfinite(x) for x in (flow,r3,r5)) or not -1<=flow<=1:
        return decision('REJECT','invalid_numeric')
    if now<=origin:return decision('REJECT','noncausal_time')
    if now-origin>PROFILE['max_pending_ms']:
        return decision('REJECT','pending_expired')
    if new_id<=old_id:return decision('PENDING','new_model_required')
    if not (micro<=now and 0<=now-micro<=PROFILE['source_max_age_ms']):
        return decision('PENDING','stale_or_future_micro')
    if not (origin<c3<now and origin<c5<now):
        return decision('PENDING','new_closed_3m_5m_required')
    if current.get('model_new_proof') is not True:
        return decision('PENDING','independent_model_proof_required')
    if current.get('entry_1m_fresh_support') is not True:
        return decision('PENDING','fresh_1m_support_missing')
    if not (r3>0 and r5>0 and flow>=PROFILE['flow15_recovery_min']):
        return decision('PENDING','multi_timeframe_or_flow_not_recovered')
    return decision('SHADOW_REVALIDATED','fresh_completed_recovery_evidence')
