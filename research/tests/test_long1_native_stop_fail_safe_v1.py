"""No exchange writes, explicit mocks for long stop attach-failure handling."""
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from core import long1_native_stop_fail_safe as fs

class Redis:
    def __init__(self):self.data={}
    def get(self,k):return self.data.get(k)
    def set(self,k,v):self.data[k]=v
class Exec:
    logger=None
    def __init__(self):self.redis=Redis();self.calls=0
    def close_position(self,*args,**kw):
        self.calls+=1
        return {"status":"close_requested"}

def r(q):
    return [{"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":str(q)}]
with TemporaryDirectory() as workdir:
    Path(workdir,'state').mkdir()
    with patch.object(fs,'DISK_LATCH',Path(workdir,'state','long1_stop.latch')):
        assert fs.entry_allowed(Redis(),native_enabled=True)
        assert not fs.entry_allowed(None,native_enabled=True)
        assert not fs.entry_allowed(Redis(),native_enabled=False)
        assert not fs.entry_allowed(Redis(),native_enabled=True,local_latched=True)
        x=Exec();x.redis.set(fs.KEY,"1")
        assert not fs.entry_allowed(x.redis,native_enabled=True)
        x=Exec()
        with patch.object(fs,'position_risk',side_effect=[r(7),r(0)]):
         a=fs.emergency(x,price=4.00,interval='1m')
         assert a['state']=='FLAT_CONFIRMED' and x.calls==1
         assert not fs.entry_allowed(x.redis,native_enabled=True)
        x=Exec()
        with patch.object(fs,'position_risk',return_value=r(0)):
         a=fs.emergency(x,price=4.00,interval='1m')
         assert a['state']=='ALREADY_FLAT' and x.calls==0
        x=Exec()
        with patch.object(fs,'position_risk',side_effect=RuntimeError('api down')):
         a=fs.emergency(x,price=4.00,interval='1m')
         assert a['state']=='POSITION_UNKNOWN' and x.calls==0
        x=Exec()
        with patch.object(fs,'position_risk',side_effect=[r(7),r(2)]):
         a=fs.emergency(x,price=4.00,interval='1m')
         assert a['state']=='STILL_OPEN' and x.calls==1
        x=Exec()
        with patch.object(fs,'position_risk',side_effect=[r(7),RuntimeError('post api down')]):
         a=fs.emergency(x,price=4.00,interval='1m')
         assert a['state']=='CLOSE_UNVERIFIED' and x.calls==1
        assert fs.DISK_LATCH.exists()
        assert not fs.entry_allowed(Redis(), native_enabled=True)
        print('PASS 11 scenarios: Redis+durable disk latch, flat, single close, partial, API errors; no external writes')
