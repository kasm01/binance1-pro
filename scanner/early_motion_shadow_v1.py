"""Early 3m motion discovery, SHADOW ONLY. Not a trading entry or Telegram signal.

Uses completed, consecutive 1m bars; thresholds are uncalibrated
research hypotheses. Does not depend on a 15m price-strength trigger.
"""
from __future__ import annotations
from math import sqrt
from statistics import median
from scanner.extreme_momentum_v1 import MS,number

def inspect_early(symbol,bars,*,observed_at_ms):
 out={'symbol':symbol,'state':'NO_EARLY_CANDIDATE','reason':'unknown',
      'direction':None,'ready':False,'telegram_ready':False,'order_authorized':False,
      'shadow_only':True}
 if not isinstance(bars,list) or len(bars)<65 or type(observed_at_ms) is not int:
  return dict(out,state='INSUFFICIENT_DATA',reason='need_65_closed_1m')
 pts=[]
 for b in bars[-65:]:
  if not isinstance(b,dict):return dict(out,state='INSUFFICIENT_DATA',reason='bad_bar')
  t=b.get('t');v=[number(b.get(k)) for k in ('o','h','l','c','quote_volume')]
  if type(t) is not int or t%MS or None in v:
   return dict(out,state='INSUFFICIENT_DATA',reason='bad_source')
  o,h,l,c,vol=v
  if min(o,h,l,c)<=0 or vol<0 or l>min(o,c) or h<max(o,c):
   return dict(out,state='INSUFFICIENT_DATA',reason='invalid_ohlcv')
  if pts and t-pts[-1][0]!=MS:
   return dict(out,state='INSUFFICIENT_DATA',reason='source_gap')
  pts.append((t,o,h,l,c,vol))
 last=pts[-1]
 if not 0<=observed_at_ms-(last[0]+MS)<=2*MS:
  return dict(out,state='INSUFFICIENT_DATA',reason='stale_or_partial')
 ret3=100*(last[4]/pts[-4][4]-1)
 ret5=100*(last[4]/pts[-6][4]-1)
 ret15=100*(last[4]/pts[-16][4]-1)
 ret60=100*(last[4]/pts[-61][4]-1)
 pre=[(pts[i][4]/pts[i-1][4]-1)**2 for i in range(1,50)]
 rms=100*sqrt(sum(pre)/len(pre))
 threshold=max(.45,2.3*rms*sqrt(3))
 sign=1 if ret3>0 else -1
 direction='LONG' if sign==1 else 'SHORT'
 volume_reference=median(p[5] for p in pts[-63:-3])*3
 vol3=sum(p[5] for p in pts[-3:])/volume_reference if volume_reference>0 else 0
 # A valid 3m early movement can occur well before 15m strength builds.
 if abs(ret3)<threshold:
  return dict(out,reason='3m_move_not_large_enough',ret3_pct=round(ret3,4))
 if ret3*ret5<=0:
  return dict(out,reason='3m_5m_directions_disagree',ret3_pct=round(ret3,4))
 if vol3<1.8:
  return dict(out,reason='three_minute_volume_not_expanded',ret3_pct=round(ret3,4))
 # Avoid chasing a move which already traveled far in the last 15m:
 if sign*ret15>2.25:
  return dict(out,reason='15m_move_already_extended',ret3_pct=round(ret3,4))
 # No early candidate on an opposing 60m trend until more context exists.
 if sign*ret60<-.8:
  return dict(out,reason='opposing_60m_move',ret3_pct=round(ret3,4))
 # Last closed candle must still point the intended way.
 high,low=last[2],last[3]
 ratio=abs(last[4]-last[1])/(high-low) if high>low else 0
 if sign*(last[4]-last[1])<=0 or ratio<.3:
  return dict(out,reason='last_candle_no_continuation',ret3_pct=round(ret3,4))
 return dict(out,state='EARLY_CANDIDATE_SHADOW',
    reason='3m_breakout_expanding_volume',
    direction=direction,ret3_pct=round(ret3,4),ret5_pct=round(ret5,4),
    ret15_pct=round(ret15,4),volume_ratio3=round(vol3,3),
    research_threshold3_pct=round(threshold,4),
    last_completed_1m_close_ms=last[0]+MS)
