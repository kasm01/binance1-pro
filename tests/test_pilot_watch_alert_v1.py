import os,unittest
from unittest.mock import patch
from tg_bot.pilot_watch_alert_v1 import candidate,dispatch_candidate
from tg_bot.signal_center_v1 import SignalDispatcher
class TestPilot(unittest.TestCase):
 def setUp(self):
  self.alloc={'LONG1':['AAAUSDT'],'LONG2':['BBB USDT'],
              'SHORT1':['CCCUSDT'],'SHORT2':['DDDUSDT']}
  self.good={'direction':'LONG','status':'STRONG_WATCH',
    'telegram_ready':False,'order_authorized':False,
    'last_completed_1m_close_ms':100000,'reason':'strong_research'}
 def test_only_long1_short1_and_real_allocation(self):
  assert candidate('AAAUSDT','LONG1',self.good,12,observed_at_ms=100001,
                  allocations=self.alloc)
  assert candidate('AAAUSDT','LONG2',self.good,12,observed_at_ms=100001,
                  allocations=self.alloc) is None
  assert candidate('DDDUSDT','SHORT2',dict(self.good,direction='SHORT'),
                   12,observed_at_ms=100001,allocations=self.alloc) is None
  assert candidate('CCCUSDT','SHORT1',dict(self.good,direction='SHORT'),
                   12,observed_at_ms=100001,allocations=self.alloc)
 def test_weak_caution_opposite_and_provenance_block(self):
  for bad in (dict(self.good,status='WATCH'),
              dict(self.good,status='SUPPRESSED_WEAK'),
              dict(self.good,status='EXTREME_CAUTION_WATCH'),
              dict(self.good,direction='SHORT'),
              dict(self.good,telegram_ready=True),
              dict(self.good,order_authorized=True),
              dict(self.good,last_completed_1m_close_ms=100100)):
   assert candidate('AAAUSDT','LONG1',bad,12,observed_at_ms=100001,
     allocations=self.alloc) is None
 def test_state_cooled_and_disabled(self):
  got=[]
  d=SignalDispatcher(sender=lambda x:got.append(x) or True,
                     bot_allocations=self.alloc,cooldown_s=7200)
  with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'0',
                            'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'0'}):
   assert dispatch_candidate(d,'AAAUSDT','LONG1',self.good,12,
      observed_at_ms=100001,allocations=self.alloc)=='PREVIEW_ONLY'
  with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'1',
                            'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'1'}):
   assert dispatch_candidate(d,'AAAUSDT','LONG1',self.good,12,
      observed_at_ms=100001,allocations=self.alloc)=='SENT'
   assert dispatch_candidate(d,'AAAUSDT','LONG1',self.good,12,
      observed_at_ms=100002,allocations=self.alloc)=='DEDUPED'
  assert len(got)==1 and 'MANUEL' in got[0]
if __name__=='__main__':unittest.main()
