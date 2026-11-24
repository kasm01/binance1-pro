"""Retain 40 distinct USD-M futures symbols while discovering extreme movers
outside top-volume rank 15. NO API, NO orders. 24h percent is only
discovery, not a BUY/SHORT signal. Keep liquid volume-ranked core as fallback.
"""
from __future__ import annotations
from scanner.universe_40_v1 import select, _num, BOT_SIDES
def select_movers(exchange_info,tickers,*,skip_rank=15,max_coins=40,
                  min_quote_volume_usdt=5_000_000,mover_slots=12,
                  move_24h_floor_pct=8.0):
 if not(type(mover_slots) is int and 0<=mover_slots<=max_coins<=40):
  raise ValueError('bad mover slots')
 if not (0<=move_24h_floor_pct<=100):
  raise ValueError('invalid move floor')
 base=select(exchange_info,tickers,skip_rank=skip_rank,
  max_coins=max_coins,min_quote_volume_usdt=min_quote_volume_usdt)
 excluded=set(base['excluded_top_rank_symbols'])
 eligible={s['symbol']:s['baseAsset'] for s in exchange_info.get('symbols',[])
  if isinstance(s,dict) and s.get('status')=='TRADING'
  and s.get('contractType')=='PERPETUAL' and s.get('quoteAsset')=='USDT'
  and isinstance(s.get('symbol'),str) and isinstance(s.get('baseAsset'),str)
  and s['baseAsset'] not in {'USDT','USDC','FDUSD','TUSD','BUSD'}}
 moves=[]
 ticker_volumes={}
 for t in tickers:
  if not isinstance(t,dict):continue
  symbol=t.get('symbol')
  if symbol not in eligible or symbol in excluded:continue
  vol=_num(t.get('quoteVolume'))
  change=_num_abs_signed(t.get('priceChangePercent'))
  if vol is None or vol<min_quote_volume_usdt:continue
  ticker_volumes[symbol]=vol
  if change is not None and abs(change)>=move_24h_floor_pct:
   moves.append((symbol,change,vol))
 # Large magnitude plus high volume disambiguation; do NOT claim ROI probability.
 moves.sort(key=lambda x:(-abs(x[1]),-x[2],x[0]))
 ordered=[];bases=set()
 for symbol,change,vol in moves:
  if len(ordered)==mover_slots:break
  if eligible[symbol] in bases:continue
  ordered.append(symbol);bases.add(eligible[symbol])
 mover_count=len(ordered)
 # Use existing 24h volume core to fill; those not top40 can still
 # be found by mover preselection on all eligible tickers.
 remaining=sorted(ticker_volumes,key=lambda s:(-ticker_volumes[s],s))
 for s in remaining:
  if len(ordered)>=max_coins:break
  if eligible[s] in bases:continue
  ordered.append(s);bases.add(eligible[s])
 allocation={f'{side}{i}':ordered[(i-1)*10:i*10] for side in BOT_SIDES for i in range(1,5)}
 return {'schema':'manual_universe_extreme_overlay.v1',
  'excluded_top_volume_15':base['excluded_top_rank_symbols'],
  'unique_symbols':ordered,'mover_slots_selected':mover_count,
  'mover_discovery_symbols':ordered[:mover_count],
  'bot_allocations':allocation,
  'not_momentum_trade_signals':True,'dynamic_membership':True,
  'total_unique':len(ordered),'no_order_authority':True}
def _num_abs_signed(x):
 try:
  n=float(x)
  from math import isfinite
  return n if isfinite(n) else None
 except (TypeError,ValueError):return None
