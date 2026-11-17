"""Staged shared helper -> real selector/master structural decision test, no Redis writes."""
import copy, json, os, time
import redis
from orchestration.selector.top_selector import TopSelector
from orchestration.executor.master_executor import MasterExecutor
from research.staging.long1_identity_runtime_v1 import verified_source_lineage

# Do not source credentials, only current non-secret policy flags.
envkeys=("ACP_ENABLE","ACP_FILTER_BASE_FLOOR","TOPSEL_MIN_SCORE",
         "TOPSEL_TOPK","TOPSEL_COOLDOWN_SEC","TOPSEL_WINDOW_SEC",
         "MASTER_WHALE_BOOST_THR","MASTER_DROP_WHALE_CONTRA")
rawconf={}
for line in open(".env"):
    if "=" in line and not line.startswith("#"):
        k,v=line.strip().split("=",1)
        if k in envkeys:rawconf[k]=v
oldenv={k:os.environ.get(k) for k in envkeys}
os.environ.update(rawconf)
sel=TopSelector.__new__(TopSelector)
sel.window_sec=max(2,int(rawconf.get("TOPSEL_WINDOW_SEC","8")))
sel.topk=int(rawconf.get("TOPSEL_TOPK","3"))
sel.w_min=0.;sel.min_score=float(rawconf.get("TOPSEL_MIN_SCORE","0.1"))
sel.cooldown_sec=int(rawconf.get("TOPSEL_COOLDOWN_SEC","90"))
sel.last_sent={};sel.require_fields=True
sel.penalty_wide_spread=.15;sel.penalty_high_vol=.05
ex=MasterExecutor.__new__(MasterExecutor)
ex.min_trade_score=0.;ex.w_min=0.;ex.require_price=True
ex.trail_pct=.05;ex.stall_ttl_sec=2400
ex.whale_boost_thr=float(rawconf.get("MASTER_WHALE_BOOST_THR",".2"))
ex.drop_if_whale_contra=rawconf.get("MASTER_DROP_WHALE_CONTRA","1")=="1"
ex.whale_use_final_decision=True
ex.whale_hard_block_actions={"block_open","hard_block"}
ex.whale_soft_block_actions={"avoid_open"}
ex.whale_boost_actions={"confirm","strong_confirm","boost_open"}
ex.whale_reduce_actions=set();ex.whale_force_exit_actions=set()
ex.whale_soft_block_score_cap=.55
ex.whale_confirm_score_bonus=.08;ex.whale_strong_confirm_score_bonus=.15
ex.w_w=.60;ex.w_mtf=.25;ex.w_micro=.15
ex.heavy_enable=False;ex._warned_heavy_stub=False
ex.max_pos=1;ex.topn=3;ex.dedup_symbol_open=True
ex._get_open_state=lambda:{}
ex._warned_missing_price=set()
# Eliminate ONLY telemetry writes, not actual whale decision.
ex._emit_long_whale_band_shadow=lambda *args,**kwargs:None
rs=redis.Redis(decode_responses=True,socket_timeout=5)
rows=rs.xrevrange("candidates_stream_long1",count=120)
assert len(rows)>=30
nowms=int(time.time()*1000)
old=[];new=[]
for i,(sid,payload) in enumerate(rows):
    obj=json.loads(payload["json"])
    transport=f"{nowms-200-i}-0"
    # Test source parent identity deterministically with synthetic source IDs
    # (not historical linkage).
    synthetic_signal={
        "event_id":f"stage13-synthetic-{i}",
        "_source_stream_id":sid,
    }
    linkage=verified_source_lineage(
        synthetic_signal,symbol="NEARUSDT",side="long",
        interval="3m",observed_at_ms=nowms
    )
    assert linkage
    old.append((transport,copy.deepcopy(obj)))
    new.append((transport,dict(copy.deepcopy(obj),lineage=linkage)))
assert len(old)==len(new)
import contextlib,io
with contextlib.redirect_stdout(io.StringIO()):
    ta=sel._select_topk(copy.deepcopy(old))
    tb=sel._select_topk(copy.deepcopy(new))
    assert len(ta)==len(tb)
    for a,b in zip(ta,tb):
        assert {k:v for k,v in b.items() if k!="lineage"}==a
        assert "lineage" in b
    direct=0; accepted=0; rejected=0
    for (_,a),(_,b) in zip(old,new):
        ia=ex._make_intent(copy.deepcopy(a))
        ib=ex._make_intent(copy.deepcopy(b))
        assert (ia is None)==(ib is None)
        if ia is None:rejected+=1;continue
        assert (ia.symbol,ia.side,ia.price,ia.score)==(ib.symbol,ib.side,ib.price,ib.score)
        assert {k:v for k,v in ib.raw.items() if k!="lineage"}==ia.raw
        assert ib.raw["lineage"]==b["lineage"]
        accepted+=1;direct+=1
    assert accepted+rejected==len(old)
    # Actual real Master policy must remain identical even when Top-K winner is rejected.
    la=ex._select_top_unique(copy.deepcopy(ta))
    lb=ex._select_top_unique(copy.deepcopy(tb))
    assert len(la)==len(lb)
    for a,b in zip(la,lb):
        assert (a.symbol,a.side,a.price,a.score)==(b.symbol,b.side,b.price,b.score)
        assert b.raw["lineage"]["source_signal_event_id"]
for k,v in oldenv.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
print(json.dumps({
    "real_candidate_samples":len(old),
    "top_selector_choice_equal":len(ta),
    "master_selected_intents_equal":len(la),
    "independent_master_accepted_equal":accepted,
    "independent_master_rejected_equal":rejected,
    "metadata_changes_to_decision":0,
    "no_redis_writes":True,
    "synthetic_lineage_is_historical":False,
    "frozen_historical_replay":False,
},sort_keys=True))
