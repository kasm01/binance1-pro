"""In-memory comparison with real Redis candidate fixtures; NEVER publishes orders."""
import copy
import json
import os
import time
import redis
from orchestration.selector.top_selector import TopSelector
from orchestration.executor.master_executor import MasterExecutor

r = redis.Redis(decode_responses=True, socket_timeout=6)
rows=r.xrevrange("candidates_stream_long1",count=120)
assert rows, "No candidates available"
# Fixture-derived events; synthetic fresh transport IDs FOR THE ISOLATED WINDOW ONLY.
base=[]
for i,(sid, fields) in enumerate(rows):
    c=json.loads(fields["json"])
    if not isinstance(c,dict) or c.get("symbol")!="NEARUSDT":
        continue
    base.append((f"{int(time.time()*1000)-1000-i}-0",c))
assert len(base)>=30
metadata={"lineage_state":"EXACT_SIGNAL_EVENT_ID_AND_STREAM_ID",
          "source_signal_event_id":"synthetic-model-event-stage9",
          "source_signal_stream_id":"1794845694935-0"}
old=[(sid,copy.deepcopy(c)) for sid,c in base]
new=[(sid,dict(copy.deepcopy(c),lineage=copy.deepcopy(metadata))) for sid,c in base]
sel=TopSelector.__new__(TopSelector)
sel.window_sec=60
sel.w_min=0.
sel.min_score=0.
sel.topk=3
sel.cooldown_sec=0.
sel.last_sent={}
sel.require_fields=True
sel.penalty_wide_spread=.15
sel.penalty_high_vol=.05
sel.cooldown_cache_max=50000
# ACP disabled only in this isolated test; no config or live process changes.
old_env={k:os.environ.get(k) for k in ["ACP_ENABLE","ACP_FILTER_BASE_FLOOR","ACP_LOG_TOPK","ACP_LIMITER_LOG_BLOCKS"]}
os.environ.update({"ACP_ENABLE":"0","ACP_FILTER_BASE_FLOOR":"0","ACP_LOG_TOPK":"0","ACP_LIMITER_LOG_BLOCKS":"0"})
try:
    top_old=sel._select_topk(old)
    top_new=sel._select_topk(new)
finally:
    for key,val in old_env.items():
        if val is None:os.environ.pop(key,None)
        else:os.environ[key]=val
assert top_old and len(top_old)==len(top_new), (len(top_old),len(top_new))
for a,b in zip(top_old,top_new):
    assert {k:v for k,v in b.items() if k!="lineage"}==a
    assert b["lineage"]==metadata
    assert a["candidate_id"]==b["candidate_id"]

ex=MasterExecutor.__new__(MasterExecutor)
ex.require_price=True
ex.min_trade_score=0.
ex.trail_pct=.005
ex.stall_ttl_sec=300
ex.w_min=0.
ex.whale_boost_actions={"boost_open","strong_confirm"}
# Stubbed policy ONLY to isolate structural payload path; not testing actual risk permission.
ex._reject_by_whale_policy=lambda *args:False
pairs=[]
for a,b in zip(top_old,top_new):
    ia=ex._make_intent(copy.deepcopy(a))
    ib=ex._make_intent(copy.deepcopy(b))
    assert (ia is None)==(ib is None)
    if ia is None: continue
    assert ia.symbol==ib.symbol and ia.side==ib.side
    assert ia.score==ib.score and ia.price==ib.price
    assert ia.trail_pct==ib.trail_pct and ia.stall_ttl_sec==ib.stall_ttl_sec
    assert {k:v for k,v in ib.raw.items() if k!="lineage"}==ia.raw
    assert ib.raw["lineage"]==metadata
    assert ib.raw["candidate_id"]==a["candidate_id"]
    assert ia.intent_id != ib.intent_id
    pairs.append((ia,ib))
assert pairs
# TopSelector collapses same dedup-key to one winner, so independently verify
# _make_intent structural metadata preservation for ALL retained candidates.
direct_pairs=0
for (_,orig),(_,tagged) in zip(old,new):
    a=sel._normalize_candidate(copy.deepcopy(orig),"1794845694935-0")
    b=sel._normalize_candidate(copy.deepcopy(tagged),"1794845694935-0")
    ia=ex._make_intent(a)
    ib=ex._make_intent(b)
    assert (ia is None)==(ib is None)
    if ia is None:continue
    assert (ia.symbol,ia.side,ia.price,ia.score)==(ib.symbol,ib.side,ib.price,ib.score)
    assert {k:v for k,v in ib.raw.items() if k!="lineage"}==ia.raw
    assert ib.raw["lineage"]==metadata
    direct_pairs+=1
assert direct_pairs>=30, direct_pairs
print(json.dumps({"redis_candidate_fixtures":len(base),
 "top_selected_equal":len(top_old),
 "intent_payload_pairs_equal":len(pairs),
 "lineage_transferred":len(pairs),
 "individual_intent_payload_equal":direct_pairs,
 "scope":"Structural in-memory methods; ACP disabled, whale policy stubbed; not full risk or live order replay"},sort_keys=True))
