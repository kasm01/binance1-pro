"""30-45m directional SCALP PREPARATION, observation only.

Uses 90 consecutive CLOSED 1m candles, no future data. Identifies
trend-continuation versus reversal watchlists; does not predict that a
breakout will happen 30-45 minutes later, authorize orders or notify.
Fixed research heuristics, not trained predictive probabilities.
"""
from __future__ import annotations
from statistics import median
from scanner.extreme_momentum_v1 import MS,number

def inspect_preparation(symbol,bars,*,observed_at_ms):
 base={'schema':'scalp_preparation_shadow.v1','symbol':symbol,
       'state':'PREPARATION_UNVERIFIED','direction':None,'mode':None,
       'ready':False,'telegram_ready':False,'order_authorized':False,
       'research_only':True}
 if not isinstance(bars,list) or len(bars)<90 or type(observed_at_ms) is not int:
  return dict(base,reason='need_90_closed_1m')
 rows=bars[-90:]
 prev=None
 for b in rows:
  if not isinstance(b,dict) or type(b.get('t')) is not int or b['t']%MS:
   return dict(base,reason='invalid_timestamp')
  if prev is not None and b['t']-prev!=MS:
   return dict(base,reason='source_discontinuity')
  prev=b['t']
  vals=[number(b.get(k)) for k in ('o','h','l','c','quote_volume','taker_buy_quote_volume')]
  if None in vals:return dict(base,reason='missing_price_or_taker_flow')
  o,h,l,c,q,buy=vals
  if min(o,h,l,c)<=0 or q<=0 or not 0<=buy<=q*(1+1e-7)+1e-7 or l>min(o,c) or h<max(o,c,l):
   return dict(base,reason='bad_ohlcv')
 if not 0<=observed_at_ms-(rows[-1]['t']+MS)<=2*MS:
  return dict(base,reason='stale_or_partial')
 def ret(minutes):
  return 100*(rows[-1]['c']/rows[-1-minutes]['c']-1)
 def buy_pressure(last):
  section=rows[-last:]
  q=sum(b['quote_volume'] for b in section)
  return 2*sum(b['taker_buy_quote_volume'] for b in section)/q-1
 r45=ret(45);r30=ret(30);r15=ret(15);r5=ret(5)
 f15=buy_pressure(15);f5=buy_pressure(5)
 # A small pre-move consolidated range relative to preceding 30m
 # is a possible preparation sign but not an entry trigger.
 ranges=[100*(b['h']/b['l']-1) for b in rows[-45:-15]]
 baseline=median(ranges)
 recent=median(100*(b['h']/b['l']-1) for b in rows[-10:])
 compression=bool(baseline>0 and recent/baseline<0.90)
 sign=1 if r45>0 else -1
 # Need actual directionality in the preparation period; otherwise do not guess.
 if abs(r45)<0.35 or abs(r30)<0.18:
  return dict(base,state='NO_PREPARATION',reason='45m_trend_unresolved',
              return45_pct=round(r45,4),return30_pct=round(r30,4))
 # Trend continuation: long-term 30-45m aligned; near-term slowdown
 # or pullback and directional taker support (not already explosive).
 continuation=(sign*r30>0 and sign*f15>=0.025 and
               sign*f5>=-0.06 and sign*r5<0.65)
 reversal_sign=-sign
 # Reversal preparation: 45m direction still apparent, 15m slope
 # weakening against it and recent aggressive buyers/sellers opposing.
 reversal=(reversal_sign*f5>=0.12 and
           sign*r15<max(0.05,abs(r45)*0.2) and
           reversal_sign*r5>0.05)
 if reversal:
  direction='LONG' if reversal_sign==1 else 'SHORT'
  mode='EARLY_REVERSAL'
 elif continuation:
  direction='LONG' if sign==1 else 'SHORT'
  mode='TREND_CONTINUATION'
 else:
  return dict(base,state='NO_PREPARATION',reason='neither_mode_supported',
              return45_pct=round(r45,4),return30_pct=round(r30,4),
              taker_imbalance5=round(f5,4))
 return dict(base,state='PREPARATION_SHADOW',reason='directional_45m_context',
             direction=direction,mode=mode,return45_pct=round(r45,4),
             return30_pct=round(r30,4),return15_pct=round(r15,4),
             return5_pct=round(r5,4),taker_imbalance5=round(f5,4),
             taker_imbalance15=round(f15,4),compression10=bool(compression),
             asof_close_ms=rows[-1]['t']+MS)
