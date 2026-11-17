"""LONG1 research-only trace schema v1; strict and fail-closed.

No writes, no trading authority. Immutable transport trace id and lineage
stages. The same upstream intent_id is required for exact intent-to-exec
correlation; model-to-intent linkage is never inferred from close_id/timing.
"""
from __future__ import annotations
import hashlib
import re
from math import isfinite
from typing import Mapping

VERSION="long1.trace.v1"
STAGES=frozenset({
 "MODEL","SIGNAL_NORMALIZATION","MARKET_CONTEXT","MODEL_SCORE_GATE","SNIPER",
 "ENTRY_CONFIRMATION","PENDING_REVALIDATION","CONTRA_TREND","EXECUTION_RISK",
 "FINAL_SAFETY","EXECUTION_INTENT","ORDER_SUBMITTED","ORDER_FILLED","POSITION_LIFECYCLE","OUTCOME"
})
STATES=frozenset({"OBSERVED","READY","PENDING","REJECT","SKIPPED","MISSING_OBSERVABILITY",
                   "SUBMITTED","FILLED","CLOSED","FAILED","UNLINKED"})
KINDS=frozenset({"EXACT_INTENT","EXACT_SOURCE_STREAM_ID","EXACT_ORDER_ID",
                  "INDEPENDENT_EVENT","UNLINKED"})
ID_LIMIT=160
def safe_id(v):
 if not isinstance(v,str) or not 1<=len(v)<=ID_LIMIT:
  raise ValueError("identity must be 1..160 chars")
 if not re.fullmatch(r"[A-Za-z0-9_:.|/-]+",v):
  raise ValueError("unsupported identity characters")
 return v
def trace_id_from_transport(stream_name:str, stream_id:str)->str:
 """Source-unique fingerprint; NOT proof of any causal downstream lineage."""
 safe_id(stream_name);safe_id(stream_id)
 return "long1:"+hashlib.sha256((stream_name+"\x00"+stream_id).encode()).hexdigest()[:24]
def validate(record:Mapping)->dict:
 if not isinstance(record,dict):raise ValueError("event must be dictionary")
 allowed={"schema","trace_id","parent_trace_id","attempt_id","strategy","symbol","side",
          "stage","state","reason","observed_at_ms","source_closed_at_ms",
          "source_stream","source_stream_id","intent_id","model_close_id",
          "position_id","exchange_order_id","correlation_kind","advisory_only"}
 unknown=set(record)-allowed
 if unknown:raise ValueError("unsupported fields: "+",".join(sorted(unknown)))
 needed={"schema","trace_id","strategy","symbol","side","stage","state",
         "reason","observed_at_ms","correlation_kind","advisory_only"}
 if not needed.issubset(record):raise ValueError("missing required fields")
 if record["schema"]!=VERSION:raise ValueError("schema version")
 if record["strategy"]!="LONG1" or record["symbol"]!="NEARUSDT" or record["side"]!="LONG":
  raise ValueError("LONG1 NEARUSDT only")
 if record["stage"] not in STAGES or record["state"] not in STATES:
  raise ValueError("invalid transition")
 if record["correlation_kind"] not in KINDS:raise ValueError("invalid correlation kind")
 if record["advisory_only"] is not True:raise ValueError("must be shadow-only")
 for k in ("trace_id","parent_trace_id","attempt_id","intent_id",
           "position_id","source_stream","source_stream_id","exchange_order_id"):
  if record.get(k) is not None:safe_id(record[k])
 if record.get("source_stream_id") is not None and record.get("source_stream") is None:
  raise ValueError("stream id requires stream")
 t=record["observed_at_ms"]
 if type(t) is not int or t<=0:raise ValueError("invalid observed_at_ms")
 c=record.get("source_closed_at_ms")
 if c is not None and (type(c) is not int or c>t or c<=0):
  raise ValueError("closed candle cannot be from future")
 m=record.get("model_close_id")
 if m is not None and (type(m) is not int or m<=0):raise ValueError("invalid model_close_id")
 reason=record["reason"]
 if not isinstance(reason,str) or not 1<=len(reason)<=96 or not re.fullmatch("[a-z0-9_.:-]+",reason):
  raise ValueError("reason must be compact lowercase code")
 if record["correlation_kind"]=="EXACT_INTENT" and not record.get("intent_id"):
  raise ValueError("exact intent requires intent_id")
 if record["correlation_kind"]=="EXACT_SOURCE_STREAM_ID" and not record.get("source_stream_id"):
  raise ValueError("exact source requires stream id")
 if record["correlation_kind"]=="EXACT_ORDER_ID" and not record.get("exchange_order_id"):
  raise ValueError("exact order requires order id")
 if record["stage"]=="ORDER_FILLED" and not record.get("exchange_order_id"):
  raise ValueError("filled stage requires order id")
 if record["state"]=="UNLINKED" and record["correlation_kind"]!="UNLINKED":
  raise ValueError("unlinked not exact")
 return dict(record)

def event(*,stream,stream_id,at_ms,stage,state,reason,kind="INDEPENDENT_EVENT",
          intent_id=None,parent_trace_id=None,order_id=None):
 out=dict(schema=VERSION,trace_id=trace_id_from_transport(stream,stream_id),
  strategy="LONG1",symbol="NEARUSDT",side="LONG",
  stage=stage,state=state,reason=reason,observed_at_ms=at_ms,
  source_stream=stream,source_stream_id=stream_id,
  correlation_kind=kind,advisory_only=True)
 if intent_id:out["intent_id"]=intent_id
 if parent_trace_id:out["parent_trace_id"]=parent_trace_id
 if order_id:out["exchange_order_id"]=order_id
 return validate(out)
