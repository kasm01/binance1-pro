"""Research-only frozen recovery lane for external hold-out hours.

No Redis writes, no orders, no switches. This is not a production gate.
The training labels and local date/time are NEVER inputs to the decision.
Inputs must be contemporaneous, not precomputed with future bars.
"""
from __future__ import annotations
import math
FROZEN_PROFILE=dict(profile_id='long1.recovery_regime_shadow_v1_20261115',
  model_score_floor=.495, min_flow15=.20,
  require_1m_support=True,require_whale_ok=True,
  require_positive_3m=True,require_positive_5m=True,
  require_positive_9m=True,require_positive_15m=True,
  require_3m_higher_low=True,require_5m_higher_low=True,
  research_only=True,production_authorized=False,order_authorized=False)
def assess(x):
    def reject(reason,stage='REJECT'):
        return {'status':stage,'reason':reason,'production_authorized':False,
                'order_authorized':False}
    if not isinstance(x,dict):return reject('missing_input')
    f=x.get('price_features')
    if not isinstance(f,dict) or not x.get('shadow_record_present'):
        return reject('missing_market_source')
    values=(x.get('score'),x.get('flow15'),
            f.get('return_3m'),f.get('return_5m'),
            f.get('return_9m'),f.get('return_15m'))
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
        return reject('invalid_or_missing_numeric_feature')
    if x['score']<FROZEN_PROFILE['model_score_floor']:
        return reject('score_floor')
    if x['flow15']<FROZEN_PROFILE['min_flow15']:
        return reject('flow_not_confirmed','PENDING')
    if x.get('one_min_support') is not True:
        return reject('one_min_not_confirmed','PENDING')
    checks=x.get('all_shadow_checks')
    if not isinstance(checks,dict) or checks.get('whale_ok') is not True:
        return reject('whale_not_confirmed','PENDING')
    if min(f['return_3m'],f['return_5m'],f['return_9m'],f['return_15m'])<=0:
        return reject('multi_timeframe_recovery_not_confirmed','PENDING')
    if f.get('three_m_higher_low') is not True or f.get('five_m_higher_low') is not True:
        return reject('higher_low_not_confirmed','PENDING')
    return reject('recovery_shadow_candidate_only','SHADOW_READY_CANDIDATE')
