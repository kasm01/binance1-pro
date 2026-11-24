import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tg_bot.signal_center_v1 import SignalDispatcher
S={'symbol':'ELSAUSDT','strategy':'SHORT1','state':'WATCH',
   'observed_at_ms':1800000000000,'price':1.25,'reason':'strong_momentum_test'}
class Test(unittest.TestCase):
 def test_confirmed_delivery_is_persisted_across_restart(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'telegram.json';events=[]
   with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'1',
     'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'1'}):
    first=SignalDispatcher(sender=lambda msg:events.append(msg) or True,
      bot_allocations={'SHORT1':['ELSAUSDT']},cooldown_s=7200,persistent_state_path=path)
    assert first.dispatch(S,now_ms=S['observed_at_ms'])=='SENT'
    assert path.stat().st_mode & 0o077==0
    second=SignalDispatcher(sender=lambda msg:events.append(msg) or True,
      bot_allocations={'SHORT1':['ELSAUSDT']},cooldown_s=7200,persistent_state_path=path)
    assert second.dispatch(dict(S,observed_at_ms=S['observed_at_ms']+60000),now_ms=S['observed_at_ms']+60000)=='DEDUPED'
    assert len(events)==1
 def test_corrupted_state_is_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'bad.json';path.write_text('{broken')
   sent=[]
   with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'1',
     'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'1'}):
    obj=SignalDispatcher(sender=lambda msg:sent.append(msg) or True,
      bot_allocations={'SHORT1':['ELSAUSDT']},persistent_state_path=path)
    assert obj.dispatch(S,now_ms=S['observed_at_ms'])=='PERSISTENCE_UNAVAILABLE'
    assert not sent
 def test_failed_delivery_never_marked_confirmed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'state.json'
   with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'1',
     'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'1'}):
    obj=SignalDispatcher(sender=lambda msg:False,bot_allocations={'SHORT1':['ELSAUSDT']},persistent_state_path=p)
    assert obj.dispatch(S,now_ms=S['observed_at_ms'])=='SEND_NOT_CONFIRMED'
    assert not p.exists()
if __name__=='__main__':unittest.main()
