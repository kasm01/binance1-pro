"""CLOSED-kline taker flow & exhaustion research classifier.

No API/Telegram/order authority. Taker buy quote asset volume is
provided by Binance REST kline index 10 and WS kline field k.Q;
buyer-initiated notional != passive bid-book support or actual fill.

Requires same 65 contiguous closed 1m bars and source time.
Missing taker data -> UNVERIFIED, never positive implied flow.
"""
from __future__ import annotations
from scanner.extreme_momentum_v1 import MS,number

def _result(state,reason):
 return {'schema':'manual_taker_flow_shadow.v1','state':state,
  'reason':reason,'ready':False,'telegram_ready':False,
  'order_authorized':False,'research_only':True}

def assess_flow(bars,direction,*,observed_at_ms):
 if direction not in ('LONG','SHORT') or type(observed_at_ms) is not int:
  return _result('FLOW_UNVERIFIED','invalid_direction_or_time')
 if not isinstance(bars,list) or len(bars)<65:
  return _result('FLOW_UNVERIFIED','insufficient_closed_history')
 p=bars[-65:]
 prev=None
 for row in p:
  if not isinstance(row,dict) or type(row.get('t')) is not int:
   return _result('FLOW_UNVERIFIED','malformed_bar')
  t=row['t']
  if t%MS or (prev is not None and t-prev!=MS):
   return _result('FLOW_UNVERIFIED','gap_or_duplicate')
  prev=t
  total=number(row.get('quote_volume'))
  buy=number(row.get('taker_buy_quote_volume'))
  if total is None or buy is None or total<=0 or not 0<=buy<=total*(1+1e-7)+1e-7:
   return _result('FLOW_UNVERIFIED','missing_or_invalid_taker_buy')
  vals=[number(row.get(k)) for k in ('o','h','l','c')]
  if None in vals or min(vals)<=0 or vals[2]>min(vals[0],vals[3]) or vals[1]<max(vals[0],vals[3],vals[2]):
   return _result('FLOW_UNVERIFIED','invalid_ohlc')
 if not 0<=observed_at_ms-(p[-1]['t']+MS)<=2*MS:
  return _result('FLOW_UNVERIFIED','partial_or_stale')
 def imbalance(window):
  total=sum(r['quote_volume'] for r in window)
  buy=sum(r['taker_buy_quote_volume'] for r in window)
  return 2*buy/total-1 if total>0 else None
 im3=imbalance(p[-3:]);im5=imbalance(p[-5:]);im15=imbalance(p[-15:])
 if None in (im3,im5,im15):
  return _result('FLOW_UNVERIFIED','zero_total_volume')
 sgn=1 if direction=='LONG' else -1
 directional3=sgn*im3
 directional5=sgn*im5
 directional15=sgn*im15
 last=p[-1];h=last['h'];l=last['l'];o=last['o'];c=last['c']
 span=h-l
 signbody=sgn*(c-o)
 candle_progress=((c-l)/span if direction=='LONG' else (h-c)/span) if span>0 else 0
 # latest three bars against the candidate vs prior three can signal
 # pressure fading, but NOT necessarily a price reversal.
 weakening=directional3<directional15-0.12
 result=_result('FLOW_MIXED','taker_pressure_mixed_or_weak')
 result.update(directional_taker_imbalance_3m=round(directional3,4),
  directional_taker_imbalance_5m=round(directional5,4),
  directional_taker_imbalance_15m=round(directional15,4),
  raw_buy_share_3m=round((im3+1)/2,4),
  last_candle_body_ratio=round(abs(c-o)/span,4) if span>0 else 0,
  last_candle_directional_progress=round(candle_progress,4),
  weakening_against_15m=weakening)
 if directional3 < -0.12 or directional5 < -0.10:
  result.update(state='FLOW_OPPOSING',reason='aggressive_taker_flow_against_direction')
 elif weakening:
  result.update(state='FLOW_EXHAUSTION_CAUTION',reason='3m_taker_pressure_fading_vs_15m')
 elif signbody<=0 or candle_progress<0.45:
  result.update(state='FLOW_EXHAUSTION_CAUTION',reason='reversal_wick_or_opposing_last_candle')
 elif directional3>=0.12 and directional5>=0.08 and directional15>=0:
  result.update(state='FLOW_SUPPORTIVE',reason='aggressive_taker_flow_matches_move')
 return result
