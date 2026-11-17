"""Two-engine domain binding and fail-closed central policy, mock fixtures."""
from dataclasses import replace,dataclass
import json
from research.staging.stage21_joint_risk_authority_v1 import evaluate_joint_candidate
@dataclass(frozen=True)
class Decision:
 state:str="READY"
 production_ready:bool=True
 strategy_id:str="LONG1"
 symbol:str="NEARUSDT"
 side:str="long"
 allowed_notional:float=15.0
d=Decision()
ts=1794948000000
ids={"LONG1":"simulated_account_A","SHORT1":"simulated_account_A"}
proof={"verified":True,"account_id":"simulated_account_A"}
snap={"account_id":"simulated_account_A","complete":True,
 "positions_and_orders_verified":True,"source_authenticated":True,
 "epoch":4,"timestamp_ms":ts,"unknown_intents":False,"available_margin":"60"}
base=dict(two_accounts=ids,shared_identity=proof,portfolio_snapshot=snap,
 central_decision=d,expected_epoch=4,strategy_id="LONG1",
 symbol="NEARUSDT",side="long",now_ms=ts+200)
def case(name,updates,allow=False):
 kw=dict(base);kw.update(updates)
 r=evaluate_joint_candidate(**kw)
 assert (r.state=="READY_CANDIDATE_ONLY")==allow,(name,r)
 assert not r.live_order_authorized
 return r.reason
cases={
 "mock_proof_pass_candidate":({},True),
 "actual_account_identity_unknown":({"shared_identity":None},False),
 "different_account_keys_unverified":({"shared_identity":{"verified":False,"account_id":"simulated_account_A"}},False),
 "different_accounts":({"two_accounts":dict(ids,SHORT1="simulated_account_B")},False),
 "wrong_snapshot_account":{"portfolio_snapshot":dict(snap,account_id="other")},
 "missing_snapshot":{"portfolio_snapshot":None},
 "stale":{"now_ms":ts+10000},
 "missing_positions":{"portfolio_snapshot":dict(snap,positions_and_orders_verified=False)},
 "source_unauthenticated":{"portfolio_snapshot":dict(snap,source_authenticated=False)},
 "epoch_mismatch":{"expected_epoch":5},
 "unknown_intents":{"portfolio_snapshot":dict(snap,unknown_intents=True)},
 "central_missing":{"central_decision":None},
 "central_dry":{"central_decision":replace(d,production_ready=False)},
 "central_reject":{"central_decision":replace(d,state="REJECT")},
 "central_other_bot":{"central_decision":replace(d,strategy_id="SHORT1")},
 "central_bad_notional":{"central_decision":replace(d,allowed_notional=0)},
 "insufficient_margin":{"portfolio_snapshot":dict(snap,available_margin="4")},
}
results={key:case(key,vals if isinstance(vals,dict) else vals[0],
 allow=(vals[1] if isinstance(vals,tuple) else False)) for key,vals in cases.items()}
print(json.dumps({"cases":len(results),"rejected":sum(k!="mock_proof_pass_candidate" for k in results),
 "mock_positive_only":"READY_CANDIDATE_ONLY",
 "account_domain_verified_in_live":False,"orders":0,"redis_writes":0},sort_keys=True))
