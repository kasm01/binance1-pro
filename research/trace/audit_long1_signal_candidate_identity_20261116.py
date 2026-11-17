"""Read-only Redis identity coverage; never writes and never infers parent matches."""
import json
from collections import Counter
import redis
from orchestration.schemas.events import SignalEvent
from research.trace.long1_candidate_lineage_shadow_v1 import lineage_from_signal

r = redis.Redis(decode_responses=True, socket_timeout=5)
for stream in ("signals_stream_long1", "candidates_stream_long1"):
    result = Counter()
    for stream_id, fields in r.xrange(stream):
        result["total"] += 1
        try:
            item = json.loads(fields["json"])
        except (KeyError, ValueError, TypeError):
            result["parse_failed"] += 1
            continue
        if not isinstance(item, dict):
            result["not_dict"] += 1
            continue
        if stream == "signals_stream_long1":
            signal = SignalEvent.normalize(item)
            signal["_source_stream_id"] = stream_id
            lineage = lineage_from_signal(signal)
            result["source_proof_exact"] += int(lineage["lineage_state"] == "EXACT_SIGNAL_EVENT_ID_AND_STREAM_ID")
            result["model_close_id"] += int("model_close_id" in signal)
            result["meta_close_id"] += int(isinstance(signal.get("meta"), dict) and "close_id" in signal["meta"])
        else:
            result["candidate_id"] += int(bool(item.get("candidate_id")))
            result["lineage"] += int(bool(item.get("lineage")))
            result["explicit_source_parent"] += int(bool(item.get("source_signal_event_id") or item.get("parent_signal_event_id")))
    print(stream, json.dumps(dict(result), sort_keys=True))
