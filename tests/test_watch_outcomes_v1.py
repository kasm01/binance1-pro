import json,tempfile,unittest
from pathlib import Path
from scanner.watch_outcomes_v1 import OutcomeLedger,evaluate_path,MS
START=1800000000000-(1800000000000%MS)
def bar(t,c,h=None,l=None):
 return {'t':t,'o':c,'h':h if h is not None else c*1.01,
  'l':l if l is not None else c*.99,'c':c,'quote_volume':50000}
SCAN={'status':'STRONG_WATCH','direction':'LONG',
      'last_completed_1m_close_ms':START,'telegram_ready':False,
      'order_authorized':False}
CTX={'state':'ENTRY_PENDING','reason':'late_extension_over_3atr'}
class Test(unittest.TestCase):
 def test_long_short_exact_future_math_and_no_lookahead(self):
  bars=[bar(START+i*MS,100+i*.1,101+i*.1,99+i*.1) for i in range(60)]
  long={'reference_close_ms':START,'reference_price':100.,'direction':'LONG'}
  short=dict(long,direction='SHORT')
  assert evaluate_path(long,bars[:4],horizon=5) is None
  a=evaluate_path(long,bars,horizon=5)
  assert a['mfe_pct']==1.4 and a['mae_pct']==-1.0
  assert a['terminal_directional_pct']==.4
  b=evaluate_path(short,bars,horizon=5)
  assert b['mfe_pct']==1.0 and b['mae_pct']==-1.4
  assert b['terminal_directional_pct']==-.4
  assert b['not_fill_or_ROI']
 def test_persistent_episode_incremental_horizons(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'outcomes.json'
   o=OutcomeLedger(p)
   assert o.observe('AAAUSDT','LONG',SCAN,CTX,
     reference_close_ms=START,reference_price=100)=='OBSERVED'
   assert o.observe('AAAUSDT','LONG',SCAN,CTX,
     reference_close_ms=START,reference_price=100)=='EPISODE_DEDUPED'
   bars=[bar(START+i*MS,100+i*.1) for i in range(60)]
   assert o.advance('AAAUSDT',bars[:4],last_close_ms=START+4*MS)==0
   assert o.advance('AAAUSDT',bars[:5],last_close_ms=START+5*MS)==1
   assert set(o.events[0]['outcomes'])=={'5'}
   restored=OutcomeLedger(p)
   assert restored.healthy
   assert restored.advance('AAAUSDT',bars,last_close_ms=START+60*MS)==3
   assert set(restored.events[0]['outcomes'])=={'5','15','30','60'}
   assert restored.summary()['outcome_events_complete']==1
   assert not restored.events[0]['trade_executed']
   assert p.stat().st_mode & 0o077==0
 def test_missing_middle_bar_invalidates_no_fictional_mae(self):
  with tempfile.TemporaryDirectory() as temp:
   o=OutcomeLedger(Path(temp)/'events.json')
   o.observe('AAAUSDT','LONG',SCAN,CTX,reference_close_ms=START,reference_price=100)
   bad=[bar(START+i*MS,100) for i in range(6) if i!=3]
   assert o.advance('AAAUSDT',bad,last_close_ms=START+6*MS)==1
   assert o.summary()['outcome_events_invalid']==1
   assert not o.events[0]['outcomes']
 def test_corrupt_state_and_no_future_bootstrap_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'events.json'
   p.write_text('{bad')
   o=OutcomeLedger(p)
   assert not o.healthy
   assert o.observe('AAAUSDT','LONG',SCAN,CTX,
      reference_close_ms=START,reference_price=100)=='LEDGER_UNAVAILABLE'
 def test_wrong_origin_state_source_disallowed(self):
  with tempfile.TemporaryDirectory() as temp:
   o=OutcomeLedger(Path(temp)/'events.json')
   assert o.observe('AAAUSDT','SHORT',SCAN,CTX,
     reference_close_ms=START,reference_price=100)=='SOURCE_UNVERIFIED'
   assert o.observe('AAAUSDT','LONG',dict(SCAN,status='WATCH'),CTX,
     reference_close_ms=START,reference_price=100)=='NOT_STRONG_WATCH'
   assert not o.events
if __name__=='__main__':unittest.main()
