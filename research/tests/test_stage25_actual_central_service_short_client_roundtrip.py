"""Actual LONG central DRY service handler + actual SHORT CentralRiskClient.

Isolated unix-socket Redis, port=0. Never connects to production port 6379.
No Binance calls, no live service, no order submission. One consumer thread.
"""
from __future__ import annotations
import importlib.util,json,os,subprocess,threading,time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import redis
from scripts import central_risk_enforce_dry_service as service

SHORT_CLIENT=Path.home()/'binance1/orchestration/risk/central_risk_client.py'
spec=importlib.util.spec_from_file_location('short_central_client_stage25',SHORT_CLIENT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CentralRiskClient=module.CentralRiskClient

def boot(folder):
 sock=str(Path(folder)/'stage25.sock')
 proc=subprocess.Popen(['redis-server','--port','0','--unixsocket',sock,
      '--unixsocketperm','600','--save','','--appendonly','no','--daemonize','no',
      '--maxmemory','16mb','--maxmemory-policy','noeviction','--dir',folder],
      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 r=redis.Redis(unix_socket_path=sock,decode_responses=True,
     socket_connect_timeout=.5,socket_timeout=3)
 for _ in range(70):
  try:
   if r.ping():return proc,r
  except (redis.exceptions.RedisError,OSError):time.sleep(.06)
 proc.terminate();proc.wait(timeout=5)
 raise RuntimeError('isolated Redis unavailable')

with TemporaryDirectory(prefix='stage25_joint_roundtrip_') as folder:
 os.chmod(folder,0o700)
 proc,r=boot(folder)
 failures=[]
 shutdown=threading.Event()
 def consume():
  last='0-0'
  while not shutdown.is_set():
   try:
    chunks=r.xread({service.REQUEST_STREAM:last},count=10,block=250)
    for _,msgs in chunks:
     for mid,fields in msgs:
      last=mid
      request=json.loads(fields['json'])
      response=service._handle(r,request)
      service._response(r,request['request_id'],response)
   except Exception as exc:
    failures.append(type(exc).__name__)
    break
 worker=threading.Thread(target=consume,daemon=True)
 try:
  r.set(service.SNAPSHOT_KEY,json.dumps({
    'ts':time.time(),'exposure_health':{'status':'OK','freeze_new_entries':False},
    'account':{'mtm_equity':100},'portfolio_state':{
       'equity_peak':100,'mode':'NORMAL','recovery_successes':0},
    'positions':[]}))
  worker.start()
  with patch.dict(os.environ,{'CENTRAL_RISK_ENFORCE_DRY_RUN':'1',
                               'CENTRAL_RISK_REQUEST_TIMEOUT_SEC':'2.0'}):
   client=CentralRiskClient(redis_client=r)
  l=client.evaluate_open(strategy_id='LONG1',symbol='NEARUSDT',
                        side='long',market_context_multiplier=1,reserve=True)
  s=client.evaluate_open(strategy_id='SHORT1',symbol='INJUSDT',
                        side='short',market_context_multiplier=1,reserve=True)
  assert l['state']==s['state']=='READY',(l,s)
  assert abs(l['decision']['allowed_notional']-46)<.001,l
  assert abs(s['decision']['allowed_notional']-46)<.001,s
  assert l['decision']['production_ready']==s['decision']['production_ready']==False
  assert r.hlen(service.RESERVATION_HASH)==2
  # New clients do not own old reservations; they cannot release another owner.
  with patch.dict(os.environ,{'CENTRAL_RISK_ENFORCE_DRY_RUN':'1'}):
   other=CentralRiskClient(redis_client=r)
  assert other.release(strategy_id='LONG1')['state']=='REJECT'
  assert r.hlen(service.RESERVATION_HASH)==2
  # Correct owners release on the real request/response stream.
  release_long=client.release(strategy_id='LONG1')
  assert release_long['state']=='READY'
  assert r.hlen(service.RESERVATION_HASH)==1
  release_short=client.release(strategy_id='SHORT1')
  assert release_short['state']=='READY'
  assert r.hlen(service.RESERVATION_HASH)==0
  assert not failures,failures
  print(json.dumps({
   'actual_LONG1_central_service_handler':True,
   'actual_SHORT1_CentralRiskClient':True,
   'two_engine_shared_budget':92,
   'central_risk_production_authority':False,
   'wrong_client_release_rejected':True,
   'owner_release_roundtrip':True,
   'api_calls':0,'order_calls':0,'production_redis_writes':0,
   'test_socket_only':True,'result':'PASS'},sort_keys=True))
 finally:
  shutdown.set();worker.join(timeout=2)
  try:r.shutdown(save=False)
  except (redis.exceptions.RedisError,OSError):pass
  proc.wait(timeout=4)
