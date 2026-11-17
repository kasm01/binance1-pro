"""LONG1 Market Context V2 research-only; no production authority.

All price returns are fractions (e.g. -0.005 => -0.5%).
Uses fully CLOSED candle returns with source snapshot freshness checked by caller.
Uses no date, hour, human labels, future bars, exits or model score.
Require as-of buyer flow for a positive READY recommendation. Missing data
is UNKNOWN/PENDING, not implicitly favorable. Pure decision function.
"""
from __future__ import annotations
from math import isfinite
from typing import Mapping
POLICY_ID='long1_market_context_v2_research_20261116'
def classify(data: Mapping|None):
 def output(regime,decision,reason,evidence=None):
  return dict(policy=POLICY_ID,regime=regime,decision=decision,reason=reason,
   evidence=evidence or {},orders_authorized=False)
 if not isinstance(data,dict) or data.get('asof_complete') is not True:
  return output('UNKNOWN','PENDING','missing_or_unclosed_context')
 keys=('return_3m','return_5m','return_15m','return_30m')
 try:
  p=[float(data[k]) for k in keys]
 except (KeyError,TypeError,ValueError):
  return output('UNKNOWN','PENDING','missing_price_return')
 if not all(isfinite(v) for v in p):
  return output('UNKNOWN','PENDING','invalid_price')
 r3,r5,r15,r30=p
 falling=(r3<0 and r5<0)
 deep_fall=(r5<=-0.005 and (r15<=-0.003 or r30<=-0.004))
 bearish_structure=(falling and (r15<0 or r30<0)) or deep_fall
 flow=data.get('flow15')
 try:f=float(flow) if flow is not None else None
 except (TypeError,ValueError):f=None
 if f is not None and (not isfinite(f) or abs(f)>1): f=None
 e=dict(r3=r3,r5=r5,r15=r15,r30=r30,flow15=f,
   falling=falling,deep_fall=deep_fall)
 # Price structure is enough for an *adverse* pending/veto proposal;
 # it does not depend on optional buyer flow.
 if deep_fall and (f is None or f<0):
  return output('BEARISH','VETO_ADVISORY','deep_5m_15m_decline',e)
 if bearish_structure and (f is None or f<0):
  return output('BEARISH','PENDING','multi_tf_downtrend',e)
 if bearish_structure and f>=0:
  return output('MIXED','PENDING','positive_flow_against_bearish_price',e)
 if f is None:
  return output('UNKNOWN','PENDING','missing_flow_to_confirm_recovery',e)
 if r3>0 and r5>0 and r15>0 and f>=0.12:
  return output('RECOVERY','READY_CANDIDATE','completed_3m_5m_15m_and_flow',e)
 if r3>=0 and r5>0 and r15>0 and r30>0 and f>0:
  return output('BULLISH','READY_CANDIDATE','positive_mtf_and_flow',e)
 return output('UNCERTAIN','PENDING','insufficient_confluence',e)
