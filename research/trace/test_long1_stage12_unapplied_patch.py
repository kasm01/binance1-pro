"""Test actual ASTs from generated but UNAPPLIED production patch in memory."""
import ast
import copy
import io
import json
import runpy
import uuid
from contextlib import redirect_stdout
from datetime import datetime,timezone
from pathlib import Path
import redis
from orchestration.aggregator import aggregator as aggmod
from orchestration.aggregator.aggregator import Aggregator
from orchestration.schemas.events import SignalEvent
from research.trace.long1_model_candle_identity_v1 import from_closed_candle

with redirect_stdout(io.StringIO()):
    ns=runpy.run_path("research/trace/build_long1_stage12_candidate_patch.py")
old_main=ns["main"];new_main=ns["m"];old_agg=ns["agg"];new_agg=ns["a"]
assert old_main!=new_main and old_agg!=new_agg

def extract(text,method,base):
    tree=ast.parse(text)
    found=[copy.deepcopy(n) for c in tree.body if isinstance(c,ast.ClassDef)
           for n in c.body if isinstance(n,ast.FunctionDef) and n.name==method]
    assert len(found)==1
    node=found[0];node.decorator_list=[];node.returns=None
    for arg in node.args.args+node.args.kwonlyargs:arg.annotation=None
    mod=ast.Module(body=[node],type_ignores=[]);ast.fix_missing_locations(mod)
    scope=dict(base);exec(compile(mod,"<isolated-stage12-ast>","exec"),scope)
    return scope[method]

env=dict(uuid=uuid,datetime=datetime,timezone=timezone,Optional=__import__("typing").Optional,
         Dict=dict,Any=object)
original_builder=extract(old_main,"_build_model_signal_event_payload",env)
patched_builder=extract(new_main,"_build_model_signal_event_payload",env)
kwargs=dict(symbol="NEARUSDT",interval="3m",side="long",p_used=.52,
            p_single=.51,price=3.91,atr_value=.03,whale_dir="short",
            whale_score=.41,signal_source="HYBRID",shadow=False)
op=1794860820000;op -= op%180000;cl=op+180000-1
identity=from_closed_candle(symbol="NEARUSDT",interval="3m",
                            open_time_ms=op,close_time_ms=cl,observed_at_ms=cl+1)
a=original_builder(None,**kwargs)
b=patched_builder(None,**kwargs)
c=patched_builder(None,**kwargs,model_candle_identity=identity)
skip={"ts_utc","event_id"}
assert {k:v for k,v in a.items() if k not in skip}=={k:v for k,v in b.items() if k not in skip}
meta={"model_candle_key","model_open_time_ms","model_close_time_ms"}
assert {k:v for k,v in c.items() if k not in meta|skip}=={k:v for k,v in a.items() if k not in skip}
assert c["model_candle_key"]==identity.model_candle_key

original_candidate=extract(old_agg,"_build_candidate_payload",aggmod.__dict__)
patched_candidate=extract(new_agg,"_build_candidate_payload",aggmod.__dict__)
agg=Aggregator.__new__(Aggregator);agg.include_raw=False
r=redis.Redis(decode_responses=True,socket_timeout=5)
rows=r.xrevrange("signals_stream_long1",count=120)
assert len(rows)>=30
tested=0
for mid,fields in rows:
    item=json.loads(fields["json"])
    if not isinstance(item,dict) or item.get("symbol")!="NEARUSDT": continue
    e=agg._normalize_event(mid,SignalEvent.normalize(item))
    e["_score_total"]=float(item.get("model_score",0))
    e["_reason_codes"]=[]
    e["_risk_tags"]=[]
    source=original_candidate(agg,copy.deepcopy(e))
    tagged=patched_candidate(agg,copy.deepcopy(e))
    for d in (source,tagged):d.pop("candidate_id",None)
    assert {k:v for k,v in tagged.items() if k!="lineage"}==source
    assert tagged["lineage"]["source_signal_event_id"]==e["event_id"]
    assert tagged["lineage"]["source_signal_stream_id"]==mid
    assert "model_candle_key" not in tagged["lineage"]
    with_key=copy.deepcopy(e)
    with_key.update(model_candle_key=identity.model_candle_key,
                    model_open_time_ms=identity.model_open_time_ms,
                    model_close_time_ms=identity.model_close_time_ms)
    verified=patched_candidate(agg,with_key)
    assert verified["lineage"]["model_candle_key"]==identity.model_candle_key
    corrupted=copy.deepcopy(with_key);corrupted["model_close_time_ms"]+=1000
    bad=patched_candidate(agg,corrupted)
    assert "model_candle_key" not in bad["lineage"]
    source_missing=copy.deepcopy(with_key);source_missing.pop("event_id",None)
    unlinked=patched_candidate(agg,source_missing)
    assert "lineage" not in unlinked
    tested+=1
assert tested>=30
print(json.dumps({"main_payload_builder_metadata_ab":True,
                  "candidate_actual_ast_fixtures":tested,
                  "candidate_core_equal":tested,
                  "candle_triplet_valid_and_invalid_tested":tested,
                  "no_fake_parent_when_missing":tested,
                  "real_production_files_changed":False},sort_keys=True))
