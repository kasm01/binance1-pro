"""AST-extract actual TopSelector + MasterExecutor publisher. No live Redis."""
import ast,copy,json,os,uuid
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from orchestration.trace.long1_lineage_v1 import candidate_parent
from orchestration.trace.long1_candidate_intent_lineage_v1 import candidate_intent_parent
from orchestration.executor.master_executor import TradeIntent,_now_utc_iso,_safe_float
from orchestration.selector.top_selector import _norm_side,_as_str_list,_clamp,_epoch_ms_to_iso,_stream_id_to_epoch_ms

def extract(path,name):
    tree=ast.parse(Path(path).read_text())
    cls=next(c for c in ast.walk(tree) if isinstance(c,ast.ClassDef)
        and any(getattr(x,'name',None)==name for x in c.body))
    method=copy.deepcopy(next(x for x in cls.body if getattr(x,'name',None)==name))
    method.decorator_list=[];method.returns=None
    for a in method.args.args+method.args.kwonlyargs:a.annotation=None
    m=ast.Module(body=[method],type_ignores=[]);ast.fix_missing_locations(m)
    return compile(m,'<actual_'+name+'>','exec')

signal={'symbol':'NEARUSDT','side_candidate':'long','producer_id':'heavy_engine',
 'event_id':'signal-event-aa','model_evaluation_id':'eval-abc123',
 'model_close_id':1794706000,'model_close_id_kind':'wallclock_bucket_180s'}
candidate={'candidate_id':'candidate-xyz','symbol':'NEARUSDT','interval':'3m',
 'side':'long','price':4.11,'score_total':.66,'model_score':.54,
 'raw':{'price':4.11,'whale_score':.05}, 'reason_codes':[],
 'whale_score':.05}
candidate.update(candidate_parent(signal,'signals_stream_long1','1794706000000-1'))
assert candidate_intent_parent(candidate=candidate,candidate_stream='candidates_stream_long1')=={}
a=dict(candidate,_source_stream_id='1794706001000-0')
parent=candidate_intent_parent(candidate=a,candidate_stream='candidates_stream_long1')
assert parent['source_candidate_id']=='candidate-xyz'
assert parent['source_candidate_stream_id']=='1794706001000-0'
assert parent['parent_signal_event_id']=='signal-event-aa'
assert parent['model_evaluation_id']=='eval-abc123'
assert parent['parent_trace_id']==candidate['parent_trace_id']
assert parent['model_close_id']==1794706000
# Strict no inference from score / timestamps. Partially missing Stage6
# provenance can still identify candidate origin, never fabricate MODEL link.
incomplete=dict(a);incomplete.pop('model_evaluation_id')
only_candidate=candidate_intent_parent(candidate=incomplete,candidate_stream='candidates_stream_long1')
assert set(only_candidate)=={'source_candidate_id','source_candidate_stream','source_candidate_stream_id'}
corrupt=dict(a,parent_trace_id='bad')
assert 'parent_trace_id' not in candidate_intent_parent(candidate=corrupt,candidate_stream='candidates_stream_long1')
for bad in ({},dict(a,_source_stream_id='missing'),dict(a,candidate_id=None),
            dict(a,symbol='INJUSDT')):
    assert not candidate_intent_parent(candidate=bad,candidate_stream='candidates_stream_long1')

scope=dict(_norm_side=_norm_side,_as_str_list=_as_str_list,_clamp=_clamp,
           _epoch_ms_to_iso=_epoch_ms_to_iso,_stream_id_to_epoch_ms=_stream_id_to_epoch_ms,
           _safe_float=_safe_float,os=os,json=json,_now_utc_iso=_now_utc_iso,
           time=__import__('time'))
exec(extract('orchestration/selector/top_selector.py','_normalize_candidate'),scope)
class Selector: pass
selector=Selector()
candidate_normalized=scope['_normalize_candidate'](selector,candidate,'1794706001000-0')
assert candidate_normalized['candidate_id']==candidate['candidate_id']
assert candidate_normalized['parent_trace_id']==candidate['parent_trace_id']
assert candidate_normalized['model_evaluation_id']==candidate['model_evaluation_id']
# Actual TopSelector selection adds _source_stream_id (candidate stream).
candidate_normalized['_source_stream_id']='1794706001000-0'

class Sink:
    def __init__(self):self.records=[]
    def xadd(self,stream,data,**kwargs):
        payload=json.loads(data['json'])
        self.records.append((stream,payload))
        return '1794706003000-0'
class Master:
    publish_allowed=True
    _last_published_source_id=None
    _last_publish_ts=0.0
    publish_cooldown_sec=0.0
    require_price=True
    out_stream='trade_intents_stream_long1'
    r=Sink()
    def _intent_price_for_publish(self,it):return it.price

exec(extract('orchestration/executor/master_executor.py','_publish_intents'),scope)
master=Master()
trade=TradeIntent(intent_id='intent-test',ts_utc='2026-11-14T19:06:12+03:00',
    symbol='NEARUSDT',interval='3m',side='long',price=4.11,score=.66,
    reasons=[],risk_tags=[],raw=candidate_normalized)
with patch.dict(os.environ,{'CANDIDATES_STREAM':'candidates_stream_long1'}):
    result=scope['_publish_intents'](master,'1794706002000-0',[trade])
assert result=='1794706003000-0'
stream,batch=master.r.records[0]
assert stream=='trade_intents_stream_long1'
assert batch['source_top5_id']=='1794706002000-0'
intent=batch['items'][0]
assert intent['intent_id']=='intent-test'
assert intent['source_candidate_id']==candidate['candidate_id']
assert intent['source_candidate_stream_id']=='1794706001000-0'
assert intent['parent_signal_event_id']==signal['event_id']
assert intent['model_evaluation_id']==signal['model_evaluation_id']
assert intent['parent_trace_id']==candidate['parent_trace_id']
assert intent['model_close_id_kind']=='wallclock_bucket_180s'
assert intent['price']==4.11 and intent['score']==.66
# Legacy candidate may still carry exact candidate id and source, not model.
trade_legacy=TradeIntent(**dict(trade.__dict__,intent_id='legacy-intent',raw=incomplete))
trade_legacy.raw['_source_stream_id']='1794706001000-1'
master2=Master();master2.r=Sink()
with patch.dict(os.environ,{'CANDIDATES_STREAM':'candidates_stream_long1'}):
    scope['_publish_intents'](master2,'1794706002001-0',[trade_legacy])
legacy=master2.r.records[0][1]['items'][0]
assert legacy['source_candidate_id']=='candidate-xyz'
assert 'parent_signal_event_id' not in legacy and 'model_evaluation_id' not in legacy
print(json.dumps({'actual_TopSelector_normalizer':True,
 'actual_MasterExecutor_trade_intent_publisher':True,
 'top5_transport_id_retained':True,
 'candidate_transport_id_exact':True,
 'parent_signal_and_model_explicit':True,
 'legacy_no_model_identity_invented':True,
 'price_and_score_unchanged':True,
 'no_redis_or_exchange_calls':True,'result':'PASS'},sort_keys=True))
