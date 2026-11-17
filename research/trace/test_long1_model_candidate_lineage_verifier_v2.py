"""Only exact matches; no score/time based guess and no Redis writes."""
import json
from research.trace.long1_model_candidate_lineage_verifier_v2 import verify
from orchestration.trace.long1_lineage_v1 import candidate_parent
signal={"symbol":"NEARUSDT","side_candidate":"long","event_id":"signal-123",
        "producer_id":"heavy_engine","model_evaluation_id":"eval-aabb",
        "model_close_id":1794706000,"model_close_id_kind":"wallclock_bucket_180s",
        "model_score":.55}
candidate=dict({"candidate_id":"candidate-1","symbol":"NEARUSDT","side":"long"},
               **candidate_parent(signal,"signals_stream_long1","1794706000000-1"))
def check(name,cand= None,sig=None,expect=None):
 result=verify(signal_stream="signals_stream_long1",
    signal_stream_id="1794706000000-1",signal=signal if sig is None else sig,
    candidate=candidate if cand is None else cand)
 assert result["state"]==expect,(name,result)
 assert result["can_open"] is False and result["advisory_only"] is True
 return result["reason"]
assert check("positive",expect="EXACT_SOURCE_AND_EVALUATION")
bad={
"missing_event":({**signal,"event_id":None},None),
"missing_eval":({**signal,"model_evaluation_id":None},None),
"missing_bucket":({**signal,"model_close_id":None},None),
"wrong_side":({**signal,"side_candidate":"short"},None),
"wrong_symbol":({**signal,"symbol":"BTCUSDT"},None),
"wrong_parent":(None,{**candidate,"parent_trace_id":"wrong"}),
"wrong_transport":(None,{**candidate,"source_signal_stream_id":"1794706000000-2"}),
"wrong_event":(None,{**candidate,"parent_signal_event_id":"foreign"}),
"wrong_eval":(None,{**candidate,"model_evaluation_id":"eval-foreign"}),
"wrong_bucket":(None,{**candidate,"model_close_id":1794706001}),
"wrong_bucket_kind":(None,{**candidate,"model_close_id_kind":"exchange_closed_candle"}),
"missing_candidate":(None,{**candidate,"candidate_id":None}),
"score_same_missing_parent":(None,{"candidate_id":"unlinked","symbol":"NEARUSDT",
                                  "side":"long","model_score":.55}),
}
for name,(sig,cand) in bad.items():
 reason=check(name,cand=cand,sig=sig,expect="UNLINKED")
print(json.dumps({"exact_positive":1,"negative_unlinked":len(bad),
 "score_or_time_never_promoted_to_exact":True,
 "production_redis_writes":0,"exchange_orders":0,"result":"PASS"},sort_keys=True))
