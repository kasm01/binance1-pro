import unittest
from scanner.extreme_momentum_v1 import MS
from scanner.scalp_preparation_shadow_v1 import inspect_preparation
BASE=1800000000000-(1800000000000%MS)
def bars(step=.0003,buy=.68):
 p=100.;result=[]
 for i in range(100):
  o=p;p*=1+step
  result.append({'t':BASE+i*MS,'o':o,'c':p,'h':max(o,p)*1.0002,
    'l':min(o,p)*.9998,'quote_volume':1000.,
    'taker_buy_quote_volume':buy*1000.})
 return result
class Test(unittest.TestCase):
 def test_trend_continuation_long_short(self):
  for step,buy,direction in ((.0003,.68,'LONG'),(-.0003,.32,'SHORT')):
   x=inspect_preparation('AAAUSDT',bars(step,buy),
                       observed_at_ms=BASE+100*MS)
   assert x['state']=='PREPARATION_SHADOW',x
   assert x['mode']=='TREND_CONTINUATION'
   assert x['direction']==direction
   assert x['ready'] is False and x['telegram_ready'] is False
 def test_unverified_missing_flow_gap_and_future(self):
  b=bars();b[-1].pop('taker_buy_quote_volume')
  assert inspect_preparation('AAAUSDT',b,observed_at_ms=BASE+100*MS)['state']=='PREPARATION_UNVERIFIED'
  b=bars();b[-2]['t']+=MS
  assert inspect_preparation('AAAUSDT',b,observed_at_ms=BASE+100*MS)['state']=='PREPARATION_UNVERIFIED'
  b=bars()
  assert inspect_preparation('AAAUSDT',b,observed_at_ms=BASE+100*MS-1)['state']=='PREPARATION_UNVERIFIED'
 def test_no_lookahead(self):
  b=bars()
  a=inspect_preparation('AAAUSDT',b[:-1],observed_at_ms=BASE+99*MS)
  b[-1]['c']*=1.1;b[-1]['h']*=1.1
  x=inspect_preparation('AAAUSDT',b[:-1],observed_at_ms=BASE+99*MS)
  assert x==a
if __name__=='__main__':unittest.main()
