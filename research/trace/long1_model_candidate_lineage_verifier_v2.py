"""Verify one literal signal source record against one candidate record.

Never guess lineage from time/price/dedup_key/score. Never creates trades.
An EXACT result verifies Redis transport plus source-payload identity equality,
not the model's market prediction or broker trade fill.
"""
from __future__ import annotations
from collections.abc import Mapping
from orchestration.trace.long1_lineage_v1 import candidate_parent

def verify(*,signal_stream:str,signal_stream_id:str,signal:Mapping,
           candidate:Mapping)->dict:
    out={"state":"UNLINKED","reason":"source_lineage_missing",
         "advisory_only":True,"can_open":False}
    if not isinstance(signal,Mapping) or not isinstance(candidate,Mapping):
        return dict(out,reason="invalid_record")
    if signal.get("symbol")!="NEARUSDT" or candidate.get("symbol")!="NEARUSDT":
        return dict(out,reason="symbol_mismatch")
    if (signal.get("side_candidate") not in ("long","short") or
        signal.get("side_candidate")!=candidate.get("side")):
        return dict(out,reason="side_mismatch")
    expected=candidate_parent(signal,signal_stream,signal_stream_id)
    if "parent_trace_id" not in expected:
        return dict(out,reason="source_stream_id_missing")
    required=("source_signal_stream","source_signal_stream_id","parent_trace_id")
    for k in required:
        if candidate.get(k)!=expected.get(k):
            return dict(out,reason="transport_parent_mismatch")
    if "parent_signal_event_id" not in expected:
        return dict(out,reason="upstream_signal_event_id_missing")
    if candidate.get("parent_signal_event_id")!=expected["parent_signal_event_id"]:
        return dict(out,reason="event_id_mismatch")
    if "model_evaluation_id" not in expected:
        return dict(out,reason="model_evaluation_id_missing")
    if candidate.get("model_evaluation_id")!=expected["model_evaluation_id"]:
        return dict(out,reason="model_evaluation_id_mismatch")
    if "model_close_id" not in expected:
        return dict(out,reason="model_wallclock_bucket_missing")
    if (candidate.get("model_close_id")!=expected["model_close_id"] or
        candidate.get("model_close_id_kind")!=expected["model_close_id_kind"]):
        return dict(out,reason="wallclock_bucket_mismatch")
    if not isinstance(candidate.get("candidate_id"),str) or not candidate["candidate_id"]:
        return dict(out,reason="candidate_id_missing")
    return {"state":"EXACT_SOURCE_AND_EVALUATION",
            "reason":"explicit_source_event_and_model_evaluation_equal",
            "advisory_only":True,"can_open":False,
            "candidate_id":candidate["candidate_id"],
            "parent_trace_id":expected["parent_trace_id"]}
