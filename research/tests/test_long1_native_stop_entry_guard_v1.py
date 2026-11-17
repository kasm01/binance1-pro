"""Mock direct entry enforcement: no network or order."""
import os
from unittest.mock import patch
from core.trade_executor import TradeExecutor
from core.long1_native_stop_fail_safe import KEY
class Redis:
    def __init__(self):self.items={}
    def get(self,k):return self.items.get(k)
    def set(self,k,v):self.items[k]=v
obj=TradeExecutor.__new__(TradeExecutor)
obj.dry_run=False
obj.redis=Redis()
with patch.dict(os.environ,{"LONG1_NATIVE_STOP_AUTO_ENABLE":"1"}):
    obj.redis.set(KEY,"1")
    out=TradeExecutor.open_position_from_signal(obj,"NEARUSDT","long","1m",{})
    assert out["reason"]=="long1_native_stop_safety_latch",out
    obj.redis.items.clear()
    obj._long1_native_stop_latched=True
    out=TradeExecutor.open_position_from_signal(obj,"NEARUSDT","long","1m",{})
    assert out["reason"]=="long1_native_stop_safety_latch",out
    obj._long1_native_stop_latched=False
with patch.dict(os.environ,{"LONG1_NATIVE_STOP_AUTO_ENABLE":"0"}):
    out=TradeExecutor.open_position_from_signal(obj,"NEARUSDT","long","1m",{})
    assert out["reason"]=="long1_native_stop_safety_latch",out
print("PASS direct entry denied when Redis latch/local latch/guard disabled")
