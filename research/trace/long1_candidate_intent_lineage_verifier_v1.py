"""Read-only CANDIDATE -> TOP5 -> INTENT equality verifier.

EXACT_SOURCE is supported only from literal source Redis records.
Does not authenticate broker orders, model prediction, or gate authorization.
"""
from __future__ import annotations
from collections.abc import Mapping
from orchestration.trace.long1_candidate_intent_lineage_v1 import candidate_intent_parent

def verify(*,candidate_stream:str,candidate_stream_id:str,
           candidate:Mapping,top5_stream_id:str,top5:Mapping,
           intent:Mapping)->dict:
    fallback={"state":"UNLINKED","reason":"missing_lineage",
              "advisory_only":True,"can_open":False}
    def reject(reason:str):return dict(fallback,reason=reason)
    if any(not isinstance(x,Mapping) for x in (candidate,top5,intent)):
        return reject("record_missing")
    if candidate.get("symbol")!="NEARUSDT" or intent.get("symbol")!="NEARUSDT":
        return reject("strategy_symbol_invalid")
    if intent.get("side")!=candidate.get("side"):
        return reject("side_mismatch")
    if intent.get("interval")!=candidate.get("interval"):
        return reject("interval_mismatch")
    if not isinstance(top5.get("items"),list):
        return reject("top5_items_invalid")
    if not isinstance(top5_stream_id,str) or not top5_stream_id:
        return reject("top5_source_unknown")
    if intent.get("_source_top5_id")!=top5_stream_id:
        return reject("top5_transport_mismatch")
    possible=[x for x in top5["items"] if isinstance(x,Mapping)
              and x.get("candidate_id")==candidate.get("candidate_id")
              and x.get("_source_stream_id")==candidate_stream_id]
    if len(possible)!=1:
        return reject("selected_candidate_not_unique_or_missing")
    selected=possible[0]
    if selected.get("symbol")!=candidate.get("symbol") or selected.get("side")!=candidate.get("side"):
        return reject("top5_candidate_mismatch")
    expected=candidate_intent_parent(candidate=dict(candidate,
                _source_stream_id=candidate_stream_id),
                candidate_stream=candidate_stream)
    if not expected or "source_candidate_id" not in expected:
        return reject("candidate_transport_identity_missing")
    for field in ("source_candidate_id","source_candidate_stream",
                  "source_candidate_stream_id"):
        if intent.get(field)!=expected[field]:
            return reject("candidate_parent_mismatch")
    # A candidate's model link may be genuinely missing (old input);
    # do not call it exact model lineage, even when candidate link exact.
    model_keys=("parent_signal_event_id","parent_trace_id",
          "source_signal_stream","source_signal_stream_id",
          "model_evaluation_id","model_close_id","model_close_id_kind")
    if all(k in expected for k in model_keys):
        if any(intent.get(k)!=expected[k] for k in model_keys):
            return reject("model_parent_mismatch")
        return {"state":"EXACT_CANDIDATE_AND_MODEL_FIELDS",
                "reason":"literal_redis_source_and_parent_fields_equal",
                "advisory_only":True,"can_open":False}
    return {"state":"EXACT_CANDIDATE_ONLY",
            "reason":"candidate_source_exact_model_unlinked",
            "advisory_only":True,"can_open":False}
