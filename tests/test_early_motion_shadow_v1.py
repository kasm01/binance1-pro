import unittest
from scanner.early_motion_shadow_v1 import inspect_early
from scanner.extreme_momentum_v1 import MS
START=1800000000000-(1800000000000%MS)
def bars(direction=1,strong=True,vol=True):
 price=10.0;out=[]
 for i in range(70):
  delta=direction*(.003 if i>=67 and strong else .00002)
  nxt=price*(1+delta)
  out.append({'t':START+i*MS,'o':price,
    'h':max(price,nxt)*1.0002,'l':min(price,nxt)*.9998,
    'c':nxt,'quote_volume':1e6*(6 if vol and i>=67 else 1)})
  price=nxt
 return out
class Test(unittest.TestCase):
 def test_3m_movement_both_directions_no_ready(self):
  for d in (1,-1):
   b=bars(d);x=inspect_early('XYZUSDT',b,observed_at_ms=START+70*MS)
   assert x['state']=='EARLY_CANDIDATE_SHADOW',x
   assert x['direction']==('LONG' if d>0 else 'SHORT')
   assert x['ready'] is False and x['telegram_ready'] is False and x['order_authorized'] is False
 def test_weak_and_no_volume(self):
  for b in (bars(strong=False),bars(vol=False)):
   x=inspect_early('XYZUSDT',b,observed_at_ms=START+70*MS)
   assert x['state']=='NO_EARLY_CANDIDATE',x
 def test_stale_partial_gap(self):
  b=bars()
  assert inspect_early('XYZUSDT',b,observed_at_ms=START+70*MS-1)['state']=='INSUFFICIENT_DATA'
  assert inspect_early('XYZUSDT',b,observed_at_ms=START+74*MS)['state']=='INSUFFICIENT_DATA'
  bad=list(b);bad[-2]=dict(bad[-2],t=bad[-2]['t']-MS)
  assert inspect_early('XYZUSDT',bad,observed_at_ms=START+70*MS)['state']=='INSUFFICIENT_DATA'
if __name__=='__main__':unittest.main()
