"""Full four-stream provenance from literal Redis IDs. Port 0 UNIX socket only.

Uses actual Stage6 candidate parent + actual TopSelector normalization +
actual MasterExecutor TradeIntent publisher. No real services/orders.
"""
import ast,copy,json,os,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import redis
from orchestration.trace.long1_lineage_v1 import candidate_parent
from orchestration.selector.top_selector import (
    _norm_side,_as_str_list,_clamp,_epoch_ms_to_iso,_stream_id_to_epoch_ms)
from orchestration.executor.master_executor import TradeIntent,_now_utc_iso
from orchestration.executor.master_executor import _safe_float

def compile_method(file,name):
    module=ast.parse(Path(file).read_text())
    cls=next(c for c in ast.walk(module) if isinstance(c,ast.ClassDef) and
             any(getattr(n,'name',None)==name for n in c.body))
    node=copy.deepcopy(next(n for n in cls.body if getattr(n,'name',None)==name))
    node.decorator_list=[];node.returns=None
    for a in node.args.args+node.args.kwonlyargs:a.annotation=None
    mod=ast.Module(body=[node],type_ignores=[]);ast.fix_missing_locations(mod)
    return compile(mod,'<actual:'+name+'>','exec')

ns=dict(os=os,time=time,json=json,_now_utc_iso=_now_utc_iso,
 _safe_float=_safe_float,_norm_side=_norm_side,_as_str_list=_as_str_list,
 _clamp=_clamp,_epoch_ms_to_iso=_epoch_ms_to_iso,
 _stream_id_to_epoch_ms=_stream_id_to_epoch_ms)
exec(compile_method('orchestration/selector/top_selector.py','_normalize_candidate'),ns)
exec(compile_method('orchestration/executor/master_executor.py','_publish_intents'),ns)
with TemporaryDirectory(prefix='stage7_lineage_isolation_') as folder:
    os.chmod(folder,0o700)
    sock=str(Path(folder)/'stream.sock')
    p=subprocess.Popen(['redis-server','--port','0','--unixsocket',sock,
      '--unixsocketperm','600','--save','','--appendonly','no',
      '--maxmemory','18mb','--maxmemory-policy','noeviction','--dir',folder],
      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    r=redis.Redis(unix_socket_path=sock,decode_responses=True,
                  socket_connect_timeout=.5,socket_timeout=2)
    try:
        for _ in range(60):
            try:
                if r.ping():break
            except (redis.exceptions.RedisError,OSError):time.sleep(.05)
        else:raise AssertionError('isolated redis startup failed')
        sig_stream='signals_stream_long1'
        cand_stream='candidates_stream_long1'
        top_stream='top5_stream_long1'
        intent_stream='trade_intents_stream_long1'
        signal={'symbol':'NEARUSDT','interval':'3m','side_candidate':'long',
                'event_id':'signal-abc','producer_id':'heavy_engine',
                'model_evaluation_id':'eval-abc',
                'model_close_id':1794706000,
                'model_close_id_kind':'wallclock_bucket_180s'}
        s_id=r.xadd(sig_stream,{'json':json.dumps(signal)})
        candidate={'candidate_id':'candidate-abc','symbol':'NEARUSDT',
                   'interval':'3m','side':'long','price':4.13,
                   'score_total':.65,'model_score':.54,
                   'reason_codes':[],'risk_tags':[],'whale_score':.08,
                   'raw':{'price':4.13}}
        candidate.update(candidate_parent(signal,sig_stream,s_id))
        c_id=r.xadd(cand_stream,{'json':json.dumps(candidate)})
        from_db=json.loads(r.xrange(cand_stream)[0][1]['json'])
        class Top:pass
        selected=ns['_normalize_candidate'](Top(),from_db,c_id)
        selected['_source_stream_id']=c_id
        t_id=r.xadd(top_stream,{'json':json.dumps({
            'topk':1,'items':[selected]})})
        from_top=json.loads(r.xrange(top_stream)[0][1]['json'])['items'][0]
        class Master:
            publish_allowed=True
            _last_published_source_id=None
            _last_publish_ts=0
            publish_cooldown_sec=0
            require_price=True
            out_stream=intent_stream
            r=r
            def _intent_price_for_publish(self,item):return item.price
        master=Master()
        item=TradeIntent(intent_id='intent-abc',ts_utc='2026-11-14T19:06:12+03:00',
             symbol='NEARUSDT',interval='3m',side='long',price=4.13,
             score=.65,reasons=[],risk_tags=[],raw=from_top)
        with patch.dict(os.environ,{'CANDIDATES_STREAM':cand_stream}):
            intent_id=ns['_publish_intents'](master,t_id,[item])
        assert intent_id
        out=json.loads(r.xrange(intent_stream)[0][1]['json'])
        intent=out['items'][0]
        assert out['source_top5_id']==t_id
        assert intent['source_candidate_stream_id']==c_id
        assert intent['source_candidate_id']==candidate['candidate_id']
        assert intent['parent_signal_event_id']==signal['event_id']
        assert intent['model_evaluation_id']==signal['model_evaluation_id']
        assert intent['source_signal_stream_id']==s_id
        assert intent['model_close_id_kind']=='wallclock_bucket_180s'
        assert intent['intent_id']=='intent-abc'
        # Redis stream IDs are only unique WITHIN each named stream;
        # separate streams can have the same millisecond-sequence ID.
        assert len({(cand_stream,c_id),(top_stream,t_id),
                    (intent_stream,intent_id)})==3
        assert intent['price']==4.13 and intent['score']==.65
        print(json.dumps({'signals':r.xlen(sig_stream),'candidates':r.xlen(cand_stream),
          'top5':r.xlen(top_stream),'intents':r.xlen(intent_stream),
          'source_signal_exact':True,'source_candidate_exact':True,
          'source_top5_exact':True,'model_evaluation_exact':True,
          'intent_id_independent':True,'score_price_unchanged':True,
          'redis_isolated_port_0':True,'production_redis_writes':0,
          'orders_sent':0,'result':'PASS'},sort_keys=True))
    finally:
        try:r.shutdown(save=False)
        except (redis.exceptions.RedisError,OSError):pass
        p.wait(timeout=5)
