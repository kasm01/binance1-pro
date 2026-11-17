"""Actual production methods + CentralRiskMaster, in-memory failure injection.

No Redis, network, state writes, or order authority.
"""
from __future__ import annotations
import ast,copy,json,os
from pathlib import Path
from orchestration.risk.central_risk_master import (
 CentralRiskMaster,CentralRiskConfig,PositionExposure,
 PortfolioRiskState,EntryRiskRequest)
from orchestration.risk.central_risk_enforce_dry_profile import build_enforce_dry_master

src=Path("core/trade_executor.py").read_text()
tree=ast.parse(src)
selected={"_count_open_positions_for_side","_evaluate_long_execution_risk_gate",
          "_get_effective_position"}
classes=[node for node in ast.walk(tree) if isinstance(node,ast.ClassDef)
         and any(getattr(ch,"name",None)=="_evaluate_long_execution_risk_gate" for ch in node.body)]
assert len(classes)==1
nodes=[copy.deepcopy(node) for node in classes[0].body if getattr(node,"name",None) in selected]
assert {n.name for n in nodes}==selected
for n in nodes:
 n.decorator_list=[];n.returns=None
 for arg in n.args.args+n.args.kwonlyargs:arg.annotation=None
mod=ast.Module(body=[ast.ClassDef(name="SafeTestClass",bases=[],keywords=[],body=nodes,decorator_list=[])],type_ignores=[])
ast.fix_missing_locations(mod)
ctx={"os":os,"Optional":__import__("typing").Optional}
exec(compile(mod,"<stage17-live-executor-extract>","exec"),ctx)
E=ctx["SafeTestClass"]

class BrokenPositions:
 def values(self):raise OSError("position store unavailable")

# Current production: LIVE count uses strict signed GET. Simulate read failure.
def unavailable_broker():
 raise OSError("signed Binance GET failed")
ctx["_futures_v3_position_risk"]=unavailable_broker
e=E()
e.dry_run=False
e.positions=BrokenPositions()
e._count_open_positions=lambda:0
e._get_effective_position=lambda _:None
e.max_open_positions=1
e.logger=None
try:
 e._count_open_positions_for_side("long")
except OSError:
 pass
else:
 raise AssertionError("unknown broker state must not return zero")
allow=e._evaluate_long_execution_risk_gate(symbol="NEARUSDT",side="long",price=4,interval="3m",extra={})
assert allow is False

# Position lookup still yields None when GET is unavailable; the strict
# independent count above blocks a LIVE open before that ambiguity matters.
p=E()
p._get_position=lambda _:None
p._get_exchange_position=lambda _:None
assert p._get_effective_position("NEARUSDT") is None

master=build_enforce_dry_master()
config=master.config
ok,issues=config.validate_for_production()
assert not ok and "production_not_authorized" in issues
request=EntryRiskRequest(strategy_id="LONG1",symbol="NEARUSDT",side="long",requested_notional=15)
state=PortfolioRiskState(equity_peak=100)
empty=master.evaluate_entry(request=request,state=state,portfolio_equity=100,positions=[])
# Important distinction: READY can coexist with production_ready=False.
assert empty.state=="READY" and empty.production_ready is False
filled=[
 PositionExposure(strategy_id="LONG1",symbol="NEARUSDT",side="long",notional=40),
 PositionExposure(strategy_id="SHORT1",symbol="INJUSDT",side="short",notional=40),
]
blocked=master.evaluate_entry(request=request,state=state,portfolio_equity=100,positions=filled)
assert blocked.state=="REJECT"
assert blocked.production_ready is False
# Separate NEW strategy would also hit the two-position cap.
other_req=EntryRiskRequest(strategy_id="LONG2",symbol="NEARUSDT",side="long",requested_notional=15)
other=master.evaluate_entry(request=other_req,state=state,portfolio_equity=100,positions=filled)
assert other.state=="REJECT" and "max_open_positions" in other.reason_codes

# Design-only strict snapshot adapter should fail closed when source unavailable.
def strict_snapshot_count(reader):
 try:
  positions=reader()
  if positions is None or not isinstance(positions,list):
   raise ValueError("position snapshot unavailable")
  if any(not isinstance(p,dict) or "side" not in p or "qty" not in p for p in positions):
   raise ValueError("incomplete position snapshot")
  return sum(1 for p in positions if str(p["side"]).lower()=="long" and float(p["qty"])>0)
 except Exception:
  return None
assert strict_snapshot_count(lambda:None) is None
assert strict_snapshot_count(lambda:(_ for _ in ()).throw(OSError("offline"))) is None
assert strict_snapshot_count(lambda:[{"side":"long","qty":2}])==1
assert strict_snapshot_count(lambda:[])==0

print(json.dumps({
 "live_executor_ast_methods":len(nodes),
 "unknown_broker_count_raises":True,
 "risk_allowed_with_unknown_positions":allow,
 "central_dry_profile_production_ready":ok,
 "central_empty_snapshot_decision":empty.state,
 "central_empty_snapshot_production_ready":empty.production_ready,
 "central_two_position_decision":blocked.state,
 "central_second_strategy_cap_decision":other.state,
 "candidate_strict_unknown_count_blocks":True,
 "source_contains_direct_central_master_import":(
  "orchestration.risk.central_risk_master" in src),
 "actual_exchange_calls":0,
 "redis_writes":0,
 "production_source_was_recently_patched":True,
},sort_keys=True))
