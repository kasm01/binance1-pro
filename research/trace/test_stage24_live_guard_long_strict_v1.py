"""AST-extracted ACTUAL LONG TradeExecutor functions. NO real Binance calls."""
import ast,copy,json,os
from pathlib import Path
from unittest.mock import patch
from core.strict_position_count_v1 import count_side
from core.joint_risk_live_guard_v1 import check_new_open
from core import strict_position_count_v1

assert check_new_open(strategy_id="LONG1",symbol="NEARUSDT",side="long",dry_run=False).allow is False
assert check_new_open(strategy_id="SHORT1",symbol="INJUSDT",side="short",dry_run=False).allow is False
assert check_new_open(strategy_id="SHORT1",symbol="NEARUSDT",side="short",dry_run=True).allow is False
assert check_new_open(strategy_id="LONG1",symbol="NEARUSDT",side="long",dry_run=True).allow is True
assert count_side([],"long")==0
assert count_side([{"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":"2"}],"long")==1
assert count_side([{"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":"2"}],"short")==0
for raw in (None,{},[{}],[{"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":"nan"}],
            [{"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":"-1"}],
            [{"symbol":"NEARUSDT","positionSide":"BOTH","positionAmt":"inf"}]):
 try:count_side(raw,"long")
 except ValueError:pass
 else:raise AssertionError("untrusted exchange data became zero")
src=ast.parse(Path("core/trade_executor.py").read_text())
methods={"_count_open_positions_for_side","_evaluate_long_execution_risk_gate",
         "open_position_from_signal","_exchange_open_market"}
cls=next(c for c in ast.walk(src) if isinstance(c,ast.ClassDef) and
         any(getattr(m,"name",None)=="_evaluate_long_execution_risk_gate" for m in c.body))
methods_nodes=[copy.deepcopy(n) for n in cls.body if getattr(n,"name",None) in methods]
assert {n.name for n in methods_nodes}==methods
for n in methods_nodes:
 n.decorator_list=[];n.returns=None
 for a in n.args.args+n.args.kwonlyargs:a.annotation=None
temp=ast.Module(body=[ast.ClassDef(name="FakeLive",bases=[],keywords=[],body=methods_nodes,decorator_list=[])],type_ignores=[])
ast.fix_missing_locations(temp)
class FailBroker:
 def __init__(self):self.calls=0
 def __call__(self):
  self.calls+=1
  raise OSError("broker offline")
broker=FailBroker()
ns={"os":os,"Optional":__import__("typing").Optional,"_futures_v3_position_risk":broker}
exec(compile(temp,"<actual-long-stage24>","exec"),ns)
Live=ns["FakeLive"]

class EvilClient:
 def __init__(self):self.order_calls=0
 def futures_create_order(self,**kwargs):
  self.order_calls+=1
  raise AssertionError("THIS MUST NEVER BE CALLED")

def live():
 x=Live();x.dry_run=False;x.logger=None;x.client=EvilClient();x.redis=None
 x.max_open_positions=1
 x._get_effective_position=lambda sym:None
 x._count_open_positions=lambda :0
 return x
x=live()
try:x._count_open_positions_for_side("long")
except OSError:pass
else:raise AssertionError("unavailable counted as 0")
assert broker.calls==1
assert x._evaluate_long_execution_risk_gate(symbol="NEARUSDT",
 side="long",price=4,interval="3m") is False
assert broker.calls==2
# Test only: make the earlier independent Native Stop gate pass, so that
# the NEW joint authority gate is exercised (no actual latch is changed).
with patch("core.long1_native_stop_fail_safe.entry_allowed",return_value=True):
 entry=x.open_position_from_signal("NEARUSDT","long","1m",{})
assert entry["status"]=="skip" and entry["reason"]=="joint_risk_live_authority_not_connected"
assert broker.calls==2
try:x._exchange_open_market("NEARUSDT","long",1,4)
except RuntimeError as exc: assert "joint_risk_live_authority_not_connected" in str(exc)
else:raise AssertionError("live order emitter allowed")
assert x.client.order_calls==0
# Isolate protected same-side scale-in failure, BEFORE the scale-in allow branch.
with patch.dict(os.environ,{"LONG_SCALE_IN_ENABLE":"1","LONG_MAX_ENTRY_LAYERS":"3"}):
 x._get_effective_position=lambda _:{"side":"long","entry_layers":1}
 assert x._evaluate_long_execution_risk_gate(symbol="NEARUSDT",
   side="long",price=4,interval="3m",extra={"signal_score":1.0}) is False
assert x.client.order_calls==0
# Real no-position result from signed GET is a valid count ONLY; it does not
# authorize a live entry through the shared central gate.
ns["_futures_v3_position_risk"]=lambda:[]
y=live()
assert y._count_open_positions_for_side("long")==0
assert y._evaluate_long_execution_risk_gate(symbol="NEARUSDT",
 side="long",price=4,interval="3m") is True
with patch("core.long1_native_stop_fail_safe.entry_allowed",return_value=True):
 assert y.open_position_from_signal("NEARUSDT","long","1m",{})["status"]=="skip"
assert y.client.order_calls==0
print(json.dumps({"strict_malformed_source_cases":6,
 "live_broker_exception_propagates":True,
 "risk_unreadable_blocks":True,
 "scale_in_with_unreadable_broker_blocks":True,
 "broker_flat_count_only_not_live_authority":True,
 "executor_entry_and_exchange_emitter_block":True,
 "real_binance_orders":0,"live_redis_writes":0},sort_keys=True))
