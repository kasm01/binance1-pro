"""Stage6 AST-extract real HeavyEngine payload + real Aggregator candidate builder.

Pure/no process, service, Redis reads/writes, or exchange calls.
"""
from __future__ import annotations
import ast,copy,json,uuid
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from orchestration.trace.long1_lineage_v1 import (
    candidate_parent,decorate_model_signal,new_model_evaluation_id,
)
from research.trace.long1_trace_contract_v1 import trace_id_from_transport

def extract(file,classmethod):
    src=ast.parse(Path(file).read_text())
    cls=next(n for n in ast.walk(src) if isinstance(n,ast.ClassDef)
        and any(getattr(f,'name',None)==classmethod for f in n.body))
    fn=copy.deepcopy(next(x for x in cls.body if getattr(x,'name',None)==classmethod))
    fn.decorator_list=[];fn.returns=None
    for a in fn.args.args+fn.args.kwonlyargs:a.annotation=None
    m=ast.Module(body=[fn],type_ignores=[])
    ast.fix_missing_locations(m)
    return compile(m,'<real-source-'+classmethod+'>','exec')
scope=dict(Dict=dict,Any=object,Optional=__import__('typing').Optional,
           datetime=datetime,timezone=timezone,uuid=uuid)
exec(extract('main.py','_build_model_signal_event_payload'),scope)
build=scope['_build_model_signal_event_payload']
class Heavy:pass
payload=build(Heavy(),symbol='NEARUSDT',interval='3m',side='long',
 p_used=.557,p_single=.519,price=4.,atr_value=.04,
 whale_dir='none',whale_score=.3,signal_source='HYBRID',
 model_evaluation_id='eval-'+'d'*32,model_close_id=1794706000)
assert payload['model_evaluation_id']=='eval-'+'d'*32
assert payload['model_close_id']==1794706000
assert payload['model_close_id_kind']=='wallclock_bucket_180s'
assert payload['model_score']==.557
assert payload['event_id'] and not payload.get('parent_trace_id')
# Shadow and production share one model EVAL, but own separate Signal event IDs.
shadow=build(Heavy(),symbol='NEARUSDT',interval='3m',side='long',
 p_used=.557,p_single=.519,price=4.,atr_value=.04,
 whale_dir='none',whale_score=.3,signal_source='HYBRID',
 model_evaluation_id=payload['model_evaluation_id'],
 model_close_id=payload['model_close_id'],shadow=True)
assert shadow['model_evaluation_id']==payload['model_evaluation_id']
assert shadow['event_id']!=payload['event_id']
# No invented lineage for legacy events, invalid or aliased event IDs.
old=build(Heavy(),symbol='NEARUSDT',interval='3m',side='short',
 p_used=.41,p_single=.5,price=4.,atr_value=.04,whale_dir='none',
 whale_score=.1,signal_source='HYBRID')
assert 'model_evaluation_id' not in old and 'model_close_id' not in old
assert abs(old['model_score']-.59)<1e-12
assert 'model_evaluation_id' not in decorate_model_signal(old,model_evaluation_id='bad id')
assert 'model_close_id' not in decorate_model_signal(old,model_close_id='1794706000')
assert new_model_evaluation_id()!=new_model_evaluation_id()

from orchestration.aggregator.aggregator import _safe_float,_clamp01
scope.update(_safe_float=_safe_float,_clamp01=_clamp01)
exec(extract('orchestration/aggregator/aggregator.py','_build_candidate_payload'),scope)
class AGG:pass
a=AGG()
a.include_raw=False
a.bus=SimpleNamespace(signals_stream='signals_stream_long1')
evt=dict(payload, _source_stream_id='1794706000000-1',_score_total=.654,
         _reason_codes=['model'],_risk_tags=[],confidence_available=False,
         spread_available=False,liq_score_available=False,
         dedup_key='NEARUSDT|3m|long')
result=scope['_build_candidate_payload'](a,evt)
assert result['parent_signal_event_id']==payload['event_id']
assert result['source_signal_stream']=='signals_stream_long1'
assert result['source_signal_stream_id']=='1794706000000-1'
assert result['parent_trace_id']==trace_id_from_transport(
    'signals_stream_long1','1794706000000-1')
assert result['model_evaluation_id']==payload['model_evaluation_id']
assert result['model_close_id']==payload['model_close_id']
assert result['model_close_id_kind']=='wallclock_bucket_180s'
assert result['candidate_id']!=result['parent_signal_event_id']
assert result['model_score']==payload['model_score']
assert result['score_total']==.654
assert result['raw'].get('event_id') is None
assert result['raw'].get('model_close_id') is None
# Other symbols must not inherit LONG1 identifiers.
other=dict(evt,symbol='BTCUSDT')
result_other=scope['_build_candidate_payload'](a,other)
assert 'parent_signal_event_id' not in result_other
assert 'parent_trace_id' not in result_other
# Invalid provenance is omitted; never invent a model link by matching scores.
for change in (
    {'_source_stream_id':'not-a-redis-id'},
    {'event_id':'bad event id'},
    {'model_close_id':1794706000,'model_close_id_kind':'actual_candle'},
    {'model_evaluation_id':'wrong eval id'},
    {'producer_id':'external_stub'},
):
 test=dict(evt,**change)
 output=scope['_build_candidate_payload'](a,test)
 if '_source_stream_id' in change:
  assert 'parent_trace_id' not in output and 'parent_signal_event_id' not in output
 elif 'event_id' in change:
  assert 'parent_signal_event_id' not in output
 elif 'model_close_id_kind' in change:
  assert 'model_close_id' not in output
 else:
  assert 'model_evaluation_id' not in output
# Raw enabled has same top-level source, and preserves existing fields.
a.include_raw=True
raw_result=scope['_build_candidate_payload'](a,evt)
assert raw_result['parent_signal_event_id']==result['parent_signal_event_id']
assert raw_result['raw']['event_id']==payload['event_id']
print(json.dumps({'real_HeavyEngine_producer_AST':True,
 'real_Aggregator_candidate_AST':True,
 'raw_disabled_parent_survives':True,'legacy_no_identity_invented':True,
 'shadow_production_distinct_event_same_evaluation':True,
 'legacy_scores_unchanged':True,'other_symbols_not_attributed_to_LONG1':True,
 'upstream_exact_signal_source_provenance':True,
 'model_close_id_kind':'wallclock_bucket_180s_NOT_candle_close',
 'external_redis_writes':0,'real_exchange_orders':0,'status':'PASS'},sort_keys=True))
