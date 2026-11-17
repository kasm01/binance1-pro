"""A/B replay of policy METHODS with file config, real candidate fixtures; no writes."""
import contextlib
import copy
import io
import json
import os
import time
from pathlib import Path
import redis
from orchestration.selector.top_selector import TopSelector
from orchestration.executor.master_executor import MasterExecutor
from research.trace.long1_candidate_lineage_shadow_v1 import candidate_shadow

# Explicit whitelist: no API secrets, no global .env sourcing or live config edits.
NAMES=("ACP_ENABLE ACP_LIMITER_ENABLE ACP_FILTER_BASE_FLOOR ACP_LOG_TOPK "
"ACP_LIMITER_LOG_BLOCKS ACP_LIMITER_HARD_CAP ACP_LIMITER_MAX_BOOST "
"TOPSEL_TOPK TOPSEL_WINDOW_SEC TOPSEL_COOLDOWN_SEC TOPSEL_MIN_SCORE "
"TOPSEL_W_MIN MASTER_MIN_TRADE_SCORE MASTER_W_MIN MASTER_MAX_POS MASTER_TOPN "
"MASTER_DROP_WHALE_CONTRA MASTER_WHALE_BOOST_THR MASTER_REQUIRE_PRICE "
"MASTER_WHALE_USE_FINAL_DECISION MASTER_WHALE_HARD_BLOCK_ACTIONS "
"MASTER_WHALE_SOFT_BLOCK_ACTIONS MASTER_WHALE_BOOST_ACTIONS "
"MASTER_WHALE_SOFT_BLOCK_SCORE_CAP MASTER_WHALE_CONFIRM_SCORE_BONUS "
"MASTER_WHALE_STRONG_CONFIRM_SCORE_BONUS MASTER_WHALE_FORCE_EXIT_ACTIONS "
"MASTER_WHALE_REDUCE_ACTIONS MASTER_W_SCORE_WHALE MASTER_W_SCORE_MTF "
"MASTER_W_SCORE_MICRO MASTER_HEAVY_ENABLE MASTER_HEAVY_TOPK "
"MASTER_HEAVY_DISCARD_BELOW MASTER_WHALE_BAND_SHADOW_ENABLE "
"REQUIRE_WHALE_FOR_OPEN STRICT_WHALE_ALIGNMENT WHALE_OPEN_MIN_SCORE "
"DEDUP_SYMBOL_OPEN STALL_TTL_SEC TRAIL_PCT").split()
conf={}
for line in Path(".env").read_text().splitlines():
    line=line.strip()
    if not line or line.startswith("#") or "=" not in line: continue
    k,v=line.split("=",1)
    if k in NAMES:conf[k]=v.strip().strip("'").strip('"')
