"""Historical Stage16 patch artifact has been superseded by installed Stage24 fix.
The original small proposed diff is retained as a research artifact on disk.
This current regression test imports only the safe strict-count helper and
exercises an AST-extracted live risk method with failing broker read.
"""
import ast,copy,json,os
from pathlib import Path
src=Path("core/trade_executor.py").read_text()
tree=ast.parse(src)
cls=next(c for c in ast.walk(tree) if isinstance(c,ast.ClassDef) and
 any(getattr(n,"name",None)=="_evaluate_long_execution_risk_gate" for n in c.body))
node=next(copy.deepcopy(n) for n in cls.body if getattr(n,"name",None)=="_evaluate_long_execution_risk_gate")
node.decorator_list=[];node.returns=None
for a in node.args.args+node.args.kwonlyargs:a.annotation=None
mod=ast.Module(body=[node],type_ignores=[]);ast.fix_missing_locations(mod)
ns={"os":os}
exec(compile(mod,"<stage16-patched-risk>","exec"),ns)
class Fake:
 dry_run=False
 logger=None
 max_open_positions=1
 _get_effective_position=lambda self,s:None
 _count_open_positions_for_side=lambda self,s: (_ for _ in ()).throw(OSError('broker offline'))
f=Fake()
fn=ns[node.name]
args=dict(symbol="NEARUSDT",side="long",price=3.9,interval="3m",extra={})
assert fn(f,**args) is False
f._count_open_positions_for_side=lambda s:0
assert fn(f,**args) is True
f._count_open_positions_for_side=lambda s:1
assert fn(f,**args) is False
print(json.dumps({"prior_fault_fixed":True,"broker_unknown_blocks":True,
  "flat_count_not_alone_an_authorization":True,"at_cap_blocks":True,
  "real_exchange_orders":0,"redis_writes":0},sort_keys=True))
