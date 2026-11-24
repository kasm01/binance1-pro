"""Pure, offline-first Binance USD-M universe selection. NO orders, NO HTTP.

Top-15 exclusion is ranked by 24h USDT quote volume, NOT market cap
and NOT automatically proof of weak BTC correlation.
40 unique assets shared by LONG1..4 and SHORT1..4; 10 each per side.
"""
from __future__ import annotations
from collections.abc import Mapping
from math import isfinite
from typing import Any

BOT_SIDES=('LONG','SHORT')
BOT_NAMES=tuple(f'{side}{i}' for side in BOT_SIDES for i in range(1,5))
def _num(x:Any)->float|None:
 try:
  n=float(x)
  return n if isfinite(n) and n>=0 else None
 except (ValueError,TypeError):return None
def select(exchange_info:Mapping, tickers:list, *,skip_rank=15,max_coins=40,
           min_quote_volume_usdt=5_000_000)->dict:
 if not (type(skip_rank)==int and 0<=skip_rank<=100 and
         type(max_coins)==int and 1<=max_coins<=40):
  raise ValueError('invalid universe bounds')
 symbols={}
 for x in exchange_info.get('symbols',[]):
  if not isinstance(x,dict):continue
  sym=x.get('symbol')
  if not isinstance(sym,str) or not sym.endswith('USDT'):continue
  if (x.get('quoteAsset')!='USDT' or x.get('contractType')!='PERPETUAL'
      or x.get('status')!='TRADING'):continue
  base=x.get('baseAsset')
  if not isinstance(base,str) or not base:continue
  # Avoid test/leveraged tokens or synthetic quote names; stablecoin collateral pairs excluded
  if base in {'USDT','USDC','FDUSD','TUSD','BUSD'}:continue
  symbols[sym]=base
 ranked=[]
 seen=set()
 for row in tickers:
  if not isinstance(row,dict):continue
  sym=row.get('symbol')
  if sym not in symbols or sym in seen:continue
  seen.add(sym)
  v=_num(row.get('quoteVolume'))
  if v is None:continue
  ranked.append((sym,symbols[sym],v))
 ranked.sort(key=lambda x:(-x[2],x[0]))
 # Exclude highest liquidity rank, regardless of minimum volume filter.
 excluded=ranked[:skip_rank]
 rest=[r for r in ranked[skip_rank:] if r[2]>=min_quote_volume_usdt]
 # One futures asset only: if more than one eligible pair exists, keep best liquidity.
 chosen=[];bases=set()
 for sym,base,vol in rest:
  if base in bases:continue
  chosen.append(sym);bases.add(base)
  if len(chosen)==max_coins:break
 assignment={side+str(i):chosen[(i-1)*10:i*10]
             for side in BOT_SIDES for i in range(1,5)}
 return {'schema':'binance1_manual_signal_universe_v1',
  'source':'USD-M_PERPETUAL_TRADING_USDT',
  'ranking':'24h_quoteVolume_usdt_not_market_cap',
  'skip_rank':skip_rank,'max_unique_symbols':max_coins,
  'min_24h_quote_volume_usdt':min_quote_volume_usdt,
  'excluded_top_rank_symbols':[r[0] for r in excluded],
  'selected_symbols':chosen,
  'unique_count':len(chosen),
  'both_directions_same_universe':True,
  'bot_allocations':assignment,
  'no_forced_fill_when_under_40':True,
  'btc_correlation_not_yet_measured':True,
  'rank_and_24h_window_are_dynamic':True,
  'live_order_authority':False,
  'manual_trading_only':True}
