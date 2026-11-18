"""Real IntentBridge + PENDING AST + position shadow/OUTCOME, isolated Redis.

Actual order placement, central LIVE Risk Master, Binance POST are NOT called.
Validates trace identity survival and no origin impersonation.
"""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import ast,copy,json,os,subprocess,time
from unittest.mock import patch
import redis
from orchestration.executor.intent_bridge import IntentBridge
from orchestration.trace.long1_execution_lineage_v1 import compact,preserve_pending_origin
from monitoring.okx_oi_shadow_context import mark_position_open_shadow,emit_position_outcome_shadow

def boot(folder):
    sock=str(Path(folder)/'trace.sock')
    proc=subprocess.Popen(['redis-server','--port','0','--unixsocket',sock,
      '--unixsocketperm','600','--save','','--appendonly','no',
      '--maxmemory','16mb','--maxmemory-policy','noeviction','--dir',folder],
      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=redis.Redis(unix_socket_path=sock,decode_responses=True,
      socket_connect_timeout=.5,socket_timeout=2)
    for _ in range(70):
        try:
            if client.ping():return proc,client
        except (redis.exceptions.RedisError,OSError):time.sleep(.05)
    proc.terminate();proc.wait(timeout=5)
    raise RuntimeError('isolated redis unavailable')

def extract_method(path,name):
    tree=ast.parse(Path(path).read_text())
    cls=next(x for x in ast.walk(tree) if isinstance(x,ast.ClassDef)
      and any(getattr(y,'name',None)==name for y in x.body))
    m=copy.deepcopy(next(x for x in cls.body if getattr(x,'name',None)==name))
    m.decorator_list=[];m.returns=None
    for a in m.args.args+m.args.kwonlyargs:a.annotation=None
    block=ast.Module(body=[m],type_ignores=[]);ast.fix_missing_locations(block)
    return compile(block,'<actual:'+name+'>','exec')

with TemporaryDirectory(prefix='long1_stage8_') as folder:
    os.chmod(folder,0o700)
    proc,r=boot(folder)
    try:
        source={
         'intent_id':'intent-first','symbol':'NEARUSDT','side':'long',
         'interval':'3m','price':4.11,'score':.55,
         'source_candidate_id':'candidate-1',
         'source_candidate_stream':'candidates_stream_long1',
         'source_candidate_stream_id':'1794706001000-0',
         'parent_signal_event_id':'signal-1',
         'source_signal_stream':'signals_stream_long1',
         'source_signal_stream_id':'1794706000000-0',
         'parent_trace_id':'long1:abc123',
         'model_evaluation_id':'eval-1','model_close_id':1794706000,
         'model_close_id_kind':'wallclock_bucket_180s'}
        b=IntentBridge.__new__(IntentBridge)
        b.publish_allowed=True;b.require_price=True
        b.pass_raw=False;b.raw_max_chars=1000
        b.out_stream='exec_events_stream_long1'
        b.out_maxlen=30;b.out_approx=False;b.r=r
        published=b._publish_exec('1794706002000-0',source)
        assert published
        exec_batch=json.loads(r.xrange(b.out_stream)[0][1]['json'])
        assert exec_batch['source_intents_id']=='1794706002000-0'
        item=exec_batch['items'][0]
        assert item['intent_id']=='intent-first'
        assert item['source_candidate_id']=='candidate-1'
        assert item['parent_signal_event_id']=='signal-1'
        assert item['model_evaluation_id']=='eval-1'
        assert item['source_candidate_stream_id']=='1794706001000-0'
        assert 'raw' not in item # BRIDGE_PASS_RAW=0

        # Actual LONG1 _store_long_pending_candidate, no real executor init.
        ns={'time':time}
        exec(extract_method('core/trade_executor.py',
                  '_store_long_pending_candidate'),ns)
        class Fake:
            long_pending_by_symbol={}
            _normalize_long_entry_decision=lambda self,d:dict(d)
            _get_long_candle_id=lambda self,interval,created:1234567
        fake=Fake()
        pending=ns['_store_long_pending_candidate'](
            fake,symbol='NEARUSDT',side='long',
            decision={'action':'pending','reason':'context_recheck'},
            interval='1m',extra=item)
        assert pending['extra']['pending_origin_intent_id']=='intent-first'
        attempt=pending['extra']['pending_attempt_id']
        assert attempt.startswith('pending-')
        assert pending['extra']['pending_recheck_count']==0
        next_signal=dict(item,intent_id='intent-second',
              model_evaluation_id='eval-new',source_candidate_id='candidate-2')
        merged=preserve_pending_origin(pending['extra'],next_signal)
        assert merged['pending_origin_intent_id']=='intent-first'
        assert merged['pending_attempt_id']==attempt
        assert merged['pending_recheck_intent_id']=='intent-second'
        assert merged['intent_id']=='intent-second'
        assert merged['pending_recheck_count']==1
        assert merged['pending_origin_lineage']['source_candidate_id']=='candidate-1'
        assert merged['source_candidate_id']=='candidate-2'
        repeat=preserve_pending_origin(merged,dict(next_signal,intent_id='intent-third'))
        assert repeat['pending_recheck_count']==2
        assert repeat['pending_attempt_id']==attempt
        assert repeat['pending_origin_intent_id']=='intent-first'
        assert repeat['pending_recheck_intent_id']=='intent-third'

        assert mark_position_open_shadow(r,symbol='NEARUSDT',side='long',
          entry_price=4.11,signal_score=.55,
          intent_id='intent-third',qty=2,notional=8.22,leverage=3,
          open_order_id='synthetic-only',trace_lineage=repeat)
        opened=json.loads(r.xrevrange('shadow:telemetry:position_open',count=1)[0][1]['json'])
        assert opened['trace_lineage']['source_candidate_id']=='candidate-2'
        assert opened['pending_origin_lineage']['source_candidate_id']=='candidate-1'
        assert opened['pending_origin_intent_id']=='intent-first'
        assert opened['pending_recheck_intent_id']=='intent-third'
        assert opened['pending_attempt_id']==attempt
        assert emit_position_outcome_shadow(r,symbol='NEARUSDT',side='long',
          entry_price=4.11,close_price=4.14,pnl_pct=.0073,
          reason='synthetic_test',qty=2,leverage=3,
          close_order_id='synthetic-close')
        closed=json.loads(r.xrevrange('shadow:telemetry:position_outcome',
                                     count=1)[0][1]['json'])
        assert closed['trace_lineage']==opened['trace_lineage']
        assert closed['pending_attempt_id']==attempt
        assert closed['pending_origin_intent_id']=='intent-first'
        assert closed['pending_recheck_intent_id']=='intent-third'
        assert closed['shadow_only'] is True
        assert closed['funding_cost_source']=='not_available'
        assert 'net_roi_pct_est' in closed
        # The recorded order ID is fixture text, not a real exchange fill.
        assert closed['close_order_id']=='synthetic-close'
        print(json.dumps({
         'actual_IntentBridge_payload_pass_raw_off':True,
         'actual_TradeExecutor_PENDING_store_AST':True,
         'original_vs_recheck_intents_distinct':True,
         'pending_attempt_stable_across_rechecks':True,
         'shadow_open_lineage_survives_to_outcome':True,
         'fee_slippage_estimated_not_real_pnl':True,
         'mock_order_ids_not_verified':True,
         'real_binance_orders':0,'production_redis_writes':0,
         'live_order_authorized':False,'result':'PASS'},sort_keys=True))
    finally:
        try:r.shutdown(save=False)
        except (redis.exceptions.RedisError,OSError):pass
        proc.wait(timeout=5)
