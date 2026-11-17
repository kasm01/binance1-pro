"""Actual LONG1 builder, actual Redis stream ID, normalizer and aggregator.

Isolated socket/port=0, no production Redis, no service start, no order.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import ast,copy,json,os,subprocess,time,uuid
from datetime import datetime,timezone
import redis
from orchestration.schemas.events import SignalEvent
from orchestration.aggregator.aggregator import _safe_float,_clamp01,_norm_side_candidate,_norm_whale_dir
from orchestration.trace.long1_lineage_v1 import MODEL_CLOSE_KIND
from research.trace.long1_trace_contract_v1 import trace_id_from_transport

def method(path,name):
 tree=ast.parse(Path(path).read_text())
 cls=next(c for c in ast.walk(tree) if isinstance(c,ast.ClassDef)
      and any(getattr(m,'name',None)==name for m in c.body))
 n=copy.deepcopy(next(m for m in cls.body if getattr(m,'name',None)==name))
 n.decorator_list=[];n.returns=None
 for a in n.args.args+n.args.kwonlyargs:a.annotation=None
 node=ast.Module(body=[n],type_ignores=[]);ast.fix_missing_locations(node)
 return compile(node,'<real-'+name+'>','exec')
ns=dict(datetime=datetime,timezone=timezone,uuid=uuid,
        _safe_float=_safe_float,_clamp01=_clamp01,
        _norm_side_candidate=_norm_side_candidate,_norm_whale_dir=_norm_whale_dir)
exec(method('main.py','_build_model_signal_event_payload'),ns)
exec(method('main.py','_publish_model_signal_production'),ns)
exec(method('orchestration/aggregator/aggregator.py','_normalize_event'),ns)
exec(method('orchestration/aggregator/aggregator.py','_build_candidate_payload'),ns)
with TemporaryDirectory(prefix='stage6_long1_lineage_') as temp:
 os.chmod(temp,0o700)
 sock=str(Path(temp)/'trace.sock')
 proc=subprocess.Popen(['redis-server','--port','0','--unixsocket',sock,
       '--unixsocketperm','600','--save','','--appendonly','no',
       '--maxmemory','16mb','--maxmemory-policy','noeviction','--dir',temp],
       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 r=redis.Redis(unix_socket_path=sock,decode_responses=True,
       socket_connect_timeout=.5,socket_timeout=1.5)
 try:
  for _ in range(75):
   try:
    if r.ping():break
   except (redis.exceptions.RedisError,OSError):time.sleep(.05)
  else:raise RuntimeError('isolated_redis_unavailable')
  stream='signals_stream_long1_test'
  cand_stream='candidates_stream_long1_test'
  class SignalBus:
   signals_stream=stream
   def publish_signal(self,payload):
    return r.xadd(stream,{'json':json.dumps(payload,ensure_ascii=False)},maxlen=200)
  class Heavy:
   _build_model_signal_event_payload=ns['_build_model_signal_event_payload']
  heavy=Heavy();heavy._model_signal_bus=SignalBus()
  ns.update(system_logger=None,RedisBus=None)
  sid=ns['_publish_model_signal_production'](
      heavy,symbol='NEARUSDT',interval='3m',side='long',
      p_used=.552,p_single=.52,price=4,atr_value=.04,
      whale_dir='none',whale_score=.15,signal_source='HYBRID',
      model_evaluation_id='eval-'+'a'*32,model_close_id=1794706000)
  assert sid
  signal=json.loads(r.xrange(stream)[0][1]['json'])
  assert signal['event_id'] and signal['model_evaluation_id']=='eval-'+'a'*32
  assert signal['model_close_id_kind']==MODEL_CLOSE_KIND
  assert signal['model_close_id']==1794706000
  assert 'parent_signal_event_id' not in signal
  class Agg:pass
  agg=Agg();agg.include_raw=False
  agg.bus=SignalBus()
  normalized=ns['_normalize_event'](agg,sid,SignalEvent.normalize(signal))
  normalized.update(_score_total=.65,_reason_codes=['ok'],_risk_tags=[])
  candidate=ns['_build_candidate_payload'](agg,normalized)
  assert candidate['parent_signal_event_id']==signal['event_id']
  assert candidate['source_signal_stream_id']==sid
  assert candidate['parent_trace_id']==trace_id_from_transport(stream,sid)
  assert candidate['model_evaluation_id']==signal['model_evaluation_id']
  assert candidate['model_close_id']==signal['model_close_id']
  assert candidate['model_close_id_kind']==MODEL_CLOSE_KIND
  assert candidate['raw']['meta'] and 'event_id' not in candidate['raw']
  assert abs(candidate['model_score']-.552)<1e-10
  assert abs(candidate['score_total']-.65)<1e-10
  candidate_id=r.xadd(cand_stream,{'json':json.dumps(candidate)},maxlen=200)
  persisted=json.loads(r.xrange(cand_stream)[0][1]['json'])
  assert persisted['candidate_id']==candidate['candidate_id']
  assert persisted['source_signal_stream_id']==sid
  assert persisted['parent_signal_event_id']==signal['event_id']
  assert persisted['parent_trace_id']==candidate['parent_trace_id']
  assert persisted['candidate_id']!=signal['event_id']
  assert candidate_id!=sid
  print(json.dumps({'real_HeavyEngine_publish_method':True,
     'real_Redis_XADD_signal_and_candidate':True,
     'real_Aggregator_normalization_and_candidate':True,
     'source_signal_stream_id_exact':True,
     'source_event_id_exact':True,
     'model_evaluation_id_exact':True,
     'raw_disabled':True,
     'model_close_id_kind':'wallclock_bucket_180s',
     'score_unchanged':True,'separate_test_redis_only':True,
     'order_calls':0,'production_redis_writes':0,'result':'PASS'},sort_keys=True))
 finally:
  try:r.shutdown(save=False)
  except (redis.exceptions.RedisError,OSError):pass
  proc.wait(timeout=5)
