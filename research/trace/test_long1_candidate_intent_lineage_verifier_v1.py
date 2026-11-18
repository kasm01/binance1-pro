"""Never infer exact from score/time, must compare real source fields."""
import json
from research.trace.long1_candidate_intent_lineage_verifier_v1 import verify
from orchestration.trace.long1_lineage_v1 import candidate_parent
from orchestration.trace.long1_candidate_intent_lineage_v1 import candidate_intent_parent

signal=dict(producer_id='heavy_engine',event_id='s12',
            model_evaluation_id='eval123',model_close_id=1794706000,
            model_close_id_kind='wallclock_bucket_180s')
c=dict(candidate_id='c11',symbol='NEARUSDT',interval='3m',side='long',
       score_total=.60)
c.update(candidate_parent(signal,'signals_stream_long1','1794706000000-1'))
stream='candidates_stream_long1'
cid='1794706001000-0'
tid='1794706002000-0'
top=dict(items=[dict(c,_source_stream_id=cid)])
intent=dict(intent_id='i11',symbol='NEARUSDT',side='long',interval='3m',
    _source_top5_id=tid,
    **candidate_intent_parent(candidate=dict(c,_source_stream_id=cid),
        candidate_stream=stream))
def case(name,*,candidate=None,top5=None,entry=None,expected='UNLINKED',topid=tid):
    proof=verify(candidate_stream=stream,candidate_stream_id=cid,
         candidate=c if candidate is None else candidate,
         top5=top if top5 is None else top5,
         top5_stream_id=topid,
         intent=intent if entry is None else entry)
    assert proof['state']==expected,(name,proof)
    assert proof['can_open'] is False
    return proof['reason']
assert case('all',expected='EXACT_CANDIDATE_AND_MODEL_FIELDS')
legacy=dict(c);legacy.pop('model_evaluation_id')
legacy_top=dict(items=[dict(legacy,_source_stream_id=cid)])
legacy_intent=dict(intent_id='i11',symbol='NEARUSDT',side='long',interval='3m',
  _source_top5_id=tid,**candidate_intent_parent(
      candidate=dict(legacy,_source_stream_id=cid),candidate_stream=stream))
case('legacy',candidate=legacy,top5=legacy_top,entry=legacy_intent,
     expected='EXACT_CANDIDATE_ONLY')
bad={
 'intent_without_candidate_identity':dict(intent,source_candidate_id=None),
 'wrong_candidate_stream':dict(intent,source_candidate_stream='other'),
 'wrong_candidate_id':dict(intent,source_candidate_stream_id='1794706001001-0'),
 'wrong_model_id':dict(intent,model_evaluation_id='eval-other'),
 'wrong_parent':dict(intent,parent_trace_id='bad'),
 'wrong_top5_id':dict(intent,_source_top5_id='1794706002001-0'),
 'same_score_no_trace':dict(intent,source_candidate_id=None,
                            source_candidate_stream_id=None,
                            parent_trace_id=None,model_evaluation_id=None),
 'other_side':dict(intent,side='short'),
 'other_symbol':dict(intent,symbol='INJUSDT'),
}
for label,obj in bad.items():
    case(label,entry=obj)
case('missing_top5_item',top5={'items':[]})
case('duplicate_selected',top5={'items':top['items']*2})
case('wrong_top5_transport',topid='1794706002002-0')
case('source_candidate_corrupt',candidate=dict(c,candidate_id=None))
print(json.dumps({'positive_exact':1,'legacy_candidate_only':1,
    'negative_unlinked':len(bad)+4,'score_equal_not_proof':True,
    'side_and_top5_parent_bound':True,'real_orders':0,
    'production_redis_writes':0,'result':'PASS'},sort_keys=True))
