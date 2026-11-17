"""Isolated exact source method & actual Redis signal samples; read-only. No order path."""
import ast
import copy
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
import redis
from orchestration.schemas.events import SignalEvent
from orchestration.aggregator.aggregator import Aggregator
from orchestration.aggregator.scoring import compute_score, pass_quality_gates
from research.trace.long1_candidate_lineage_shadow_v1 import candidate_shadow
from research.trace.long1_model_candle_identity_v1 import from_closed_candle

# Extract the actual production payload builder, not a rewritten approximation.
tree = ast.parse(Path("main.py").read_text())
methods = [node for cls in tree.body if isinstance(cls, ast.ClassDef)
           for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
           and node.name == "_build_model_signal_event_payload"]
assert len(methods) == 1
method = copy.deepcopy(methods[0]);method.decorator_list = []
method.returns = None
for arg in method.args.args + method.args.kwonlyargs:
    arg.annotation = None
module = ast.Module(body=[method], type_ignores=[])
ast.fix_missing_locations(module)
scope = {"uuid":uuid, "datetime":datetime,"timezone":timezone,
         "Optional":__import__("typing").Optional,"Dict":dict,"Any":object}
exec(compile(module,"main.py::<payload_builder>", "exec"),scope)
build = scope["_build_model_signal_event_payload"]
kwargs=dict(symbol="NEARUSDT",interval="3m",side="long",p_used=.535,
            p_single=.53,price=3.98,atr_value=.02,whale_dir="short",
            whale_score=.42,signal_source="HYBRID",shadow=False)
with_id=build(None,**kwargs)
assert isinstance(with_id,dict) and with_id["model_score"]==.535
base=copy.deepcopy(with_id)
op=1794845520000;op -= op%180000; cl=op+180000-1
candle=from_closed_candle(symbol="NEARUSDT",interval="3m",
                          open_time_ms=op,close_time_ms=cl,observed_at_ms=cl+1)
extra=copy.deepcopy(base)
extra["model_candle_key"]=candle.model_candle_key
extra["model_open_time_ms"]=candle.model_open_time_ms
extra["model_close_time_ms"]=candle.model_close_time_ms
assert {k:v for k,v in extra.items() if k not in
        ("model_candle_key","model_open_time_ms","model_close_time_ms")}==base

agg=Aggregator.__new__(Aggregator)
agg.include_raw=False
agg.min_score=0.0
r=redis.Redis(decode_responses=True,socket_timeout=6)
rows=r.xrevrange("signals_stream_long1",count=120)
assert rows, "no retained live signals"
tested=0;unchanged=0;linked=0;missing=0;drop_deltas=0
for mid,fields in rows:
    item=json.loads(fields["json"])
    if not isinstance(item,dict) or item.get("symbol")!="NEARUSDT":
        continue
    old=agg._normalize_event(mid,SignalEvent.normalize(item))
    newitem=copy.deepcopy(item)
    newitem["model_candle_key"]=candle.model_candle_key
    newitem["model_open_time_ms"]=candle.model_open_time_ms
    newitem["model_close_time_ms"]=candle.model_close_time_ms
    new=agg._normalize_event(mid,SignalEvent.normalize(newitem))
    oldgate=pass_quality_gates(old)
    newgate=pass_quality_gates(new)
    oldscore=compute_score(old)
    newscore=compute_score(new)
    assert oldgate==newgate and oldscore==newscore
    drop_deltas+=int(oldgate!=newgate or oldscore!=newscore)
    for evt, result in [(old, oldscore),(new,newscore)]:
        evt["_score_total"]=result[0]
        evt["_reason_codes"]=result[1]
        evt["_risk_tags"]=result[2]
    oldpayload=agg._build_candidate_payload(old)
    newpayload=agg._build_candidate_payload(new)
    for key in ["candidate_id","ts_utc"]:
        oldpayload.pop(key,None)
        newpayload.pop(key,None)
    assert oldpayload==newpayload, "non-identity candidate payload changed"
    proven=candidate_shadow(newpayload,new)
    assert proven["lineage"]["source_signal_event_id"]==item["event_id"]
    assert proven["lineage"]["source_signal_stream_id"]==mid
    assert {k:v for k,v in proven.items() if k!="lineage"}==oldpayload
    assert "model_close_id" not in proven["lineage"]
    tested+=1;unchanged+=1;linked+=1
assert tested>=30, ("insufficient fixtures",tested)
print(json.dumps(dict(exact_production_builder=True,real_redis_fixture_count=tested,
                      quality_and_score_equal=unchanged,candidate_core_equal=unchanged,
                      source_parent_proven=linked,model_close_not_invented=linked,
                      observed_decision_deltas=drop_deltas,
                      note="NOT a full live replay; no dedup/intent/order executed"),sort_keys=True))
