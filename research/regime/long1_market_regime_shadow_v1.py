"""LONG1 conservative research-only market regime classifier, no order authority.

Pure market-state detector: labels, wall-clock times, and user-selected
trading windows are NOT inputs. Missing as-of evidence -> UNKNOWN/PENDING.
"""
from __future__ import annotations
from math import isfinite

PROFILE=dict(id='long1.market_regime.shadow_v1',
 price_5m_down_bps=-3.0,price_15m_down_bps=-8.0,
 price_30m_down_bps=-12.0,
 flow15_negative_ceiling=-0.05,flow15_recovery_floor=0.20,
 price_3m_recovery_bps=3.0,price_5m_recovery_bps=3.0,
 lookback_5m_max_age_ms=303000,
 lookback_15m_max_age_ms=903000,
 shadow_only=True,orders_authorized=False)

def classify(data):
    """Return regime class, veto advice and reasons. No trading permissions.

    Price returns are percent-free fractional changes, e.g. -0.001 = -10 bps.
    Flow signed in [-1,+1]. Price bars are completed; freshness verified by caller.
    """
    def ans(state,reason,advice='PENDING'):
        return dict(regime=state,reason=reason,
                    advisory=advice,orders_authorized=False,
                    profile=PROFILE['id'])
    if not isinstance(data,dict):return ans('UNKNOWN','missing_context')
    names=('return_3m','return_5m','return_15m','return_30m','flow15')
    try:vals={k:float(data[k]) for k in names}
    except (TypeError,ValueError,KeyError):return ans('UNKNOWN','missing_numeric')
    if not all(isfinite(v) for v in vals.values()):return ans('UNKNOWN','nan_or_inf')
    if not data.get('asof_complete') is True:return ans('UNKNOWN','not_asof_complete')
    if abs(vals['flow15'])>1:return ans('UNKNOWN','bad_flow')
    flow=vals['flow15']
    p3=vals['return_3m']*10000;p5=vals['return_5m']*10000
    p15=vals['return_15m']*10000;p30=vals['return_30m']*10000
    # Strong decline: completed multi-timeframe downtrend and sell side flow.
    longdown=p15<=PROFILE['price_15m_down_bps'] and p30<=PROFILE['price_30m_down_bps']
    shortdown=p5<=PROFILE['price_5m_down_bps'] or p3<0
    if longdown and shortdown and flow<=PROFILE['flow15_negative_ceiling']:
        return ans('BEARISH','multi_timeframe_decline_and_selling','VETO_LONG')
    # Positive 5m+15m and positive taker flow: evidence of broader recovery.
    if p3>=PROFILE['price_3m_recovery_bps'] and p5>=PROFILE['price_5m_recovery_bps'] and p15>0 and flow>=PROFILE['flow15_recovery_floor']:
        return ans('RECOVERY','completed_mtf_recovery_and_buyers','RESEARCH_CANDIDATE')
    if p15>0 and p30>0 and flow>0:
        return ans('BULLISH','positive_15m30m_and_flow','RESEARCH_CANDIDATE')
    return ans('UNCERTAIN','mixed_or_weak_market_context','PENDING')
