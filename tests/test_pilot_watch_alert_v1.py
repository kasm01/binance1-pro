import os,unittest
from unittest.mock import patch
from tg_bot.pilot_watch_alert_v1 import candidate,dispatch_candidate
from tg_bot.signal_center_v1 import SignalDispatcher
CTX={'state':'COST_PENDING','symbol':'AAAUSDT','direction':'LONG',
     'observed_at_ms':100001,
     'ready':False,'order_authorized':False}
class TestPilot(unittest.TestCase):
 def setUp(self):
  self.alloc={'LONG1':['AAAUSDT'],'LONG2':['BBB USDT'],
              'SHORT1':['CCCUSDT'],'SHORT2':['DDDUSDT']}
  self.good={'direction':'LONG','status':'STRONG_WATCH',
    'telegram_ready':False,'order_authorized':False,
    'last_completed_1m_close_ms':100000,'reason':'strong_research'}
 def test_only_long1_short1_and_real_allocation(self):
  assert candidate('AAAUSDT','LONG1',self.good,12,observed_at_ms=100001,
                  allocations=self.alloc,context=CTX)
  assert candidate('AAAUSDT','LONG2',self.good,12,observed_at_ms=100001,
                  allocations=self.alloc,context=CTX) is None
  assert candidate('DDDUSDT','SHORT2',dict(self.good,direction='SHORT'),
                   12,observed_at_ms=100001,allocations=self.alloc,context=dict(CTX,symbol='DDDUSDT',direction='SHORT')) is None
  assert candidate('CCCUSDT','SHORT1',dict(self.good,direction='SHORT'),
                   12,observed_at_ms=100001,allocations=self.alloc,context=dict(CTX,symbol='CCCUSDT',direction='SHORT'))
 def test_weak_caution_opposite_and_provenance_block(self):
  for bad in (dict(self.good,status='WATCH'),
              dict(self.good,status='SUPPRESSED_WEAK'),
              dict(self.good,status='EXTREME_CAUTION_WATCH'),
              dict(self.good,direction='SHORT'),
              dict(self.good,telegram_ready=True),
              dict(self.good,order_authorized=True),
              dict(self.good,last_completed_1m_close_ms=100100)):
   assert candidate('AAAUSDT','LONG1',bad,12,observed_at_ms=100001,
     allocations=self.alloc,context=CTX) is None
 def test_context_late_and_cost_reject_never_alert(self):
  for state in ('ENTRY_PENDING','CONTEXT_PENDING','CONTEXT_REJECT','INSUFFICIENT_DATA'):
   assert candidate('AAAUSDT','LONG1',self.good,12,
     observed_at_ms=100001,allocations=self.alloc,
     context=dict(CTX,state=state)) is None
  assert candidate('AAAUSDT','LONG1',self.good,12,
     observed_at_ms=100001,allocations=self.alloc,
     context=CTX,cost={'state':'COST_REJECT'}) is None
  assert candidate('AAAUSDT','LONG1',self.good,12,
     observed_at_ms=100001,allocations=self.alloc,
     context=None) is None
 def test_stale_context_rejected(self):
  assert candidate('AAAUSDT','LONG1',self.good,12,
    observed_at_ms=100002,allocations=self.alloc,context=CTX) is None
 def test_state_cooled_and_disabled(self):
  got=[]
  d=SignalDispatcher(sender=lambda x:got.append(x) or True,
                     bot_allocations=self.alloc,cooldown_s=7200)
  with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'0',
                            'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'0'}):
   assert dispatch_candidate(d,'AAAUSDT','LONG1',self.good,12,
      observed_at_ms=100001,allocations=self.alloc,context=CTX)=='PREVIEW_ONLY'
  with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'1',
                            'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'1'}):
   assert dispatch_candidate(d,'AAAUSDT','LONG1',self.good,12,
      observed_at_ms=100001,allocations=self.alloc,context=CTX)=='SENT'
   assert dispatch_candidate(d,'AAAUSDT','LONG1',self.good,12,
      observed_at_ms=100002,allocations=self.alloc,
      context=dict(CTX,observed_at_ms=100002))=='DEDUPED'
  assert len(got)==1 and 'MANUEL' in got[0]
if __name__=='__main__':unittest.main()
