"""Injected callable-only read; assert full two-symbol ordering and fail closed."""
import json
from research.staging.stage18_broker_snapshot_reader_v1 import capture
now=1794948000000
def make(broken=None):
 calls=[]
 ticks=iter([now,now+750])
 def account():
  calls.append("account")
  if broken=="account":raise OSError("offline")
  return {"totalMarginBalance":"63","availableBalance":"63"}
 def positions(sym):
  calls.append("positions:"+sym)
  if broken=="positions:"+sym:raise TimeoutError("offline")
  return [{"symbol":sym,"positionSide":"LONG","positionAmt":"0"},
          {"symbol":sym,"positionSide":"SHORT","positionAmt":"0"}]
 def orders(sym):
  calls.append("orders:"+sym)
  if broken=="orders:"+sym:return None
  return []
 def algos(sym):
  calls.append("algos:"+sym)
  if broken=="algos:"+sym:raise OSError("offline")
  return []
 result=capture(read_account=account,read_positions=positions,
                read_open_orders=orders,read_open_algos=algos,
                clock_ms=lambda:next(ticks))
 return result,calls
ok,calls=make()
assert ok.state=="CONSISTENT_INPUTS_NOT_AUTHORIZED" and ok.can_authorize_live is False
assert len(calls)==7 and calls[0]=="account"
fail=[]
for item in ("account","positions:NEARUSDT","positions:INJUSDT",
             "orders:NEARUSDT","orders:INJUSDT","algos:NEARUSDT","algos:INJUSDT"):
 res,_=make(item)
 assert res.state=="UNKNOWN" and not res.can_authorize_live,(item,res)
 fail.append(item)
ticks=iter([now,now+8000])
res=capture(read_account=lambda:{"totalMarginBalance":"63","availableBalance":"63"},
  read_positions=lambda s:[],read_open_orders=lambda s:[],
  read_open_algos=lambda s:[],clock_ms=lambda:next(ticks))
assert res.state=="UNKNOWN" and res.reason=="capture_duration_exceeded"
print(json.dumps({"full_two_symbol_read_calls":len(calls),
 "missing_or_failed_broker_reads_rejected":len(fail),
 "capture_timeout_rejected":True,
 "snapshot_grants_order_authority":False,
 "external_calls":0,"redis_writes":0},sort_keys=True))
