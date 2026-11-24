import tempfile,unittest
from pathlib import Path
from scanner.watch_outcomes_v1 import OutcomeLedger,MS
START=1800000000000-(1800000000000%MS)
def early(direction='LONG'):
 return {'symbol':'AAAUSDT','state':'EARLY_CANDIDATE_SHADOW',
  'direction':direction,'last_completed_1m_close_ms':START,
  'ready':False,'telegram_ready':False,'order_authorized':False,
  'reason':'3m_breakout_expanding_volume'}
def candle(i):
 return {'t':START+i*MS,'o':100,'h':101,'l':99,'c':100,'quote_volume':500}
class Test(unittest.TestCase):
 def test_early_separate_persist_resume_and_never_trade(self):
  with tempfile.TemporaryDirectory() as p:
   f=Path(p)/'early.json'
   x=OutcomeLedger(f)
   assert x.observe_early('AAAUSDT','LONG',early(),
     reference_close_ms=START,reference_price=100)=='OBSERVED'
   assert x.observe_early('AAAUSDT','LONG',early(),
     reference_close_ms=START,reference_price=100)=='EPISODE_DEDUPED'
   y=OutcomeLedger(f)
   assert y.healthy and len(y.events)==1
   assert y.events[0]['telegram_sent'] is False
   assert y.events[0]['trade_executed'] is False
   assert y.advance('AAAUSDT',[candle(i) for i in range(5)],
     last_close_ms=START+5*MS)==1
   z=OutcomeLedger(f)
   assert z.events[0]['outcomes']['5']['mfe_pct']==1.0
   assert z.summary()['real_trades']==0
 def test_bad_source_never_recorded(self):
  with tempfile.TemporaryDirectory() as p:
   x=OutcomeLedger(Path(p)/'early.json')
   for bad in [dict(early(),order_authorized=True),
               dict(early(),telegram_ready=True),
               dict(early(),last_completed_1m_close_ms=START+MS),
               dict(early(),state='NO_EARLY_CANDIDATE')]:
    assert x.observe_early('AAAUSDT','LONG',bad,
       reference_close_ms=START,reference_price=100)!='OBSERVED'
   assert not x.events
 def test_missing_bar_invalidates_and_does_not_fake_fill(self):
  with tempfile.TemporaryDirectory() as p:
   x=OutcomeLedger(Path(p)/'early.json')
   x.observe_early('AAAUSDT','LONG',early(),
      reference_close_ms=START,reference_price=100)
   missing=[candle(i) for i in range(15) if i!=6]
   assert x.advance('AAAUSDT',missing,last_close_ms=START+15*MS)>0
   assert x.events[0]['invalid_reason']=='missing_or_discontinuous_future_bars'
   assert x.events[0]['final']
if __name__=='__main__':unittest.main()
