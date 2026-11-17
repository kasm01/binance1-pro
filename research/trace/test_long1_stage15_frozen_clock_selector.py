"""Frozen clock, actual selector methods; compare metadata A/B WITHOUT Redis writes."""
import contextlib,copy,io,json,os,time
from unittest.mock import patch
import redis
from orchestration.selector import top_selector as mod
from orchestration.selector.top_selector import TopSelector
from research.staging.long1_identity_runtime_v1 import verified_source_lineage

r=redis.Redis(decode_responses=True,socket_timeout=5)
rows=r.xrevrange("candidates_stream_long1",count=120)
assert len(rows)>=40
conf={}
for line in open(".env"):
    if "=" in line and not line.startswith("#"):
        k,v=line.strip().split("=",1)
        if k in ("ACP_ENABLE","ACP_FILTER_BASE_FLOOR","ACP_LOG_TOPK","ACP_LIMITER_LOG_BLOCKS","TOPSEL_TOPK","TOPSEL_WINDOW_SEC","TOPSEL_COOLDOWN_SEC","TOPSEL_MIN_SCORE"):
            conf[k]=v
old={k:os.environ.get(k) for k in conf}
os.environ.update(conf)
os.environ["ACP_LOG_TOPK"]="0"
os.environ["ACP_LIMITER_LOG_BLOCKS"]="0"

selector=TopSelector.__new__(TopSelector)
selector.window_sec=max(1,int(conf.get("TOPSEL_WINDOW_SEC",8)))
selector.topk=int(conf.get("TOPSEL_TOPK",3))
selector.min_score=float(conf.get("TOPSEL_MIN_SCORE",0))
selector.w_min=0.;selector.require_fields=True
selector.penalty_wide_spread=.15;selector.penalty_high_vol=.05

def run(items,now,cooldown,last):
    selector.cooldown_sec=cooldown
    selector.last_sent=copy.deepcopy(last)
    with patch.object(mod.time,"time",return_value=now):
        with contextlib.redirect_stdout(io.StringIO()):
            return selector._select_topk(copy.deepcopy(items))

matched=0;positive=0;cooldown_blocked=0;nonblocked=0
for i,(sid,fields) in enumerate(rows):
    c=json.loads(fields["json"])
    if not isinstance(c,dict) or c.get("symbol")!="NEARUSDT":continue
    stamp=int(sid.split("-")[0])/1000
    # Frozen event-time + 0.25 seconds: real Redis stream ids.
    frozen=stamp+.25
    lineage=verified_source_lineage(
        dict(event_id=f"stage15-synthetic-{i}",_source_stream_id=sid),
        symbol="NEARUSDT",side="long",interval="3m",observed_at_ms=int(frozen*1000)
    )
    assert lineage is not None
    a=[(sid,c)]
    b=[(sid,dict(copy.deepcopy(c),lineage=lineage))]
    # Production config currently zero cooldown, plus 90s counterfactual to
    # exercise the state branch. Never call _publish() (which writes Redis).
    key=c.get("dedup_key") or f"NEARUSDT|3m|long"
    for cooldown,last in (
        (0,{}),(90,{key:frozen-30}), (90,{key:frozen-120})
    ):
        oa=run(a,frozen,cooldown,last)
        ob=run(b,frozen,cooldown,last)
        assert len(oa)==len(ob)
        for u,v in zip(oa,ob):
            assert {k:w for k,w in v.items() if k!="lineage"}==u
            assert v["lineage"]==lineage
        matched+=1
        if oa:positive+=1
        if cooldown==90 and last.get(key,0)==frozen-30 and not oa:cooldown_blocked+=1
        if cooldown==90 and last.get(key,0)==frozen-120 and oa:nonblocked+=1
assert matched>=120
assert positive>0, "no positive selection cases"
assert cooldown_blocked>0 and nonblocked>0
for k,v in old.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
print(json.dumps({
    "real_candidate_events":len(rows),
    "frozen_time_ab_scenarios":matched,
    "selected_positive_scenarios":positive,
    "cooldown_block_cases":cooldown_blocked,
    "cooldown_expiry_release_cases":nonblocked,
    "decision_delta":0,
    "real_cooldown_config":int(conf.get("TOPSEL_COOLDOWN_SEC",90)),
    "redis_writes":0,
    "master_pending_execution_tested":False
},sort_keys=True))