oldenv={key:os.environ.get(key) for key in NAMES}
os.environ.update(conf)
def num(k,default):return float(os.getenv(k,str(default)) or default)
def truth(k,default):return str(os.getenv(k,"1" if default else "0")).lower() in ("1","true","yes","on")
def choices(k,default):return set(x.strip() for x in os.getenv(k,default).split(",") if x.strip())
sel=TopSelector.__new__(TopSelector)
sel.window_sec=int(num("TOPSEL_WINDOW_SEC",8))
sel.topk=int(num("TOPSEL_TOPK",3))
sel.min_score=num("TOPSEL_MIN_SCORE",0.1)
sel.w_min=num("TOPSEL_W_MIN",0)
sel.cooldown_sec=num("TOPSEL_COOLDOWN_SEC",90)
sel.last_sent={}
sel.require_fields=True
sel.penalty_wide_spread=.15
sel.penalty_high_vol=.05
ex=MasterExecutor.__new__(MasterExecutor)
ex.require_price=truth("MASTER_REQUIRE_PRICE",True)
ex.min_trade_score=num("MASTER_MIN_TRADE_SCORE",.1)
ex.trail_pct=num("TRAIL_PCT",.05)
ex.stall_ttl_sec=int(num("STALL_TTL_SEC",0))
ex.w_min=num("MASTER_W_MIN",0)
ex.whale_boost_thr=num("MASTER_WHALE_BOOST_THR",.20)
ex.drop_if_whale_contra=truth("MASTER_DROP_WHALE_CONTRA",True)
ex.whale_use_final_decision=truth("MASTER_WHALE_USE_FINAL_DECISION",True)
ex.whale_hard_block_actions=choices("MASTER_WHALE_HARD_BLOCK_ACTIONS","block_open,hard_block")
ex.whale_soft_block_actions=choices("MASTER_WHALE_SOFT_BLOCK_ACTIONS","avoid_open")
ex.whale_boost_actions=choices("MASTER_WHALE_BOOST_ACTIONS","confirm,strong_confirm,boost_open")
ex.whale_reduce_actions=choices("MASTER_WHALE_REDUCE_ACTIONS","reduce_size,tighten_risk")
ex.whale_force_exit_actions=choices("MASTER_WHALE_FORCE_EXIT_ACTIONS","force_exit")
ex.whale_soft_block_score_cap=num("MASTER_WHALE_SOFT_BLOCK_SCORE_CAP",.55)
ex.whale_confirm_score_bonus=num("MASTER_WHALE_CONFIRM_SCORE_BONUS",.08)
ex.whale_strong_confirm_score_bonus=num("MASTER_WHALE_STRONG_CONFIRM_SCORE_BONUS",.15)
ex.w_w=num("MASTER_W_SCORE_WHALE",.60)
ex.w_mtf=num("MASTER_W_SCORE_MTF",.25)
ex.w_micro=num("MASTER_W_SCORE_MICRO",.15)
ex.heavy_enable=truth("MASTER_HEAVY_ENABLE",False)
ex._warned_heavy_stub=False
ex.topn=int(num("MASTER_TOPN",3))
ex.max_pos=int(num("MASTER_MAX_POS",3))
ex.dedup_symbol_open=truth("DEDUP_SYMBOL_OPEN",True)
ex._warned_missing_price=set()
# Critical: disable ONLY shadow writer; actual whale decision code remains active.
ex._emit_long_whale_band_shadow=lambda *args,**kwargs: None
# Never connect MasterExecutor to Redis, never modify live position state.
ex._get_open_state=lambda: {}
rows=redis.Redis(decode_responses=True,socket_timeout=5).xrevrange("candidates_stream_long1",count=120)
assert len(rows)>=30
fixtures=[]
nowms=int(time.time()*1000)
for i,(sid,fields) in enumerate(rows):
    obj=json.loads(fields["json"])
    if obj.get("symbol")!="NEARUSDT":continue
    fixtures.append((f"{nowms-100-i}-0",obj))
assert len(fixtures)>=30
# Synthetic ancestry for STRUCTURAL test; never represent it as historical proof.
tag={"lineage_state":"EXACT_SIGNAL_EVENT_ID_AND_STREAM_ID",
     "source_signal_event_id":"stage10-synthetic-signal",
     "source_signal_stream_id":"1794845694935-0"}
old=[(sid,copy.deepcopy(c)) for sid,c in fixtures]
new=[(sid,dict(copy.deepcopy(c),lineage=copy.deepcopy(tag))) for sid,c in fixtures]
out={}
def stripped(obj):
    z=copy.deepcopy(obj)
    z.pop("lineage",None)
    return z
