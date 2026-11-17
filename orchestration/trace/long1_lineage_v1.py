"""Small additive LONG1 model -> signal -> candidate lineage fields.

No Redis, exchange, disk, logging, or order authority.
The model close_id below is a 180s wallclock bucket, NOT an exchange
closed-candle identity. Carry model_evaluation_id as the actual unique
model calculation identity. Parent source stream ID is exact transport
provenance; it is not proof of Binance fill or downstream execution.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any, Mapping

MODEL_CLOSE_KIND="wallclock_bucket_180s"
_STREAM_ID=re.compile(r"^[0-9]{10,16}-[0-9]+$")
_IDENT=re.compile(r"^[A-Za-z0-9_:.|/-]{1,160}$")

def new_model_evaluation_id()->str:
    return "eval-"+uuid.uuid4().hex

def _identity(x:Any)->str|None:
    if isinstance(x,str) and _IDENT.fullmatch(x):
        return x
    return None

def decorate_model_signal(payload:dict,*,model_evaluation_id:Any=None,
                          model_close_id:Any=None)->dict:
    """Add only explicitly supplied and valid advisory fields."""
    if not isinstance(payload,dict):raise ValueError("payload_not_mapping")
    out=dict(payload)
    ident=_identity(model_evaluation_id)
    if ident:
        out["model_evaluation_id"]=ident
    if type(model_close_id) is int and model_close_id>0:
        out["model_close_id"]=model_close_id
        out["model_close_id_kind"]=MODEL_CLOSE_KIND
    return out

def candidate_parent(signal:Mapping[str,Any],stream:str,stream_id:str)->dict:
    """Exact provenance only for observed transport and explicit signal ID.

    No relationship is guessed from score, timestamp, dedup_key or close_id.
    """
    result={}
    if not isinstance(signal,Mapping) or not _identity(stream) or not isinstance(stream_id,str) or not _STREAM_ID.fullmatch(stream_id):
        return result
    result["source_signal_stream"]=stream
    result["source_signal_stream_id"]=stream_id
    result["parent_trace_id"]="long1:"+hashlib.sha256(
        (stream+"\x00"+stream_id).encode()).hexdigest()[:24]
    signal_id=_identity(signal.get("event_id"))
    if signal_id:
        result["parent_signal_event_id"]=signal_id
    eval_id=_identity(signal.get("model_evaluation_id"))
    if eval_id and str(signal.get("producer_id") or "").lower()=="heavy_engine":
        result["model_evaluation_id"]=eval_id
    bucket=signal.get("model_close_id")
    if (type(bucket) is int and bucket>0 and
        signal.get("model_close_id_kind")==MODEL_CLOSE_KIND and
        str(signal.get("producer_id") or "").lower()=="heavy_engine"):
        result["model_close_id"]=bucket
        result["model_close_id_kind"]=MODEL_CLOSE_KIND
    return result
