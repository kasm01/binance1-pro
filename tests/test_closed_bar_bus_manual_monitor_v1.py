import json,os,tempfile,unittest
from pathlib import Path
from scanner.closed_bar_bus_v1 import ClosedBarBus
from scanner.manual_watch_runner_v1 import make_status,atomic_status,watch_rows
from tests.test_shared40_snapshot_pilot_v1 import START,ASOF,source
MS=60000
def ws(symbol,t,prev,new,*,x=True,q=12000000):
 return {'e':'kline','E':t+MS+200,'s':symbol,
  'k':{'s':symbol,'i':'1m','x':x,'t':t,'T':t+MS-1,
   'o':str(prev),'h':str(max(prev,new)*1.0001),
   'l':str(min(prev,new)*.9999),'c':str(new),'q':str(q)}}
class BusTest(unittest.TestCase):
 def test_bootstrap_once_and_same_direction_partition(self):
  bus=ClosedBarBus(['RISEUSDT','FALLUSDT'])
  assert bus.bootstrap('RISEUSDT',source(1),asof_ms=ASOF)
  assert bus.bootstrap('FALLUSDT',source(-1),asof_ms=ASOF)
  assert bus.stats()['bars_cached']==142
  alloc={'LONG1':['RISEUSDT','FALLUSDT'],'SHORT1':['RISEUSDT','FALLUSDT']}
  rows=watch_rows(bus,alloc,ASOF)
  assert any(x['direction']=='LONG' for x in rows)
  assert any(x['direction']=='SHORT' for x in rows)
  assert bus.stats()['source_readers_per_symbol']==1
  status=make_status(bus,alloc,ASOF,{'excluded_top_volume_15':['BTCUSDT']})
  assert not status['order_authorized'] and not status['telegram_sent']
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/'status.json'
   atomic_status(status,p)
   assert json.loads(p.read_text())==status
   assert p.stat().st_mode & 0o077==0
 def test_ws_partial_dup_gap_and_rebootstrap(self):
  bus=ClosedBarBus(['RISEUSDT'])
  assert bus.bootstrap('RISEUSDT',source(),asof_ms=ASOF)
  prev=bus.data['RISEUSDT'][-1]['c']
  t=START+71*MS
  message=ws('RISEUSDT',t,prev,prev*1.002)
  assert bus.update_ws('RISEUSDT',dict(message,k=dict(message['k'],x=False)),
   observed_at_ms=t+MS+200)=='PARTIAL_IGNORED'
  assert bus.update_ws('RISEUSDT',message,observed_at_ms=t+MS+200)=='CLOSED_ACCEPTED'
  assert bus.update_ws('RISEUSDT',message,observed_at_ms=t+MS+300)=='DUPLICATE_IGNORED'
  assert bus.update_ws('RISEUSDT',ws('RISEUSDT',t+2*MS,prev,prev*1.003),
   observed_at_ms=t+3*MS+200)=='GAP_BLOCKED'
  assert bus.analyze('RISEUSDT',asof_ms=t+3*MS+200)['status']=='INSUFFICIENT_DATA'
  assert bus.stats()['valid_symbols']==0
  assert bus.update_ws('RISEUSDT',ws('RISEUSDT',t+3*MS,prev,prev*1.004),
   observed_at_ms=t+4*MS+200)=='NEEDS_BOOTSTRAP'
 def test_no_partial_future_invalid(self):
  bus=ClosedBarBus(['RISEUSDT'])
  assert bus.bootstrap('RISEUSDT',source(),asof_ms=ASOF)
  last=bus.data['RISEUSDT'][-1]['c']
  t=START+71*MS
  assert bus.update_ws('FALLUSDT',ws('FALLUSDT',t,last,last),observed_at_ms=t+MS+200)=='OUTSIDE_UNIVERSE'
  assert bus.update_ws('RISEUSDT',ws('RISEUSDT',t,last,last),
     observed_at_ms=t+MS-1)=='FUTURE_OR_STALE_CLOSE'
  fake=ws('RISEUSDT',t,last,last);fake['k']['T']+=1
  assert bus.update_ws('RISEUSDT',fake,observed_at_ms=t+MS+200)=='BAD_CANDLE'
if __name__=='__main__':unittest.main()
