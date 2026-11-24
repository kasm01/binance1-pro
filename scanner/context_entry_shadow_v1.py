"""Pure, fail-closed multi-horizon context/entry research filter.

NO READY, trading, alerts or permissions. No exchange keys or APIs.
The 3m/5m/15m/60m returns are rolling horizons from CLOSED 1m bars,
not native completed Binance 3m/5m/15m/1h kline candles.
Thresholds are explicit RESEARCH HYPOTHESES, not calibrated edge.
"""
from __future__ import annotations

from math import isfinite
from statistics import median
from scanner.extreme_momentum_v1 import inspect, MS, number

VALID_WATCH = {'STRONG_WATCH', 'EXTREME_WATCH', 'EXTREME_CAUTION_WATCH', 'WATCH'}
MAX_BARS = 180
MIN_BARS = 125

def _base(symbol, direction, observed):
    return {'schema': 'manual_context_entry_shadow.v1', 'symbol': symbol,
            'direction': direction, 'observed_at_ms': observed,
            'state': 'INSUFFICIENT_DATA', 'reason': 'not_evaluated',
            'entry_confirmed': False, 'cost_check_pass': False,
            'ready': False, 'telegram_ready': False, 'order_authorized': False}

def assess(symbol: str, direction: str, bars: list, *, observed_at_ms: int):
    result = _base(symbol, direction, observed_at_ms)
    if direction not in ('LONG','SHORT') or not isinstance(bars, list) or len(bars)<MIN_BARS:
        result['reason']='insufficient_125_closed_1m_bars'
        return result
    sample=bars[-MAX_BARS:]
    pts=[]
    prev=None
    for raw in sample:
        if not isinstance(raw,dict):
            result['reason']='invalid_bar'; return result
        t=raw.get('t')
        vals=[number(raw.get(k)) for k in ('o','h','l','c','quote_volume')]
        if type(t) is not int or t%MS or None in vals:
            result['reason']='invalid_bar';return result
        o,h,l,c,vol=vals
        if min(o,h,l,c)<=0 or vol<0 or l>min(o,c) or h<max(o,c):
            result['reason']='invalid_ohlcv';return result
        if prev is not None and t-prev!=MS:
            result['reason']='source_gap_or_duplicate';return result
        pts.append((t,o,h,l,c,vol));prev=t
    if type(observed_at_ms) is not int or not (0 <= observed_at_ms-(pts[-1][0]+MS) <= 2*MS):
        result['reason']='future_or_stale_source';return result
    # Reuse exact existing WATCH gate to avoid disagreeing with market feed.
    base=inspect(symbol,bars,observed_at_ms=observed_at_ms)
    if base.get('status') not in VALID_WATCH:
        result.update(state='CONTEXT_REJECT',reason='weak_or_unconfirmed_watch',
                      watch_status=base.get('status'))
        return result
    if base.get('direction')!=direction:
        result.update(state='CONTEXT_REJECT',reason='opposite_watch_direction')
        return result
    closes=[r[4] for r in pts]
    last=closes[-1]; sign=1 if direction=='LONG' else -1
    returns={n:sign*100*(last/closes[-n-1]-1) for n in (3,5,15,60)}
    result['rolling_direction_returns_pct']={str(n)+'m':round(v,4) for n,v in returns.items()}
    result['watch_status']=base['status']
    # Contra-trend 60m overrules the immediate 1m/3m bounce;
    # 15m signal must also share the candidate's direction.
    if returns[15]<=0 or returns[60]<=0:
        result.update(state='CONTEXT_PENDING',reason='opposing_15m_or_60m_trend')
        return result
    if returns[3]<=0 or returns[5]<=0:
        result.update(state='CONTEXT_PENDING',reason='short_horizon_not_aligned')
        return result
    prev15=closes[-31]
    pre15_advance=sign*100*(closes[-16]/prev15-1)
    result['preceding_15m_directional_return_pct']=round(pre15_advance,4)
    # 1m candle body and wick, no lookahead or intrabar bar.
    t,o,h,l,c,q=pts[-1]
    candle_range=h-l
    body=abs(c-o)/candle_range if candle_range>0 else 0
    aligned_candle=sign*(c-o)>0
    result['last_1m_body_ratio']=round(body,4)
    if not aligned_candle or body<.25:
        result.update(state='ENTRY_PENDING',reason='last_closed_1m_not_directionally_confirmed')
        return result
    # ATR14 from pre-existing closed 1m bars; never estimated from future.
    trs=[]
    for i in range(len(pts)-14,len(pts)):
        _,_,high,low,_,_=pts[i]
        pc=pts[i-1][4]
        trs.append(max(high-low,abs(high-pc),abs(low-pc)))
    atr=sum(trs)/len(trs)
    if not isfinite(atr) or atr<=0:
        result.update(state='INSUFFICIENT_DATA',reason='invalid_atr')
        return result
    atr_pct=100*atr/last
    # Distance to trailing 20m reference in ATR units: avoid chasing.
    mean20=sum(closes[-20:])/20
    extension=sign*(last-mean20)/atr
    result['atr14_1m_pct']=round(atr_pct,4)
    result['extension_from_20m_mean_in_atr']=round(extension,4)
    if extension>3:
        result.update(state='ENTRY_PENDING',reason='late_extension_over_3atr')
        return result
    if extension<-.5:
        result.update(state='ENTRY_PENDING',reason='mean_dislocation_against_direction')
        return result
    # Two prior closed 1m closes should not show sudden opposite decay.
    if sign*(closes[-1]-closes[-3])<=0:
        result.update(state='ENTRY_PENDING',reason='last_three_minutes_reversal')
        return result
    result.update(state='COST_PENDING',reason='spread_fees_slippage_not_verified')
    # A 40-coin research scan has no live bid/ask, taker-fill, actual
    # Binance fee tier or manual execution price. Cannot be READY.
    return result
