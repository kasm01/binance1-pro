"""Real central DRY _handle on isolated local Redis unix socket, no live data."""
from __future__ import annotations
import json,os,subprocess,time
from tempfile import TemporaryDirectory
from pathlib import Path
import redis
from scripts.central_risk_enforce_dry_service import _handle,RESERVATION_HASH,SNAPSHOT_KEY

def boot(folder):
 sock=str(Path(folder)/"research.sock")
 p=subprocess.Popen(["redis-server","--port","0","--unixsocket",sock,
   "--unixsocketperm","600","--save","","--appendonly","no",
   "--maxmemory","16mb","--maxmemory-policy","noeviction",
   "--daemonize","no","--dir",folder],
   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 r=redis.Redis(unix_socket_path=sock,decode_responses=True,
               socket_connect_timeout=.5,socket_timeout=1)
 for _ in range(70):
  try:
   if r.ping():return p,r
  except (redis.exceptions.RedisError,OSError):time.sleep(.05)
 p.terminate();p.wait(timeout=4)
 raise RuntimeError("isolated_redis_not_ready")
def stop(p,r):
 try:r.shutdown(save=False)
 except redis.exceptions.RedisError:pass
 try:p.wait(timeout=4)
 except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=4)

def req(i,strategy="LONG1",action="EVALUATE_OPEN",**k):
 out=dict(request_id=i,request_mode="DRY_RUN",action=action,
          strategy_id=strategy,symbol="NEARUSDT" if strategy=="LONG1" else "INJUSDT",
          side="long" if strategy=="LONG1" else "short",
          market_context_multiplier=1.,reserve=True)
 out.update(k);return out

with TemporaryDirectory(prefix="stage25_central_owner_cas_") as folder:
 os.chmod(folder,0o700);p,r=boot(folder)
 try:
  r.set(SNAPSHOT_KEY,json.dumps({
    "ts":time.time(),"exposure_health":{"status":"OK","freeze_new_entries":False},
    "account":{"mtm_equity":100},"portfolio_state":{
      "equity_peak":100,"mode":"NORMAL","recovery_successes":0},
    "positions":[]}))
  a=_handle(r,req("openA"))
  assert a["state"]=="READY" and a["decision"]["production_ready"] is False,a
  assert r.hlen(RESERVATION_HASH)==1
  for scenario,q,reason in [
   ("live_release",req("intruder","LONG1","RELEASE",request_mode="LIVE",
             reservation_owner_request_id="openA"),"live_release_not_authorized"),
   ("missing_owner",req("bad","LONG1","RELEASE"),"reservation_owner_missing"),
   ("stale_owner",req("bad2","LONG1","RELEASE",
             reservation_owner_request_id="prior"),"reservation_owner_mismatch")]:
   result=_handle(r,q)
   assert result["state"]=="REJECT" and result["reason"]==reason,(scenario,result)
   assert r.hlen(RESERVATION_HASH)==1
  ok=_handle(r,req("releaseA","LONG1","RELEASE",
                         reservation_owner_request_id="openA"))
  assert ok["state"]=="READY" and r.hlen(RESERVATION_HASH)==0
  b=_handle(r,req("openB"))
  assert b["state"]=="READY"
  stale=_handle(r,req("delayedA","LONG1","RELEASE",
                         reservation_owner_request_id="openA"))
  assert stale["state"]=="REJECT"
  assert json.loads(r.hget(RESERVATION_HASH,"LONG1"))["request_id"]=="openB"
  good_b=_handle(r,req("releaseB","LONG1","RELEASE",
                        reservation_owner_request_id="openB"))
  assert good_b["state"]=="READY"
  short=_handle(r,req("short","SHORT1"))
  assert short["state"]=="READY"
  wrong_strategy=_handle(r,req("bad-strategy","LONG2","RELEASE",
                               reservation_owner_request_id="short"))
  assert wrong_strategy["state"]=="REJECT"
  assert r.hexists(RESERVATION_HASH,"SHORT1")
  print(json.dumps({
    "actual_central_dry_handle":True,"real_lua_atomic_cas":True,
    "live_release_rejected":True,"missing_owner_rejected":True,
    "stale_owner_rejected":True,"newer_reservation_preserved":True,
    "legitimate_owner_release_works":True,
    "dry_short_reservation_works":True,
    "production_redis_touched":False,"orders_sent":0,
    "live_order_authorized":False,"status":"PASS"},sort_keys=True))
 finally:stop(p,r)
