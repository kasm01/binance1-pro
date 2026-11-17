"""Safety test: all 285 retained intents, oversized JSON and lineage envelope."""
import json
import redis
from pathlib import Path
from research.staging.long1_bridge_trace_envelope_v1 import (
    OversizedRawPayload,serialize_json_bounded,trace_envelope_from_intent)
r=redis.Redis(decode_responses=True,socket_timeout=5)
rows=r.xrevrange("trade_intents_stream_long1",count=285)
assert len(rows)>=200
accepted=0
max_chars=0
for stream_id,fields in rows:
    packet=json.loads(fields["json"])
    for item in packet.get("items",[]):
        trace=trace_envelope_from_intent(item,stream_id)
        assert trace["intent_id"]==item["intent_id"]
        assert trace["candidate_id"]==item["raw"]["candidate_id"]
        serialized=serialize_json_bounded(item)
        assert json.loads(serialized)==item
        max_chars=max(max_chars,len(serialized))
        accepted+=1
assert accepted>=200

huge={"intent_id":"synthetic","raw":{"lineage":{"source_signal_event_id":"signal-1",
      "source_signal_stream_id":"1794845694935-0"},
      "candidate_id":"candidate-1","unneeded_debug":"Z"*30000}}
trace=trace_envelope_from_intent(huge,"1794842643079-0")
assert trace["candidate_id"]=="candidate-1"
assert trace["source_signal_event_id"]=="signal-1"
assert trace["source_signal_stream_id"]=="1794845694935-0"
for limit in [12000,200]:
    try:serialize_json_bounded(huge,limit=limit)
    except OversizedRawPayload:pass
    else:raise AssertionError("large item not rejected")
assert len(serialize_json_bounded(trace,limit=1000))<1000
assert "model_candle_key_unverified" not in trace
for field in ["intent_id","candidate_id","source_signal_event_id","source_signal_stream_id"]:
    assert field in trace
bad=dict(huge,intent_id="bad id with spaces")
try:trace_envelope_from_intent(bad,"1794842643079-0")
except ValueError:pass
else:raise AssertionError("invalid intent id accepted")
print(json.dumps({"retained_intent_items_tested":accepted,
 "max_serialized_item_chars":max_chars,
 "standard_items_roundtrip_equal":accepted,
 "oversized_full_raw_rejected_without_truncation":True,
 "synthetic_large_trace_envelope_preserved":True,
 "trace_candle_not_certified_by_bridge":True,
 "redis_writes":0},sort_keys=True))
