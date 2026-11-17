"""Actual Stage26 atomic Redis reservation record -> actual SHORT broker binder.

All broker responses synthetic, isolation socket-only, no LIVE order authority.
"""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util,json,os,subprocess,time
import redis
from research.staging.stage26_joint_atomic_master_dry_v1 import AtomicResearch,policy_decision
import orchestration.risk as pkg
pkg.__path__.append(str(Path.home()/'binance1/orchestration/risk'))
short=Path.home()/'binance1/research/staging/stage28_reservation_exact_broker_bridge_v1.py'
spec=importlib.util.spec_from_file_location('stage28_exact_source',short)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assess=module.assess_stage28

def start(folder):
 sock=str(Path(folder)/'sandbox.sock')
 p=subprocess.Popen(['redis-server','--port','0','--unixsocket',sock,
   '--unixsocketperm','600','--save','','--appendonly','no',
   '--maxmemory','18mb','--maxmemory-policy','noeviction','--dir',folder],
   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 r=redis.Redis(unix_socket_path=sock,decode_responses=True,
     socket_connect_timeout=.5,socket_timeout=2)
 for _ in range(70):
  try:
   if r.ping():return p,r
  except (redis.exceptions.RedisError,OSError):time.sleep(.05)
 p.terminate();p.wait(timeout=4);raise RuntimeError('isolated socket failed')

with TemporaryDirectory(prefix='stage28_stage26_record_') as folder:
 os.chmod(folder,0o700);p,r=start(folder)
 try:
  central=AtomicResearch(r,prefix='research:stage28:exact')
  epoch=central.action('BEGIN')['epoch']
  digest='c'*64
  assert central.action('BIND_TEST',epoch=epoch,digest=digest,requested_notional=92)['state']=='READY'
  checked=[]
  for strategy,symbol,side,order_side,position_side,stop_side,position_amt in (
      ('LONG1','NEARUSDT','long','BUY','LONG','SELL','2'),
      ('SHORT1','INJUSDT','short','SELL','SHORT','BUY','-2')):
   decision=policy_decision(strategy=strategy,symbol=symbol,side=side,
                           equity=100,positions=[])
   assert decision.state=='READY' and decision.production_ready is False
   req=f'intent-{strategy}'
   owner=f'owner-{strategy}'
   cid=f'entry-{strategy}'
   granted=central.action('RESERVE',epoch=epoch,digest=digest,request=req,
            strategy=strategy,symbol=symbol,side=side,owner=owner,
            client_order_id=cid,requested_notional=50,
            approved_notional=decision.allowed_notional)
   assert granted['state']=='READY',granted
   stored=json.loads(r.hget(central.keys[3],strategy))
   assert stored['fence']==granted['fence']
   assert stored['epoch']==epoch
   ledger=dict(intent_id=req,reservation_owner=owner,
      reservation_id=f"epoch-{epoch}-fence-{granted['fence']}",
      epoch=epoch,fence=granted['fence'],owner=strategy,symbol=symbol,
      side=order_side,client_order_id=cid,stage='FILLED',
      original_qty='2',filled_qty='2',client_algo_id=f'stop-{strategy}')
   order=dict(symbol=symbol,clientOrderId=cid,orderId=100,
              side=order_side,status='FILLED',origQty='2',executedQty='2')
   fills=[dict(symbol=symbol,orderId=100,id=1,qty='2')]
   pos=[dict(symbol=symbol,positionSide=position_side,positionAmt=position_amt)]
   stop=[dict(symbol=symbol,clientAlgoId=f'stop-{strategy}',
      algoId=900,side=stop_side,positionSide=position_side,
      orderType='STOP_MARKET',closePosition=True,
      workingType='MARK_PRICE',algoStatus='NEW')]
   def read(*,algos=stop):
    return assess(reservation=stored,ledger=ledger,
      read_order=lambda s,c:order,read_fills=lambda s,o:fills,
      read_positions=lambda s:pos,read_open_orders=lambda s:[],
      read_open_algo=lambda s:algos,
      expected_epoch=epoch,expected_fence=granted['fence'],now_ms=1000300)
   protected=read()
   assert protected['state']=='PROTECTED_EVIDENCE_ONLY',protected
   assert not protected['can_submit'] and not protected['can_commit']
   assert not protected['can_release'] and not protected['live_order_authorized']
   assert read(algos=[])['state']=='FREEZE_UNPROTECTED'
   assert central.action('VALIDATE',epoch=epoch,digest=digest,
            request=req,strategy=strategy,symbol=symbol,side=side,
            owner=owner,client_order_id=cid,now=1000300,
            fence=granted['fence'])['order_authorized'] is False
   checked.append(strategy)
  assert r.hlen(central.keys[3])==2
  print(json.dumps({'actual_stage26_redis_records':len(checked),
      'both_strategy_ledger_protected_evidence':checked,
      'missing_owned_stop_freezes_both':True,
      'reservation_remains_held':True,
      'automatic_commits':0,'automatic_releases':0,
      'exchange_orders':0,'production_redis_writes':0,
      'live_order_authorized':False,'result':'PASS'},sort_keys=True))
 finally:
  try:r.shutdown(save=False)
  except (redis.exceptions.RedisError,OSError):pass
  p.wait(timeout=5)
