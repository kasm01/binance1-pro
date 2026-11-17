"""In-memory isolated A/B tests of prospective 3-file patch. No I/O writes."""
import ast
import copy
import importlib.util
import io
import json
import runpy
import sys
import time
import uuid
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import redis
from orchestration.aggregator import aggregator as aggmodule
from orchestration.aggregator.aggregator import Aggregator
from orchestration.schemas.events import SignalEvent

target = "orchestration.schemas.identity_provenance"
assert target not in sys.modules
assert not Path("orchestration/schemas/identity_provenance.py").exists()
spec=importlib.util.spec_from_file_location(target,"research/staging/long1_identity_runtime_v1.py")
identity=importlib.util.module_from_spec(spec)
sys.modules[target]=identity
spec.loader.exec_module(identity)

with redirect_stdout(io.StringIO()):
    ns=runpy.run_path("research/trace/build_long1_stage13_shared_runtime_patch.py")
base_main=ns["main"]; preview_main=ns["m"]
base_agg=ns["agg"]; preview_agg=ns["a"]

def method(text,name,namespace):
    tree=ast.parse(text)
    found=[copy.deepcopy(n) for cls in tree.body if isinstance(cls,ast.ClassDef)
           for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name]
    assert len(found)==1,(name,len(found))
    node=found[0];node.returns=None;node.decorator_list=[]
    for arg in node.args.args+node.args.kwonlyargs:arg.annotation=None
    mod=ast.Module(body=[node],type_ignores=[])
    ast.fix_missing_locations(mod)
    local=dict(namespace)
    exec(compile(mod,"<prospective-stage13>","exec"),local)
    return local[name]

source_ns={"uuid":uuid,"datetime":datetime,"timezone":timezone,
           "Optional":__import__("typing").Optional,"Dict":dict,"Any":object}
baseline_build=method(base_main,"_build_model_signal_event_payload",source_ns)
preview_build=method(preview_main,"_build_model_signal_event_payload",source_ns)
baseline_candidate=method(base_agg,"_build_candidate_payload",aggmodule.__dict__)
preview_candidate=method(preview_agg,"_build_candidate_payload",aggmodule.__dict__)

now=int(time.time()*1000)
op=(now//180000-2)*180000
cl=op+179999
frame=pd.DataFrame([{"open_time":op,"close_time":cl,"price":3.91}])
model_id=identity.identity_from_closed_frame(frame,symbol="NEARUSDT",
                                              interval="3m",observed_at_ms=now)
assert model_id.model_candle_key==f"NEARUSDT:3m:{op}:{cl}"
oldparams=dict(symbol="NEARUSDT",interval="3m",side="long",p_used=.521,
               p_single=.510,price=3.91,atr_value=.03,whale_dir="short",
               whale_score=.419,signal_source="HYBRID",shadow=False)
old=baseline_build(None,**oldparams)
new=preview_build(None,**oldparams,model_candle_identity=model_id)
exclude={"event_id","ts_utc"}
core={"model_candle_key","model_open_time_ms","model_close_time_ms"}
assert {k:v for k,v in old.items() if k not in exclude}=={k:v for k,v in new.items() if k not in exclude|core}
assert {k:new[k] for k in core}=={
"model_candle_key":model_id.model_candle_key,
"model_open_time_ms":op,"model_close_time_ms":cl}
assert preview_build(None,**oldparams).keys()==old.keys()

agg=Aggregator.__new__(Aggregator)
agg.include_raw=False
r=redis.Redis(decode_responses=True,socket_timeout=5)
rows=r.xrevrange("signals_stream_long1",count=120)
assert len(rows)>=30
cases=0
for sid,fields in rows:
    item=json.loads(fields["json"])
    if item.get("symbol")!="NEARUSDT" or item.get("side_candidate")!="long":
        continue
    parsed=agg._normalize_event(sid,SignalEvent.normalize(item))
    parsed["_score_total"]=float(item.get("model_score",0))
    parsed["_reason_codes"]=[];parsed["_risk_tags"]=[]
    a=baseline_candidate(agg,copy.deepcopy(parsed))
    b=preview_candidate(agg,copy.deepcopy(parsed))
    assert {k:v for k,v in b.items() if k not in ("candidate_id","lineage")}=={
        k:v for k,v in a.items() if k!="candidate_id"
    }
    assert b["lineage"]=={
        "lineage_state":"EXACT_SIGNAL_EVENT_ID_AND_STREAM_ID",
        "source_signal_event_id":item["event_id"],
        "source_signal_stream_id":sid,
    }
    valid=copy.deepcopy(parsed)
    valid.update(model_candle_key=model_id.model_candle_key,
                 model_open_time_ms=op,model_close_time_ms=cl)
    vc=preview_candidate(agg,valid)
    assert vc["lineage"]["model_candle_key"]==model_id.model_candle_key
    for corruption in (
        {"model_candle_key":model_id.model_candle_key+"X"},
        {"model_close_time_ms":cl+180000},
        {"model_open_time_ms":float(op)},
        {"model_close_time_ms":None},
    ):
        ev=dict(valid,**corruption)
        bad=preview_candidate(agg,ev)
        assert "model_candle_key" not in bad["lineage"]
        assert bad["lineage"]["source_signal_event_id"]==item["event_id"]
    ev=copy.deepcopy(valid)
    ev.pop("event_id",None)
    assert "lineage" not in preview_candidate(agg,ev)
    # Old signal from another bot must not receive LONG1 metadata.
    ev=dict(valid, symbol="INJUSDT")
    assert "lineage" not in preview_candidate(agg,ev)
    cases+=1
assert cases>=30
# Reject uncertain/unclosed/wallclock-derived provenance
for kw in (
    {"close_time_ms":cl+180000},
    {"open_time_ms":op+1000},
    {"open_time_ms":float(op)},
    {"observed_at_ms":cl},
    {"interval":"5m"},
):
    args=dict(symbol="NEARUSDT",interval="3m",
              open_time_ms=op,close_time_ms=cl,observed_at_ms=now)
    args.update(kw)
    try:identity.validate_candle_identity(**args)
    except ValueError: pass
    else:raise AssertionError(f"accepted invalid source: {kw}")
print(json.dumps({
    "patch_three_files_compiled":True,
    "candidate_ab_real_samples":cases,
    "old_core_payload_unchanged":cases,
    "source_event_parent_exact":cases,
    "valid_source_candle_accepted":cases,
    "invalid_optional_candle_stripped":cases*4,
    "missing_signal_id_no_lineage":cases,
    "cross_bot_signal_no_lineage":cases,
    "production_files_edited":False
},sort_keys=True))
