"""LONG1 exact CANDIDATE -> TRADE INTENT provenance.

Advisory-only, zero I/O; never infer a missing candidate source from
TopK Redis transport ID, timestamps, model_score or price.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_ID = re.compile(r"^[A-Za-z0-9_:.|/-]{1,160}$")
_REDIS_ID = re.compile(r"^[0-9]{10,16}-[0-9]+$")

def _id(value:Any)->str|None:
    return value if isinstance(value,str) and _ID.fullmatch(value) else None

def candidate_intent_parent(*,candidate:Mapping[str,Any],
                            candidate_stream:str)->dict[str,Any]:
    if not isinstance(candidate,Mapping) or candidate.get("symbol")!="NEARUSDT":
        return {}
    candidate_id=_id(candidate.get("candidate_id"))
    source_stream_id=candidate.get("_source_stream_id")
    source_stream=_id(candidate_stream)
    if (not candidate_id or not source_stream or not isinstance(source_stream_id,str)
            or not _REDIS_ID.fullmatch(source_stream_id)):
        return {}
    result={
        "source_candidate_id":candidate_id,
        "source_candidate_stream":source_stream,
        "source_candidate_stream_id":source_stream_id,
    }
    # Preserve prior explicit lineage ONLY if the candidate itself has the
    # complete validated Stage6 fields. No synthetic model IDs.
    from orchestration.trace.long1_lineage_v1 import MODEL_CLOSE_KIND
    required=("parent_signal_event_id","parent_trace_id",
              "source_signal_stream","source_signal_stream_id",
              "model_evaluation_id")
    if all(_id(candidate.get(k)) for k in required):
        upstream_stream_id=candidate["source_signal_stream_id"]
        bucket=candidate.get("model_close_id")
        if (isinstance(upstream_stream_id,str) and _REDIS_ID.fullmatch(upstream_stream_id)
                and type(bucket) is int and bucket>0
                and candidate.get("model_close_id_kind")==MODEL_CLOSE_KIND):
            # Parent hash is recomputed from transport, never trusted blindly.
            from orchestration.trace.long1_lineage_v1 import candidate_parent
            expected=candidate_parent(
                {"event_id":candidate["parent_signal_event_id"],
                 "model_evaluation_id":candidate["model_evaluation_id"],
                 "model_close_id":bucket,
                 "model_close_id_kind":MODEL_CLOSE_KIND,
                 "producer_id":"heavy_engine"},
                candidate["source_signal_stream"],upstream_stream_id,
            )
            if candidate["parent_trace_id"]==expected.get("parent_trace_id"):
                result.update({k:candidate[k] for k in required})
                result["model_close_id"]=bucket
                result["model_close_id_kind"]=MODEL_CLOSE_KIND
    return result
