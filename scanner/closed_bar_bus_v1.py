"""Bounded one-copy 1m candle source for 40 USD-M symbols.

Pure cache; REST bootstrap and websocket CLOSED klines only. No exchange
credentials, execution, Telegram network or filesystem writes.
"""
from collections import deque
from scanner.shared_market_snapshot_v1 import parse_closed_klines
from scanner.extreme_momentum_v1 import MS,inspect

class ClosedBarBus:
 def __init__(self, symbols, capacity=180):
  if not isinstance(symbols,list) or len(symbols)>40 or len(symbols)!=len(set(symbols)):
   raise ValueError('invalid unique universe')
  if not 125<=capacity<=250:raise ValueError('invalid capacity')
  self.data={s:deque(maxlen=capacity) for s in symbols}
  self.rejections={}
 def bootstrap(self,symbol,klines,*,asof_ms):
  if symbol not in self.data:raise ValueError('symbol outside subscription')
  try:bars=parse_closed_klines(klines,asof_ms=asof_ms)
  except ValueError as e:
   self.rejections[symbol]='INVALID_BOOTSTRAP'
   self.data[symbol].clear()
   return False
  if len(bars)<65 or asof_ms-(bars[-1]['t']+MS)>2*MS:
   self.rejections[symbol]='STALE_OR_SHORT_BOOTSTRAP'
   self.data[symbol].clear()
   return False
  self.data[symbol].clear()
  self.data[symbol].extend(bars)
  self.rejections.pop(symbol,None)
  return True
 def update_ws(self,symbol,event,*,observed_at_ms):
  if symbol not in self.data:return 'OUTSIDE_UNIVERSE'
  if not isinstance(event,dict) or event.get('s')!=symbol:
   return 'BAD_SOURCE'
  k=event.get('k')
  if not isinstance(k,dict) or k.get('s')!=symbol or k.get('i')!='1m':
   return 'BAD_SOURCE'
  if k.get('x') is not True:return 'PARTIAL_IGNORED'
  try:
   t=int(k['t']);end=int(k['T'])
   if type(observed_at_ms) is not int or not (t+MS<=observed_at_ms<=t+MS+120000):
    return 'FUTURE_OR_STALE_CLOSE'
   raw=[[t,k['o'],k['h'],k['l'],k['c'],k.get('v','0'),
     end,k['q']]]
   parsed=parse_closed_klines(raw,asof_ms=observed_at_ms)
   if len(parsed)!=1:return 'BAD_CANDLE'
   bar=parsed[0]
  except (ValueError,KeyError,TypeError):
   return 'BAD_CANDLE'
  queue=self.data[symbol]
  if queue:
   last=queue[-1]['t']
   if t==last:return 'DUPLICATE_IGNORED'
   if t<last:return 'OUT_OF_ORDER'
   if t-last!=MS:
    queue.clear()
    self.rejections[symbol]='SOURCE_GAP_REQUIRES_BOOTSTRAP'
    return 'GAP_BLOCKED'
  else:
   self.rejections[symbol]='EMPTY_REQUIRES_BOOTSTRAP'
   return 'NEEDS_BOOTSTRAP'
  queue.append(bar)
  self.rejections.pop(symbol,None)
  return 'CLOSED_ACCEPTED'
 def analyze(self,symbol,*,asof_ms):
  if symbol not in self.data:raise ValueError('outside universe')
  if symbol in self.rejections:
   return {'symbol':symbol,'status':'INSUFFICIENT_DATA',
    'reason':self.rejections[symbol],'direction':None,
    'telegram_ready':False,'order_authorized':False}
  return inspect(symbol,list(self.data[symbol]),observed_at_ms=asof_ms)
 def stats(self):
  return {'symbols':len(self.data),
   'valid_symbols':sum(len(q)>=65 and s not in self.rejections
                      for s,q in self.data.items()),
   'bars_cached':sum(len(q) for q in self.data.values()),
   'symbols_needing_rebootstrap':sorted(self.rejections),
   'source_readers_per_symbol':1,'orders':0}
