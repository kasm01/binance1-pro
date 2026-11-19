"""Run ACTUAL LONG1 Contra Guard against isolated Redis + mocked Binance GET.

Exercise veto stale/no-new-intent/3m recovery/5m recovery, observer failures,
and completed 5m closed-bar identity; never touch production Redis or Binance.
"""
from __future__ import annotations
from unittest.mock import patch
from datetime import datetime,timezone
import tempfile,subprocess,time,os,json
from pathlib import Path
import redis
from core.trade_executor import TradeExecutor
from orchestration.trace.long1_entry_decision_audit_v1 import STREAM,prepare
from core.long_contra_guard import five_minute_recovered
NOW=1794708000000
def snapshots(m3=-.002,up=0.0,flow15=-.15,flow60=-.2,ret=-.001,candle=None):
 candle=NOW-240000 if candle is None else candle
 return ({'status':'OK','observed_at_ms':NOW-900,'derived':{
  'taker_flow15_completed':flow15,'taker_flow60_completed':flow60}},
 {'status':'OK','observed_at_ms':NOW-800,
  'research_3m_close_time_ms':candle,
  'research_m3_ret1':ret,'research_m3_ret1_mean3':m3,
  'research_m3_up_frac3':up})
def bars5(recovered):
 # aligned UTC full 5m candle close times; after original pending creation
 first=(NOW//300000)*300000-600000
 vals=[]
 for k,p in enumerate((3.0,3.01 if recovered else 2.99)):
  start=first+k*300000
  vals.append([start,'','',None,str(p),None,start+300000-1])
 return vals
def boot(path):
 sock=path+'/redis.sock'
 proc=subprocess.Popen(['redis-server','--port','0','--unixsocket',sock,'--unixsocketperm','600',
 '--save','','--appendonly','no','--dir',path],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 r=redis.Redis(unix_socket_path=sock,decode_responses=True,socket_timeout=1,socket_connect_timeout=.2)
 for _ in range(60):
  try:
   if r.ping():return proc,r
  except Exception:time.sleep(.05)
 raise AssertionError('no isolated redis')
def put(r,flow15=-.15,flow60=-.2,m3=-.002,up=0,ret=-.001,candle=None):
 a,b=snapshots(m3,up,flow15,flow60,ret,candle)
 r.set('shadow:market_context:combined:NEARUSDT',json.dumps(a))
 r.set('shadow:market_context:binance_structure:NEARUSDT',json.dumps(b))
with tempfile.TemporaryDirectory(prefix='long1_stage12_') as directory:
 os.chmod(directory,0o700)
 proc,r=boot(directory)
 try:
  t=TradeExecutor.__new__(TradeExecutor)
  t.redis=r;t.logger=None;t._long_contra_context_pending={}
  root={'intent_id':'origin-1','symbol':'NEARUSDT',
    'model_evaluation_id':'model-abc','parent_trace_id':'long1:correct'}
  def call(intent):
   return t._long_contra_context_gate(symbol='NEARUSDT',side='long',extra=intent)
  with patch.dict(os.environ,{'LONG_CONTRA_GUARD_ENABLE':'1',
    'LONG1_ENTRY_DECISION_TRACE_SHADOW_ENABLE':'1'}),patch('core.trade_executor.time.time',return_value=NOW/1000):
   put(r)
   assert call(root) is False
   assert r.xlen(STREAM)==1
   orig=t._long_contra_context_pending['NEARUSDT']
   assert orig['origin_intent']=='origin-1'
   # Simulate pending persisted across completed 5m bars: the mocked
   # current observation time is NOW, origin happened earlier.
   orig['created_ms']=NOW-480000
   # same intent even after market recovery MUST NOT authorize
   put(r,flow15=.02,flow60=.01,m3=.005,up=1,ret=.003,candle=orig['origin_candle_ms']+180000)
   assert call(root) is False
   newer=dict(root,intent_id='new-intent')
   put(r,flow15=-.01,flow60=.02,m3=.005,up=1,ret=.003,candle=orig['origin_candle_ms']+180000)
   assert call(newer) is False
   put(r,flow15=.02,flow60=.01,m3=.005,up=1,ret=.003,candle=orig['origin_candle_ms']+180000)
   class Dummy:
    def __init__(self,rows):self.rows=rows
    def json(self):return self.rows
   with patch('requests.get',return_value=Dummy(bars5(False))):
    assert call(newer) is False
   # second 5m candle finally above previous, after original created
   with patch('requests.get',return_value=Dummy(bars5(True))):
    assert call(newer) is True
   assert not t._long_contra_context_pending
   assert r.xlen(STREAM)>=4
   items=[json.loads(fields['json']) for _,fields in r.xrange(STREAM)]
   last=items[-1]
   assert last['stage']=='contra_trend' and last['action']=='ready'
   assert last['context_valid_asof'] and last['five_minute_recovered']
   assert last['fresh_intent_verified']
   assert last['market_context_3m_5m_recovery_verified']
   assert not last['order_authority']
   assert last['intent_id']=='new-intent'
   assert last['lineage']['model_evaluation_id']=='model-abc'
   # no prior contra pending -> gate ready, but not proof 5m recovery
   t._long_contra_context_pending={}
   assert call(newer) is True
   item=json.loads(r.xrevrange(STREAM,count=1)[0][1]['json'])
   assert item['action']=='ready' and not item['market_context_3m_5m_recovery_verified']
   # observer exceptions MUST NOT change decision.
   t._long1_trace_decision_shadow=lambda **k:(_ for _ in ()).throw(RuntimeError('observer failure'))
   put(r)
   assert call(root) is False
   assert r.xlen(STREAM)>=5
  with patch.dict(os.environ,{'LONG_CONTRA_GUARD_ENABLE':'1',
   'LONG1_ENTRY_DECISION_TRACE_SHADOW_ENABLE':'0'}),patch('core.trade_executor.time.time',return_value=NOW/1000):
   count=r.xlen(STREAM)
   put(r)
   assert call(root) is False
   assert r.xlen(STREAM)==count
  print(json.dumps({'status':'PASS','shadow_events':count,
   'fresh_intent_required':True,'completed_5m_verified':True,
   'observer_failure_does_not_change_veto':True,'live_orders':0,
   'production_redis_writes':0},sort_keys=True))
 finally:
  proc.terminate();proc.wait(timeout=5)
