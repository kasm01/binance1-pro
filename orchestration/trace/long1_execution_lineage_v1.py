"""LONG1 intent -> execution/PENDING/position shadow metadata, advisory only.

Never infer absent parents from score or time. Never grant order authority.
An origin intent is stable during pending rechecks; the current recheck
intent remains distinct. No state, network, Redis or exchange side effects.
"""
from __future__ import annotations
import re
import uuid
from collections.abc import Mapping
from typing import Any

_ID=re.compile(r"^[A-Za-z0-9_:.|/-]{1,160}$")
_REDIS_ID=re.compile(r"^[0-9]{10,16}-[0-9]+$")
_KEYS=("source_candidate_id","source_candidate_stream",
       "source_candidate_stream_id","parent_signal_event_id",
       "parent_trace_id","source_signal_stream","source_signal_stream_id",
       "model_evaluation_id")
_BUCKET="wallclock_bucket_180s"

def _id(v:Any)->bool:
    return isinstance(v,str) and _ID.fullmatch(v) is not None

def compact(item:Mapping|None)->dict:
    if not isinstance(item,Mapping) or str(item.get("symbol") or "").upper()!="NEARUSDT":
        return {}
    result={k:item[k] for k in _KEYS if _id(item.get(k))}
    for key in ("source_candidate_stream_id","source_signal_stream_id"):
        if key in result and not _REDIS_ID.fullmatch(result[key]):
            result.pop(key,None)
    if (type(item.get("model_close_id")) is int and item["model_close_id"]>0
            and item.get("model_close_id_kind")==_BUCKET):
        result["model_close_id"]=item["model_close_id"]
        result["model_close_id_kind"]=_BUCKET
    return result

def from_trade_intent(item:Mapping|None)->dict:
    if not isinstance(item,Mapping):return {}
    result=compact(item)
    # Partial trace links are allowed as advisory annotations, never as
    # strict full-model provenance or order permission.
    if str(item.get("symbol") or "").upper()=="NEARUSDT" and _id(item.get("intent_id")):
        result["intent_id"]=item["intent_id"]
    return result

def new_pending_origin(extra:Mapping|None)->dict:
    result={"pending_attempt_id":"pending-"+uuid.uuid4().hex,
            "pending_recheck_count":0}
    if isinstance(extra,Mapping):
        if _id(extra.get("intent_id")):result["pending_origin_intent_id"]=extra["intent_id"]
        parent=compact(extra)
        if parent:result["pending_origin_lineage"]=parent
    return result

def preserve_pending_origin(original:Mapping|None,recheck:Mapping|None)->dict:
    merged=dict(original) if isinstance(original,Mapping) else {}
    for k,v in (recheck.items() if isinstance(recheck,Mapping) else ()):
        if k not in ("pending_attempt_id","pending_origin_intent_id",
                     "pending_origin_lineage","pending_recheck_count"):
            merged[k]=v
    if not _id(merged.get("pending_attempt_id")):
        merged["pending_attempt_id"]="pending-"+uuid.uuid4().hex
    old=merged.get("pending_recheck_count",0)
    try:old=int(old)
    except (TypeError,ValueError):old=0
    merged["pending_recheck_count"]=max(0,old)+1
    if isinstance(recheck,Mapping) and _id(recheck.get("intent_id")):
        merged["pending_recheck_intent_id"]=recheck["intent_id"]
    return merged
