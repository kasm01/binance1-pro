"""Pure snapshot fixtures and strict unknown tests; no network."""
from dataclasses import asdict
import json
from research.staging.stage18_shared_portfolio_snapshot_v1 import inspect_snapshot
T=1794948000000
base=dict(
 positions_by_symbol={
  "NEARUSDT":[{"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":"0"},{"symbol":"NEARUSDT","positionSide":"SHORT","positionAmt":"0"}],
  "INJUSDT":[{"symbol":"INJUSDT","positionSide":"LONG","positionAmt":"0"},{"symbol":"INJUSDT","positionSide":"SHORT","positionAmt":"0"}]},
 orders_by_symbol={"NEARUSDT":[],"INJUSDT":[]},
 algo_by_symbol={"NEARUSDT":[],"INJUSDT":[]},
 account={"totalMarginBalance":"63","availableBalance":"61"},
 fetched_at_ms=T,observed_at_ms=T+700,source_complete=True)
def run(update=None):
 data=dict(base)
 if update:data.update(update)
 return inspect_snapshot(**data)
valid=run()
assert valid.state=="CONSISTENT_INPUTS_NOT_AUTHORIZED" and not valid.can_authorize_live
assert valid.positions==() and valid.open_algo_orders==0
fail={
 "not_complete":{"source_complete":False},
 "stale":{"observed_at_ms":T+50001},
 "future_clock":{"fetched_at_ms":T+4000},
 "no_margin":{"account":None},
 "nan_equity":{"account":{"totalMarginBalance":"NaN","availableBalance":"63"}},
 "missing_symbol":{"positions_by_symbol":{"NEARUSDT":[]}},
 "missing_order_leg":{"orders_by_symbol":{"NEARUSDT":[]}},
 "missing_algo_leg":{"algo_by_symbol":{"INJUSDT":[]}},
 "unavailable_positions":{"positions_by_symbol":{"NEARUSDT":None,"INJUSDT":[]}},
 "invalid_pos_qty":{"positions_by_symbol":{"NEARUSDT":[{"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":"NaN"}],"INJUSDT":[]}},
 "wrong_position_symbol":{"positions_by_symbol":{"NEARUSDT":[{"symbol":"INJUSDT","positionSide":"LONG","positionAmt":"0"}],"INJUSDT":[]}},
 "duplicate_leg":{"positions_by_symbol":{"NEARUSDT":[{"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":"0"},{"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":"0"}],"INJUSDT":[]}},
 "bad_sign":{"positions_by_symbol":{"NEARUSDT":[{"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":"-1"}],"INJUSDT":[]}},
 "open_orders_bad":{"orders_by_symbol":{"NEARUSDT":[{"symbol":"NEARUSDT"}],"INJUSDT":[]}},
 "open_algo_bad":{"algo_by_symbol":{"NEARUSDT":[{"symbol":"INJUSDT","algoId":1}],"INJUSDT":[]}},
}
for label,data in fail.items():
 result=run(data)
 assert result.state=="UNKNOWN" and not result.can_authorize_live,(label,result)
with_open=run({"positions_by_symbol":{"NEARUSDT":[{"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":"10"}],"INJUSDT":[{"symbol":"INJUSDT","positionSide":"SHORT","positionAmt":"-4"}]}})
assert with_open.state=="CONSISTENT_INPUTS_NOT_AUTHORIZED"
assert len(with_open.positions)==2 and with_open.can_authorize_live is False
with_orders=run({"orders_by_symbol":{"NEARUSDT":[{"symbol":"NEARUSDT","orderId":1}],"INJUSDT":[]}})
assert with_orders.open_standard_orders==1 and with_orders.can_authorize_live is False
print(json.dumps({"normal_flat_snapshots":1,"open_positions_recognized":2,
 "open_orders_recognized":1,"negative_unknown_cases":len(fail),
 "live_authorization_from_snapshot":False,"external_requests":0,"redis_writes":0},sort_keys=True))
