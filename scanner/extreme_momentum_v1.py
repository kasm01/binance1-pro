"""Manual-only 40-coin watch ranking, never an entry/exit decision.

All inputs must be CLOSED, consecutive UTC 1m bars available at one
observed_at_ms. A strong price move is only a WATCH candidate; abnormal
price moves can reverse violently, never auto-promote to READY.
Thresholds are research hypotheses, not tested profitable rules.
"""
from __future__ import annotations
from collections import defaultdict
from math import isfinite,sqrt
from statistics import median
from typing import Mapping

MIN_HISTORY=65
MS=60_000

def number(x):
 try:
  if isinstance(x,bool):return None
  y=float(x)
  return y if isfinite(y) else None
 except (TypeError,ValueError):return None

def inspect(symbol:str, bars:list, *, observed_at_ms:int)->dict:
 base={'symbol':symbol,'status':'INSUFFICIENT_DATA','direction':None,
       'order_authorized':False,'telegram_ready':False,
       'manual_watch_only':True}
 if (not isinstance(symbol,str) or not symbol.endswith('USDT') or
     type(observed_at_ms) is not int or observed_at_ms<=0 or
     not isinstance(bars,list) or len(bars)<MIN_HISTORY):
  return dict(base,reason='missing_history')
 # Expect 1m rows: t is candle OPEN, OHLC and volume in quote units.
 prepared=[]
 for raw in bars[-MIN_HISTORY:]:
  if not isinstance(raw,Mapping):return dict(base,reason='bad_bar')
  t=raw.get('t')
  if type(t) is not int or t%MS:return dict(base,reason='invalid_time')
  o=number(raw.get('o'));h=number(raw.get('h'))
  l=number(raw.get('l'));c=number(raw.get('c'))
  vol=number(raw.get('quote_volume'))
  if None in (o,h,l,c,vol) or min(o,h,l,c)<=0 or vol<0 or h<max(o,c,l) or l>min(o,c,h):
   return dict(base,reason='invalid_ohlcv')
  prepared.append((t,o,h,l,c,vol))
 for before,after in zip(prepared,prepared[1:]):
  if after[0]-before[0]!=MS:return dict(base,reason='gap_or_duplicate')
 latest=prepared[-1]
 if latest[0]+MS>observed_at_ms:
  return dict(base,reason='partial_or_future_candle')
 if observed_at_ms-(latest[0]+MS)>2*MS:
  return dict(base,reason='stale_market_data')
 # 15m and 5m price return, measured at the last CLOSED 1m.
 last=latest[4]
 ret5=100*(last/prepared[-6][4]-1)
 ret15=100*(last/prepared[-16][4]-1)
 ret60=100*(last/prepared[-61][4]-1)
 # Use PRE-move volatility baseline, not the same recent 15m move
 # being tested; prevents abnormal breakout suppressing its own z-score.
 prior_abs=[abs(prepared[i][4]/prepared[i-1][4]-1)
            for i in range(1,len(prepared)-15)]
 realized_sigma_pct=100*sqrt(sum(x*x for x in prior_abs)/len(prior_abs))
 # Robust historical volume baseline excludes the last 5m.
 prior_volumes=[x[5] for x in prepared[-65:-5]]
 current_volume=sum(x[5] for x in prepared[-5:])
 reference=median(prior_volumes)*5
 if reference<=0:return dict(base,reason='zero_reference_volume')
 relative_volume=current_volume/reference
 # Group direction must have consistency across short, middle and 60m;
 # otherwise recent reaction is unconfirmed regardless of score.
 direction='LONG' if ret5>0 and ret15>0 else 'SHORT' if ret5<0 and ret15<0 else None
 # Hypothesis thresholds, intentionally symmetric and coarse.
 threshold15=max(.75,2.0*realized_sigma_pct*sqrt(15))
 extreme=abs(ret15)>=max(2.5,3.5*realized_sigma_pct*sqrt(15))
 price_strength=abs(ret15)>=threshold15
 flow_like_volume=relative_volume>=1.6
 if direction is None:
  status='SUPPRESSED_WEAK';reason='direction_disagreement'
 elif not price_strength:
  status='SUPPRESSED_WEAK';reason='move_below_volatility_floor'
 elif not flow_like_volume and extreme:
  status='EXTREME_CAUTION_WATCH';reason='extreme_price_move_without_volume_expansion'
 elif not flow_like_volume:
  status='SUPPRESSED_WEAK';reason='volume_not_expanded'
 elif ret60*ret15<=0:
  status='WATCH';reason='countertrend_momentum_caution'
 elif extreme:
  status='EXTREME_WATCH';reason='extreme_price_move_high_reversal_risk'
 else:
  status='STRONG_WATCH';reason='sustained_move_and_volume_expansion'
 # Never output READY. Additional context, spread, taker-flow, safety
 # and live candle/entry confirmation are absent.
 return {'symbol':symbol,'status':status,'reason':reason,'direction':direction,
  'ret5_pct':round(ret5,4),'ret15_pct':round(ret15,4),
  'ret60_pct':round(ret60,4),
  'relative_volume_5m':round(relative_volume,3),
  'realized_1m_rms_vol_pct':round(realized_sigma_pct,4),
  'research_threshold15_pct':round(threshold15,4),
  'extreme_move':extreme,'signal_observed_at_ms':observed_at_ms,
  'last_completed_1m_close_ms':latest[0]+MS,
  'order_authorized':False,'telegram_ready':False,
  'manual_watch_only':True,'price_rise_not_proof_of_long_edge':True}