with contextlib.redirect_stdout(io.StringIO()):
    # Actual policy config and score, including ACP state from .env.
    scores=0; intents=0; rejected=0
    for (sid,a),(sid2,b) in zip(old,new):
        assert sid==sid2
        a=sel._normalize_candidate(copy.deepcopy(a),sid)
        b=sel._normalize_candidate(copy.deepcopy(b),sid)
        assert sel._adaptive_coin_priority_score(a)==sel._adaptive_coin_priority_score(b)
        assert sel._score(a)==sel._score(b)
        assert sel._cooldown_key(a)==sel._cooldown_key(b)
        assert sel._required_ok(a)==sel._required_ok(b)
        assert ex._compute_final_score(a)==ex._compute_final_score(b)
        aa=ex._make_intent(copy.deepcopy(a))
        bb=ex._make_intent(copy.deepcopy(b))
        assert (aa is None)==(bb is None)
        if aa is None: rejected+=1
        else:
            assert (aa.symbol,aa.interval,aa.side,aa.price,aa.score,aa.trail_pct,aa.stall_ttl_sec)==(bb.symbol,bb.interval,bb.side,bb.price,bb.score,bb.trail_pct,bb.stall_ttl_sec)
            assert stripped(bb.raw)==aa.raw and bb.raw["lineage"]==tag
            intents+=1
        scores+=1
    # Complete selector decision for single common-batch input in same virtual time.
    ta=sel._select_topk(copy.deepcopy(old))
    tb=sel._select_topk(copy.deepcopy(new))
    assert len(ta)==len(tb)
    for a,b in zip(ta,tb):
        assert stripped(b)==a and b["lineage"]==tag
    # Position safety: in-memory frozen empty and occupied snapshots, no Redis access.
    decisions={}
    for mode,state in (("empty",{}),("occupied",{"NEARUSDT":{"qty":1}})):
        ex._get_open_state=lambda s=state:copy.deepcopy(s)
        oa=ex._select_top_unique(copy.deepcopy(ta))
        ob=ex._select_top_unique(copy.deepcopy(tb))
        assert len(oa)==len(ob)
        for a,b in zip(oa,ob):
            assert (a.symbol,a.side,a.price,a.score)==(b.symbol,b.side,b.price,b.score)
            assert stripped(b.raw)==a.raw and b.raw["lineage"]==tag
        decisions[mode]=len(oa)
    # Additional controlled high-score scenario exercises actual open-slot gate.
    # It is synthetic (NOT a historical accepted event), and uses real policy.
    seed=copy.deepcopy(fixtures[0][1])
    seed["score_total"]=0.99
    seed["model_score"]=0.99
    seed["whale_dir"]="none"
    seed["whale_score"]=0.0
    seed["risk_tags"]=[]
    seed["raw"]={"price":float(seed["price"]),"whale_dir":"none","whale_score":0.0}
    seed["dedup_key"]="NEARUSDT|3m|long"
    seed["side"]="long"
    empty_a=sel._normalize_candidate(copy.deepcopy(seed),f"{nowms-50}-0")
    empty_b=sel._normalize_candidate(dict(copy.deepcopy(seed),lineage=copy.deepcopy(tag)),f"{nowms-50}-0")
    accepted=ex._make_intent(copy.deepcopy(empty_a))
    assert accepted is not None, "synthetic positive fixture blocked unexpectedly"
    slot_tests={}
    for mode,state in (("empty",{}),("occupied",{"NEARUSDT":{"qty":1}})):
        ex._get_open_state=lambda s=state:copy.deepcopy(s)
        a=ex._select_top_unique([copy.deepcopy(empty_a)])
        b=ex._select_top_unique([copy.deepcopy(empty_b)])
        assert len(a)==len(b)
        if mode=="empty": assert len(a)==1
        if mode=="occupied": assert len(a)==0
        if a: assert stripped(b[0].raw)==a[0].raw and b[0].raw["lineage"]==tag
        slot_tests[mode]=len(a)
    out=dict(policy_score_pairs=scores,real_whale_policy_intent_pairs=intents,
             controlled_position_slot_tests=slot_tests,
             real_whale_policy_rejections=rejected,top_selected=len(ta),
             position_snapshot_decisions=decisions,
             acp_enabled=truth("ACP_ENABLE",True),
             no_routing_writes=True)
for k,v in oldenv.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
print(json.dumps(out,sort_keys=True))
