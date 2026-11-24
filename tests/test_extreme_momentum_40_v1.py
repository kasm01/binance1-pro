"""No future candles, fail-closed stale/gap, weak suppression and extremes."""
import unittest
from scanner.extreme_momentum_v1 import inspect
from scanner.universe_extreme_overlay_v1 import select_movers
START=1794500000000-(1794500000000%60000)
def bars(*,direction=1,move=.002,spike_volume=8,flat=False):
 out=[]
 last=10.
 for i in range(65):
  new=last*(1+(direction*move if not flat else 0))
  o=last;c=new
  out.append({'t':START+i*60000,'o':o,'h':max(o,c)*1.0001,
    'l':min(o,c)*.9999,'c':c,
    'quote_volume':1_000_000*(spike_volume if i>=60 else 1)})
  last=new
 return out
ASOF=START+65*60000
class TestExtreme(unittest.TestCase):
 def test_fast_long_short_but_only_watch(self):
  for direction,expected in ((1,'LONG'),(-1,'SHORT')):
   r=inspect('MOVUSDT',bars(direction=direction),observed_at_ms=ASOF)
   assert r['direction']==expected
   assert r['status'] in ('STRONG_WATCH','EXTREME_WATCH'),r
   assert r['relative_volume_5m']>=1.6
   assert r['telegram_ready'] is False
   assert r['order_authorized'] is False
 def test_noise_and_volume_suppression(self):
  x=inspect('MOVUSDT',bars(flat=True),observed_at_ms=ASOF)
  assert x['status']=='SUPPRESSED_WEAK'
  y=inspect('MOVUSDT',bars(spike_volume=1),observed_at_ms=ASOF)
  assert y['status'] in ('SUPPRESSED_WEAK','EXTREME_CAUTION_WATCH')
  assert y['reason'] in ('volume_not_expanded',
                         'extreme_price_move_without_volume_expansion')
  assert not y['telegram_ready']
 def test_no_future_stale_missing_or_dup(self):
  rows=bars()
  assert inspect('MOVUSDT',rows,observed_at_ms=ASOF-1)['status']=='INSUFFICIENT_DATA'
  assert inspect('MOVUSDT',rows,observed_at_ms=ASOF+180001)['reason']=='stale_market_data'
  no=rows.copy();no[15]=dict(no[15],t=no[15]['t']+60000)
  assert inspect('MOVUSDT',no,observed_at_ms=ASOF)['reason']=='gap_or_duplicate'
  bad=rows.copy();bad[-1]=dict(bad[-1],c=-1.)
  assert inspect('MOVUSDT',bad,observed_at_ms=ASOF)['reason']=='invalid_ohlcv'
 def test_volume_overlay_reaches_movers_outside_liquid_top40(self):
  info={'symbols':[{'symbol':f'X{i}USDT','baseAsset':f'X{i}',
   'quoteAsset':'USDT','contractType':'PERPETUAL','status':'TRADING'}
   for i in range(100)]}
  ticker=[{'symbol':f'X{i}USDT','quoteVolume':str((100-i)*1_000_000),
    'priceChangePercent':'12.0' if i in (80,90) else '2.0'} for i in range(100)]
  x=select_movers(info,ticker)
  assert x['total_unique']==40
  assert {'X80USDT','X90USDT'}<=set(x['unique_symbols'])
  assert x['mover_slots_selected']==2
  assert set(x['unique_symbols']).isdisjoint({f'X{i}USDT' for i in range(15)})
  assert x['bot_allocations']['LONG1']==x['bot_allocations']['SHORT1']
  assert not x['no_order_authority'] is False
 def test_overlay_no_force_bad_liquidity(self):
  info={'symbols':[{'symbol':f'X{i}USDT','baseAsset':f'X{i}',
   'quoteAsset':'USDT','contractType':'PERPETUAL','status':'TRADING'}
   for i in range(20)]}
  ticker=[{'symbol':f'X{i}USDT','quoteVolume':'1000000',
    'priceChangePercent':'800'} for i in range(20)]
  x=select_movers(info,ticker)
  assert x['total_unique']==0
  assert x['mover_slots_selected']==0
if __name__=='__main__':unittest.main()
