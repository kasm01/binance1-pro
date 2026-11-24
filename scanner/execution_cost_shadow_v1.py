"""Manual-only USD-M quote cost & top-of-book liquidity research.

A quote is *not* an executable price guarantee; this module never
returns READY or advice to place an exchange order. All bps are
percentage of notional in basis points (1 bp = 0.01%).
No signed endpoints, Binance keys, Telegram or trading modules.
"""
from __future__ import annotations
from math import isfinite
from scanner.extreme_momentum_v1 import number

# Explicit research assumptions, not account fee facts:
ASSUMED_TAKER_FEE_SIDE_BPS=5.0  # 0.05%, regular tier example
ASSUMED_SLIPPAGE_SIDE_BPS=5.0  # stress assumption, not prediction
MAX_SPREAD_BPS=12.0
MAX_QUOTE_AGE_MS=3500
DEFAULT_NOTIONAL_USDT=100.0

def _base(symbol,direction,now):
 return {'schema':'execution_cost_shadow.v1','symbol':symbol,
  'direction':direction,'asof_ms':now,'state':'COST_PENDING',
  'reason':'unverified_top_of_book','ready':False,'telegram_ready':False,
  'order_authorized':False,'fee_tier_verified':False,
  'slippage_verified':False,'funding_cost_verified':False,
  'stop_and_target_verified':False,'cost_research_only':True}

def assess_quote(symbol,direction,context,quote,*,now_ms,
                 notional_usdt=DEFAULT_NOTIONAL_USDT,
                 fee_side_bps=ASSUMED_TAKER_FEE_SIDE_BPS,
                 assumed_slippage_side_bps=ASSUMED_SLIPPAGE_SIDE_BPS):
 result=_base(symbol,direction,now_ms)
 if not isinstance(context,dict) or context.get('state')!='COST_PENDING':
  result.update(reason='context_gate_not_eligible')
  return result
 if context.get('symbol')!=symbol or context.get('direction')!=direction:
  result.update(reason='mismatched_context_identity')
  return result
 if (type(now_ms) is not int or type(context.get('observed_at_ms')) is not int or
     not 0<=now_ms-context['observed_at_ms']<=MAX_QUOTE_AGE_MS):
  result.update(reason='stale_context_asof')
  return result
 if not isinstance(quote,dict) or quote.get('symbol')!=symbol:
  result.update(reason='quote_missing_or_wrong_symbol')
  return result
 # Binance REST bookTicker may not return a reliable fresh event timestamp.
 # Record local receipt and latency separately in wrapper; no fabricated
 # exchange-time verification or fill certainty.
 bid=number(quote.get('bidPrice'));ask=number(quote.get('askPrice'))
 bqty=number(quote.get('bidQty'));aqty=number(quote.get('askQty'))
 notional=number(notional_usdt)
 fee=number(fee_side_bps);slip=number(assumed_slippage_side_bps)
 if (None in (bid,ask,bqty,aqty,notional,fee,slip) or
     min(bid,ask,bqty,aqty,notional)<=0 or ask<bid or
     not 0<=fee<=20 or not 0<=slip<=50):
  result.update(reason='invalid_quote_or_assumptions')
  return result
 mid=(bid+ask)/2
 spread=10000*(ask-bid)/mid
 result.update(bid_price=bid,ask_price=ask,
  midpoint_price=round(mid,10),spread_bps=round(spread,3),
  assumed_fee_per_side_bps=fee,assumed_slippage_per_side_bps=slip,
  assumed_roundtrip_bps=round(2*(fee+slip)+spread,3),
  top_bid_notional_usdt=round(bid*bqty,2),
  top_ask_notional_usdt=round(ask*aqty,2),
  evaluated_notional_usdt=notional)
 if spread>MAX_SPREAD_BPS:
  result.update(state='COST_REJECT',reason='wide_spread')
  return result
 # For LONG, entry lifts ask and exit sells bid. For SHORT opposite.
 # Both top-of-book sides require >=3x indicative notional.
 if min(bid*bqty,ask*aqty)<3*notional:
  result.update(state='COST_REJECT',reason='shallow_best_quote')
  return result
 atr_pct=number(context.get('atr14_1m_pct'))
 if atr_pct is None or atr_pct<=0:
  result.update(reason='no_context_atr')
  return result
 # Example hypothetical protective stop budget: 2x ATR,
 # but stop price & risk/reward are *not* verified.
 indicative_stop_bps=2*atr_pct*100
 burden=result['assumed_roundtrip_bps']/indicative_stop_bps
 result['indicative_stop_budget_bps']=round(indicative_stop_bps,3)
 result['cost_to_indicative_stop_ratio']=round(burden,4)
 if burden>0.35:
  result.update(state='COST_REJECT',reason='assumed_cost_over_35pct_of_2atr')
  return result
 result.update(state='COST_ESTIMATE_PASS',reason='indicative_cost_under_research_budget')
 # Passing an indicative estimate does not establish a tradable setup:
 # funding, actual user's VIP fee tier, executable fills, planned stop,
 # live top-of-book freshness, target and slippage remain unverified.
 return result

def analyze_book_ticker_response(context,raw,*,now_ms):
 """API-shape adapter. Never stores raw response beyond the call."""
 return assess_quote(context.get('symbol'),context.get('direction'),
                     context,raw,now_ms=now_ms)
