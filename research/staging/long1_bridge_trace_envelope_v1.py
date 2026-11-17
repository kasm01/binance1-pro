"""Read-only research proposal: bounded lossless intent bridge trace envelope.

Never truncate JSON into invalid data. A compact trace envelope goes through
explicit fields rather than depending on nested optional raw passthrough.
No Redis, order, or exchange access.
"""
from __future__ import annotations
import json
import re
from typing import Any, Mapping

_MAX_JSON_CHARS = 12000
_STREAM_ID = re.compile(r"[0-9]{11,16}-[0-9]{1,6}\Z")
_EVENT_ID = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")

class OversizedRawPayload(ValueError):
    pass

def serialize_json_bounded(value: Any, *, limit: int = _MAX_JSON_CHARS) -> str:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 100:
        raise ValueError("invalid bounded JSON limit")
    out = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",",":"))
    if len(out) > limit:
        raise OversizedRawPayload(f"JSON payload exceeds limit={limit}, chars={len(out)}")
    return out

def trace_envelope_from_intent(item: Mapping[str, Any], source_intents_id: str) -> dict[str,str]:
    """Copy only the explicit trusted trace fields; never infer parents."""
    if not isinstance(item, Mapping):
        raise ValueError("expected intent mapping")
    iid=item.get("intent_id")
    if not isinstance(iid,str) or not _EVENT_ID.fullmatch(iid):
        raise ValueError("missing / unsafe intent id")
    if not isinstance(source_intents_id,str) or not _STREAM_ID.fullmatch(source_intents_id):
        raise ValueError("missing source intent Redis id")
    output={"intent_id":iid,"source_intents_id":source_intents_id}
    raw=item.get("raw") if isinstance(item.get("raw"), Mapping) else {}
    cid=raw.get("candidate_id")
    if isinstance(cid,str) and _EVENT_ID.fullmatch(cid):
        output["candidate_id"]=cid
    lineage=raw.get("lineage") if isinstance(raw.get("lineage"),Mapping) else {}
    sid=lineage.get("source_signal_stream_id")
    event=lineage.get("source_signal_event_id")
    if isinstance(sid,str) and _STREAM_ID.fullmatch(sid) and isinstance(event,str) and _EVENT_ID.fullmatch(event):
        output["source_signal_event_id"]=event
        output["source_signal_stream_id"]=sid
        candle=lineage.get("model_candle_key")
        # Candle validation belongs upstream to shared identity module; do not
        # infer a candle or certify from an untrusted path here.
        if isinstance(candle,str) and re.fullmatch(r"NEARUSDT:3m:[0-9]{13}:[0-9]{13}",candle):
            output["model_candle_key_unverified"]=candle
    return output
