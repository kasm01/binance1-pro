import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tg_bot.early_watch_pilot_v1 import EarlyWatchDispatcher,eligibility,format_early
T=1795541400000
def e(symbol='AAAUSDT',direction='LONG'):
 return {'state':'EARLY_CANDIDATE_SHADOW','symbol':symbol,'direction':direction,
  'last_completed_1m_close_ms':T-250,
  'ret3_pct':0.9,'ret5_pct':1.2,'ret15_pct':1.8,'volume_ratio3':2.2,
  'ready':False,'telegram_ready':False,'order_authorized':False}
FLOW={'state':'FLOW_SUPPORTIVE','ready':False,'telegram_ready':False,
      'order_authorized':False}
ALLOC={'LONG1':['AAAUSDT','BBBUSDT','CCCUSDT','DDDUSDT','EEEUSDT',
                'FFFUSDT','GGGUSDT'],'SHORT2':['SHORTUSDT']}
FLAGS={'TELEGRAM_SIGNAL_CENTER_ENABLED':'1',
       'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'1',
       'TELEGRAM_EARLY_WATCH_ENABLED':'1'}
class Test(unittest.TestCase):
 def test_opt_in_and_manual_warning_and_private_persistence(self):
  with tempfile.TemporaryDirectory() as path:
   delivered=[];file=Path(path)/'early.json'
   with patch.dict(os.environ,FLAGS),patch('time.time',return_value=T/1000):
    dispatch=EarlyWatchDispatcher(file,sender=lambda msg:delivered.append(msg) or True)
    got=dispatch.send_early('AAAUSDT','LONG',e(),FLOW,ALLOC,10.25,now_ms=T)
    assert got=='SENT'
    assert len(delivered)==1
    assert 'ERKEN İZLEME' in delivered[0]
    assert 'GİRİŞ ONAYI / READY DEĞİL' in delivered[0]
    assert 'Otomatik Binance emri YOK' in delivered[0]
    assert 'BUY' not in delivered[0]
    assert file.stat().st_mode & 0o077==0
    again=EarlyWatchDispatcher(file,sender=lambda msg:delivered.append(msg) or True)
    assert again.healthy
    assert again.send_early('AAAUSDT','LONG',e(),FLOW,ALLOC,10.25,now_ms=T)=='DEDUPED'
    assert len(delivered)==1
 def test_early_requires_explicit_opt_in(self):
  with tempfile.TemporaryDirectory() as path:
   delivered=[]
   with patch.dict(os.environ,dict(FLAGS,TELEGRAM_EARLY_WATCH_ENABLED='0')):
    x=EarlyWatchDispatcher(Path(path)/'early.json',sender=lambda msg:delivered.append(msg) or True)
    assert x.send_early('AAAUSDT','LONG',e(),FLOW,ALLOC,10,now_ms=T)=='PREVIEW_ONLY'
    assert not delivered
 def test_flow_opposing_exhausted_missing_and_unallocated(self):
  for flow in ('FLOW_OPPOSING','FLOW_EXHAUSTION_CAUTION','FLOW_UNVERIFIED'):
   assert eligibility('AAAUSDT','LONG',e(),dict(FLOW,state=flow),ALLOC,now_ms=T) is None
  assert eligibility('ZZZUSDT','LONG',e('ZZZUSDT'),FLOW,ALLOC,now_ms=T) is None
  assert eligibility('AAAUSDT','SHORT',e(),FLOW,ALLOC,now_ms=T) is None
  assert eligibility('AAAUSDT','LONG',dict(e(),ready=True),FLOW,ALLOC,now_ms=T) is None
  assert eligibility('AAAUSDT','LONG',dict(e(),last_completed_1m_close_ms=T-90000),
          FLOW,ALLOC,now_ms=T) is None
 def test_global_throttle(self):
  with tempfile.TemporaryDirectory() as path:
   sent=[]
   with patch.dict(os.environ,FLAGS):
    d=EarlyWatchDispatcher(Path(path)/'early.json',sender=lambda msg:sent.append(msg) or True)
    letters=['AAA','BBB','CCC','DDD','EEE','FFF','GGG']
    for index,letter in enumerate(letters[:6]):
     now=T+index*3*60000+100
     data=e(letter+'USDT')
     data['last_completed_1m_close_ms']=now-250
     with patch('time.time',return_value=now/1000):
      assert d.send_early(letter+'USDT','LONG',data,FLOW,ALLOC,10,now_ms=now)=='SENT'
    now=T+6*3*60000+100
    data=e('GGGUSDT');data['last_completed_1m_close_ms']=now-250
    with patch('time.time',return_value=now/1000):
     assert d.send_early('GGGUSDT','LONG',data,FLOW,ALLOC,10,now_ms=now)=='GLOBAL_HOURLY_LIMIT'
    assert len(sent)==6
 def test_corrupt_state_fails_closed(self):
  with tempfile.TemporaryDirectory() as path:
   p=Path(path)/'early.json';p.write_text('not-json')
   sent=[]
   with patch.dict(os.environ,FLAGS):
    d=EarlyWatchDispatcher(p,sender=lambda msg:sent.append(msg) or True)
    assert not d.healthy
    assert d.send_early('AAAUSDT','LONG',e(),FLOW,ALLOC,10,now_ms=T)=='PERSISTENCE_UNAVAILABLE'
    assert not sent
 def test_short2_assignment(self):
  a=e('SHORTUSDT','SHORT')
  assert eligibility('SHORTUSDT','SHORT',a,FLOW,ALLOC,now_ms=T)=='SHORT2'
 def test_failed_delivery_does_not_persist(self):
  with tempfile.TemporaryDirectory() as path:
   p=Path(path)/'early.json'
   with patch.dict(os.environ,FLAGS),patch('time.time',return_value=T/1000):
    d=EarlyWatchDispatcher(p,sender=lambda _:False)
    assert d.send_early('AAAUSDT','LONG',e(),FLOW,ALLOC,10,now_ms=T)=='SEND_NOT_CONFIRMED'
    assert not p.exists()
if __name__=='__main__':unittest.main()
