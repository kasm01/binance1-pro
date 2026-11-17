"""Pure research-only tiered ROI lock. All input ROI values are PERCENT POINTS.

Each tier is (arm ROI %, giveback ROI percentage points). Once a tier
activates, peak and locked floor cannot go backwards. This is NOT production
order logic and never authorizes a trade.
"""
from __future__ import annotations
from math import isfinite
from dataclasses import dataclass
TIERS=((0.60,0.10),(0.95,0.15),(1.20,0.15),(1.65,0.20),(2.00,0.20),(2.50,0.20))
@dataclass
class LockState:
    peak:float=0.0
    floor:float|None=None
    tier:int=-1
    armed_at_ms:int|None=None
def update(state:LockState, roi_pct:float, candle_ms:int):
    if not isinstance(state,LockState) or not isfinite(float(roi_pct)):
        raise ValueError('invalid state or ROI')
    old_floor=state.floor
    if roi_pct>state.peak:state.peak=float(roi_pct)
    newtier=max((k for k,(arm,_) in enumerate(TIERS) if state.peak>=arm),default=-1)
    if newtier>state.tier:
        state.tier=newtier
        if state.armed_at_ms is None:state.armed_at_ms=int(candle_ms)
    if state.tier>=0:
        candidate=state.peak-TIERS[state.tier][1]
        state.floor=max(candidate,state.floor if state.floor is not None else float('-inf'))
    assert state.floor is None or (old_floor is None or state.floor>=old_floor-1e-12)
    # A later bar close can trigger; first ARM bar is excluded to avoid
    # treating its own initial close as both arm and retract.
    hit=(state.floor is not None and state.armed_at_ms is not None
         and candle_ms>state.armed_at_ms and roi_pct<=state.floor)
    return dict(state='SHADOW_TRAIL_TRIGGER' if hit else 'SHADOW_HOLD',
     active_tier=state.tier+1 if state.tier>=0 else 0,peak_roi=state.peak,
     floor_roi=state.floor,roi_now=roi_pct,orders_authorized=False)
