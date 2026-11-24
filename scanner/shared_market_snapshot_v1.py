"""40-symbol shared CLOSED-1m snapshot engine: no network, no orders.

One canonical data snapshot per symbol is shared across LONGx and SHORTx.
Reject unverified, misaligned, duplicate, missing or partial bars.
Data is not promoted to a real execution-ready entry.
"""
from __future__ import annotations
from collections.abc import Mapping
from scanner.extreme_momentum_v1 import inspect,MS,MIN_HISTORY,number

FIELDS=('o','h','l','c','quote_volume')
def parse_closed_klines(raw,*,asof_ms):
 if type(asof_ms) is not int or asof_ms<=0:raise ValueError('invalid asof')
 if not isinstance(raw,list):raise ValueError('klines must be list')
 result=[];seen=set()
 for entry in raw:
  if not isinstance(entry,(list,tuple)) or len(entry)<8:
   raise ValueError('invalid kline layout')
  try:t=int(entry[0]);end=int(entry[6])
  except (TypeError,ValueError):raise ValueError('bad kline timestamps')
  if t%MS or end!=t+MS-1 or t in seen:raise ValueError('noncanonical or duplicate kline')
  seen.add(t)
  if end>=asof_ms:
   # Only the final partial bar is allowed to be dropped; never
   # drop an internal future bar and then silently pretend continuity.
   if raw[-1] is not entry:raise ValueError('nonfinal future bar')
   continue
  o,h,l,c,q=(number(entry[i]) for i in (1,2,3,4,7))
  if None in (o,h,l,c,q) or min(o,h,l,c)<=0 or q<0:
   raise ValueError('invalid price or volume')
  if l>min(o,c) or h<max(o,c,l):raise ValueError('invalid OHLC')
  if result and t!=result[-1]['t']+MS:raise ValueError('missing source bar')
  bar={'t':t,'o':o,'h':h,'l':l,'c':c,'quote_volume':q}
  # Binance USD-M REST kline index 10 = taker BUY quote volume.
  # Older fixtures intentionally omit this field: remain compatible,
  # but NEVER fabricate flow from total volume or candle direction.
  if len(entry)>10:
   taker_buy=number(entry[10])
   if taker_buy is None or taker_buy<0 or taker_buy>q*(1+1e-7)+1e-7:
    raise ValueError('invalid taker buy quote volume')
   bar['taker_buy_quote_volume']=taker_buy
  result.append(bar)
 return result

def evaluate(*,selected_symbols,bot_allocations,klines_by_symbol,
             observed_at_ms,universe_time_ms,universe_ttl_ms=900000):
 """Return safe per-bot watch only. No signal state READY can arise."""
 if type(observed_at_ms) is not int or observed_at_ms<=0:
  raise ValueError('missing observation clock')
 if type(universe_time_ms) is not int or not (0<=observed_at_ms-universe_time_ms<=universe_ttl_ms):
  raise ValueError('stale or future universe snapshot')
 if not isinstance(selected_symbols,list) or len(selected_symbols)>40:
  raise ValueError('invalid universe length')
 if len(selected_symbols)!=len(set(selected_symbols)):
  raise ValueError('duplicate universe symbol')
 if not isinstance(bot_allocations,Mapping) or not isinstance(klines_by_symbol,Mapping):
  raise ValueError('invalid scanner sources')
 if set(klines_by_symbol)-set(selected_symbols):
  raise ValueError('unallocated market sources')
 for bot,syms in bot_allocations.items():
  if bot not in {f'{direction}{i}' for direction in ('LONG','SHORT') for i in range(1,5)}:
   raise ValueError('unknown strategy')
  if not isinstance(syms,list) or len(syms)>10 or any(s not in selected_symbols for s in syms):
   raise ValueError('bot outside universe')
 shared={}
 for symbol in selected_symbols:
  raw=klines_by_symbol.get(symbol)
  if raw is None:
   shared[symbol]={'symbol':symbol,'status':'INSUFFICIENT_DATA',
     'reason':'NO_SOURCE','direction':None,'telegram_ready':False,
     'order_authorized':False}
   continue
  try:
   closed=parse_closed_klines(raw,asof_ms=observed_at_ms)
   shared[symbol]=inspect(symbol,closed,observed_at_ms=observed_at_ms)
  except ValueError:
   shared[symbol]={'symbol':symbol,'status':'INSUFFICIENT_DATA',
     'reason':'INVALID_SOURCE','direction':None,
     'telegram_ready':False,'order_authorized':False}
 result={}
 for bot,syms in sorted(bot_allocations.items()):
  direction='LONG' if bot.startswith('LONG') else 'SHORT'
  rows=[]
  for symbol in syms:
   x=shared[symbol]
   permitted_direction=x.get('direction')==direction
   # Never turn an opposite-side extreme into a proposed position.
   rows.append({'symbol':symbol,'scanner_status':x['status'],
      'watch_for_this_bot':bool(permitted_direction and
        x['status'] in ('STRONG_WATCH','EXTREME_WATCH',
                      'EXTREME_CAUTION_WATCH','WATCH')),
      'scanner_direction':x.get('direction'),
      'reason':x.get('reason'),
      'ret15_pct':x.get('ret15_pct'),
      'quote_relative_volume_5m':x.get('relative_volume_5m'),
      'order_authorized':False,'telegram_ready':False})
  result[bot]=rows
 return {'schema':'manual_shared40_closed1m_snapshot.v1',
  'observed_at_ms':observed_at_ms,
  'unique_klines_sources_scanned':len(shared),
  'unique_symbols':selected_symbols,
  'universe_timestamp_ms':universe_time_ms,
  'per_symbol':shared,'per_bot':result,
  'watch_candidates_by_direction':{
   direction:sorted({r['symbol'] for bot,rows in result.items()
    if bot.startswith(direction) for r in rows if r['watch_for_this_bot']})
   for direction in ('LONG','SHORT')},
  'no_telegram_sent':True,'no_order_authority':True,
  'no_live_entry_validation':True}
