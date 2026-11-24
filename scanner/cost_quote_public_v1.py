"""Public single-symbol bookTicker REST probe for shadow-only cost gate.

Only called after context state COST_PENDING, bounded number of
requests, no private keys, no exchange order calls.
"""
from __future__ import annotations
import time
from scanner.execution_cost_shadow_v1 import assess_quote

def check_candidate(context,*,get=None,base_url='https://fapi.binance.com'):
 if not isinstance(context,dict) or context.get('state')!='COST_PENDING':
  return {'state':'NOT_QUERIED','reason':'context_gate_not_eligible',
          'ready':False,'order_authorized':False}
 import requests
 from scanner.execution_cost_shadow_v1 import MAX_QUOTE_AGE_MS
 get=get or requests.get
 symbol=context.get('symbol')
 if not isinstance(symbol,str) or not symbol.endswith('USDT'):
  return {'state':'NOT_QUERIED','reason':'invalid_symbol',
          'ready':False,'order_authorized':False}
 now=int(time.time()*1000)
 if not(type(context.get('observed_at_ms')) is int and
        0<=now-context['observed_at_ms']<=MAX_QUOTE_AGE_MS):
  return {'state':'NOT_QUERIED','reason':'context_stale_before_http',
          'ready':False,'order_authorized':False}
 started=time.monotonic()
 try:
  response=get(base_url+'/fapi/v1/ticker/bookTicker',
               params={'symbol':symbol},timeout=2.5)
  response.raise_for_status()
  body=response.json()
 except (requests.RequestException,ValueError,TypeError,AttributeError):
  return {'state':'COST_PENDING','reason':'public_quote_request_failed',
          'ready':False,'order_authorized':False}
 duration_ms=int((time.monotonic()-started)*1000)
 received=int(time.time()*1000)
 if duration_ms>1500:
  return {'state':'COST_PENDING','reason':'public_quote_latency_too_high',
          'roundtrip_latency_ms':duration_ms,'ready':False,'order_authorized':False}
 if not 0<=received-context['observed_at_ms']<=MAX_QUOTE_AGE_MS:
  return {'state':'COST_PENDING','reason':'public_quote_vs_candle_too_old',
          'roundtrip_latency_ms':duration_ms,'ready':False,'order_authorized':False}
 result=assess_quote(symbol,context['direction'],context,body,now_ms=received)
 result['roundtrip_latency_ms']=duration_ms
 result['data_source']='binance_public_usdm_bookTicker_rest'
 result['quote_exchange_timestamp_verified']=False
 return result
