"""Isolated-Redis REAL LONG1 executor hook + event dedupe; no prod data writes."""
from __future__ import annotations
import copy,json,os,subprocess,tempfile,time
from pathlib import Path
from unittest.mock import patch
import redis
from core.trade_executor import TradeExecutor
from orchestration.trace.long1_entry_decision_audit_v1 import STREAM,emit,prepare
from orchestration.trace.long1_execution_lineage_v1 import preserve_pending_origin
def boot(folder):
 sock=str(Path(folder)/'redis.sock')
 proc=subprocess.Popen(['redis-server','--port','0','--unixsocket',sock,
   '--unixsocketperm','600','--save','','--appendonly','no','--dir',folder],
   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 c=redis.Redis(unix_socket_path=sock,decode_responses=True,
  socket_connect_timeout=.4,socket_timeout=2)
 for _ in range(80):
  try:
   if c.ping():return proc,c
  except (redis.RedisError,OSError):time.sleep(.05)
 proc.terminate();proc.wait(timeout=4)
 raise AssertionError('no isolated socket')
def check():
 with tempfile.TemporaryDirectory(prefix='long1_shadow_stage11_') as folder:
  os.chmod(folder,0o700)
  proc,r=boot(folder)
  try:
   ex=TradeExecutor.__new__(TradeExecutor)
   ex.redis=r;ex.long_pending_by_symbol={}
   ex.logger=None
   ex._normalize_long_entry_decision=lambda d:dict(d)
   ex._get_long_candle_id=lambda itv,ts=None:1000
   origin={'symbol':'NEARUSDT','side':'long','intent_id':'intent-origin',
      'source_candidate_id':'candidate-x',
      'source_candidate_stream':'candidates_stream_long1',
      'source_candidate_stream_id':'1794706001000-0',
      'parent_signal_event_id':'signal-uuid',
      'source_signal_stream':'signals_stream_long1',
      'source_signal_stream_id':'1794706000000-0',
      'parent_trace_id':'long1:traceorigin',
      'model_evaluation_id':'eval-id'}
   decision={'action':'pending','reason':'sniper_window_early','retryable':True,
      'score':.52,'required_score':.50,'progress':.02,
      'details':{'pending_kind':'early'}}
   # Environment default OFF. Real pending state retained but NO new Redis writes.
   with patch.dict(os.environ,{'LONG1_ENTRY_DECISION_TRACE_SHADOW_ENABLE':'0'}):
    p=ex._store_long_pending_candidate(symbol='NEARUSDT',
       side='long',decision=decision,interval='1m',extra=origin)
    assert r.xlen(STREAM)==0
    assert p['extra']['pending_attempt_id'].startswith('pending-')
   ex.long_pending_by_symbol={}
   with patch.dict(os.environ,{'LONG1_ENTRY_DECISION_TRACE_SHADOW_ENABLE':'1'}):
    pending=ex._store_long_pending_candidate(symbol='NEARUSDT',
       side='long',decision=decision,interval='1m',extra=origin)
    attempt=pending['extra']['pending_attempt_id']
    assert r.xlen(STREAM)==1
    assert ex._dispatch_long_candidate_decision(decision)==decision
    ex._long1_trace_decision_shadow(stage='sniper',decision=decision,extra=origin)
    ex._long1_trace_decision_shadow(stage='sniper',decision=decision,extra=origin)
    assert r.xlen(STREAM)==2
    entry={'action':'open','reason':'entry_confirmation_ready',
      'score':.52,'required_score':.5,
      'details':{'entry_quality':.59,'body_ratio':.27,'retrace_ratio':.22,
      'entry_context_source':'asof-executor','entry_candle_interval':'1m'}}
    ex._long1_trace_decision_shadow(stage='entry_confirmation',decision=entry,extra=origin)
    assert r.xlen(STREAM)==3
    newer=dict(origin,intent_id='intent-recheck',model_evaluation_id='eval-new')
    merged=preserve_pending_origin(pending['extra'],newer)
    assert merged['pending_origin_intent_id']=='intent-origin'
    assert merged['pending_attempt_id']==attempt
    ex._long1_trace_decision_shadow(stage='pending_recheck',
      decision={'action':'wait','reason':'pending_recheck_wait'},extra=merged)
    ex._long1_trace_decision_shadow(stage='pending_recheck',
      decision={'action':'wait','reason':'pending_recheck_wait'},extra=merged)
    ex._long1_trace_decision_shadow(stage='pending_recheck',
      decision={'action':'ready','reason':'pending_recheck_ready'},extra=merged)
    assert r.xlen(STREAM)==5
    for _,entry in r.xrange(STREAM):
     event=json.loads(entry['json'])
     assert event['source']=='ACTUAL_EXECUTOR_DECISION'
     assert event['side']=='long' and event['symbol']=='NEARUSDT'
     assert event['advisory_only'] and not event['order_authority']
     assert not event['market_context_3m_5m_recovery_verified']
     assert not event['decision_candle_identity_verified']
    rows=[json.loads(x['json']) for _,x in r.xrange(STREAM)]
    assert [x['stage'] for x in rows]==[
     'pending_store','sniper','entry_confirmation','pending_recheck','pending_recheck']
    assert rows[0]['pending_attempt_id']==attempt
    assert rows[-1]['pending_origin_intent_id']=='intent-origin'
    assert rows[-1]['pending_recheck_intent_id']=='intent-recheck'
    assert rows[2]['metrics']['quality']==.59
    # Only LONG/NEAR is captured, never SHORT or any other symbol.
    ex._store_long_pending_candidate(symbol='INJUSDT',side='long',
      decision=decision,extra={'intent_id':'inj'})
    ex._store_long_pending_candidate(symbol='NEARUSDT',side='short',
      decision=decision,extra={'intent_id':'short'})
    assert r.xlen(STREAM)==5
    invalid=prepare(symbol='NEARUSDT',stage='sniper',
      decision={'action':'unknown'},extra=origin)
    assert invalid is None
    assert emit(redis_client=r,symbol='INJUSDT',stage='sniper',
      decision=decision,extra=origin) is False
    assert r.xlen(STREAM)==5
   # OFF again remains no new network or Redis work
   with patch.dict(os.environ,{'LONG1_ENTRY_DECISION_TRACE_SHADOW_ENABLE':'0'}):
    ex._long1_trace_decision_shadow(stage='sniper',
      decision={'action':'block','reason':'test-off'},extra=origin)
    assert r.xlen(STREAM)==5
   return 5
  finally:
   proc.terminate()
   proc.wait(timeout=5)
if __name__=='__main__':
 n=check()
 print(json.dumps({'status':'PASS','isolated_redis_events':n,
   'pending_origin_immutable':True,'deduped':True,
   'disabled_writes':0,'production_redis_writes':0,
   'real_exchange_orders':0},sort_keys=True))
