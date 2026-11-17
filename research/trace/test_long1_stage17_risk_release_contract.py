"""Positive and fail-closed negative cases without live market side effects."""
import json
from dataclasses import dataclass,replace
from research.staging.long1_stage17_risk_release_contract_v1 import authorize_long_open
@dataclass(frozen=True)
class D:
 state:str="READY"
 production_ready:bool=True
 allowed_notional:float=12.0
 strategy_id:str="LONG1"
 symbol:str="NEARUSDT"
 side:str="long"
base=D()
snap={"complete":True,"fresh":True,"epoch":"sandbox-epoch",
      "positions":[{"strategy_id":"SHORT1","symbol":"INJUSDT","side":"short","notional":11}]}
default=dict(local_gate=True,central_decision=base,authoritative_snapshot=snap,
             expected_symbol="NEARUSDT",expected_epoch="sandbox-epoch")
def test(name,changes,expected):
 k=dict(default);k.update(changes)
 out=authorize_long_open(**k)
 assert out.allow is expected,(name,out)
 return out.reason
cases={
 "positive_candidate":({},True),
 "no_local_permit":({"local_gate":False},False),
 "no_snapshot":({"authoritative_snapshot":None},False),
 "snapshot_incomplete":({"authoritative_snapshot":dict(snap,complete=False)},False),
 "snapshot_stale":({"authoritative_snapshot":dict(snap,fresh=False)},False),
 "snapshot_missing_epoch":({"authoritative_snapshot":dict(snap,epoch=None)},False),
 "epoch_conflict":({"expected_epoch":"different"},False),
 "missing_positions":({"authoritative_snapshot":dict(snap,positions=None)},False),
 "incomplete_position":({"authoritative_snapshot":dict(snap,positions=[{"side":"long"}])},False),
 "no_central_decision":({"central_decision":None},False),
 "dry_profile_ready_without_authority":({"central_decision":replace(base,production_ready=False)},False),
 "central_reject":({"central_decision":replace(base,state="REJECT")},False),
 "zero_allowed_notional":({"central_decision":replace(base,allowed_notional=0)},False),
 "wrong_strategy":({"central_decision":replace(base,strategy_id="LONG2")},False),
 "wrong_symbol":({"central_decision":replace(base,symbol="INJUSDT")},False),
 "wrong_side":({"central_decision":replace(base,side="short")},False),
}
outputs={name:test(name,changes,result) for name,(changes,result) in cases.items()}
print(json.dumps({"scenarios":len(outputs),"fail_closed_scenarios":sum(1 for name,(change,allow) in cases.items() if not allow),
 "positive_only_is_candidate":True,"orders_placed":0,"redis_writes":0,
 "producer_source_modified":False,"results":outputs},sort_keys=True))
