"""LONG1 contra-trend context policy; pure as-of snapshot checks and independent revalidation.

No trading API side effects; the caller owns safe order authority.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any, Mapping

@dataclass(frozen=True)
class Context:
    valid: bool
    reason: str
    candle_ms: int = 0
    observed_ms: int = 0
    ret3: float = 0.0
    mean3: float = 0.0
    upfrac3: float = 0.0
    flow15: float = 0.0
    flow60: float = 0.0
    @property
    def contra(self) -> bool:
        return self.valid and self.mean3 < 0 and self.upfrac3 <= (1/3+1e-8) and self.flow15 < 0 and self.flow60 < 0
    @property
    def recovery(self) -> bool:
        return self.valid and self.ret3 > 0 and self.flow15 >= 0

def _num(x):
    try:
        y=float(x)
        if math.isfinite(y):return y
    except (TypeError,ValueError):pass
    return None

def snapshot(combined: Mapping[str,Any], structure: Mapping[str,Any], now_ms: int) -> Context:
    if not isinstance(combined,dict) or not isinstance(structure,dict):
        return Context(False,'missing_snapshot')
    if combined.get('status') not in ('OK','DEGRADED') or structure.get('status')!='OK':
        return Context(False,'source_status')
    ctime=_num(combined.get('observed_at_ms'))
    stime=_num(structure.get('observed_at_ms'))
    candle=_num(structure.get('research_3m_close_time_ms'))
    if not ctime or not stime or not candle:return Context(False,'missing_timestamps')
    if not all(0<=now_ms-t<=240000 for t in (ctime,stime,candle)):
        return Context(False,'stale_or_future_snapshot')
    derived=combined.get('derived') or {}
    keys=(structure.get('research_m3_ret1'),structure.get('research_m3_ret1_mean3'),
          structure.get('research_m3_up_frac3'),derived.get('taker_flow15_completed'),
          derived.get('taker_flow60_completed'))
    nums=[_num(x) for x in keys]
    if any(x is None for x in nums):return Context(False,'missing_features')
    if not 0<=nums[2]<=1:return Context(False,'invalid_upfrac')
    return Context(True,'ok',int(candle),int(stime),*nums)

def five_minute_recovered(klines, *, origin_ms:int, now_ms:int) -> bool:
    """Only FULLY CLOSED consecutive 5m candles, latest must have closed after the original intent."""
    if not isinstance(klines,(list,tuple)) or len(klines)<2:return False
    rows=[]
    for x in klines:
        try:
            start=int(x[0]);close_ms=int(x[6]);closing=float(x[4])
            if start%(5*60*1000)==0 and close_ms==start+5*60*1000-1 and close_ms<now_ms and math.isfinite(closing):
                rows.append((start,close_ms,closing))
        except (TypeError,ValueError,IndexError):continue
    if len(rows)<2:return False
    last,prev=rows[-1],rows[-2]
    return bool(last[0]-prev[0]==300000 and last[1]>origin_ms and last[2]>prev[2])
