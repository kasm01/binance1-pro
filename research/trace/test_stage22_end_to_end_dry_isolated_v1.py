"""Shared LONG1/SHORT1 order-path model, isolated Redis + FAKE order sink.

This uses actual staged epoch/fencing Lua, actual stage21 candidate, and a
strict simulated Final Safety; it CANNOT make real orders or authorize them.
"""
from __future__ import annotations
import json,os,sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import redis,subprocess,time
from research.staging.stage19_epoch_fencing_reservation_v1 import (
    IsolatedEpochFenceRisk,local_evidence_digest)
from research.staging.stage21_joint_risk_authority_v1 import evaluate_joint_candidate

@dataclass(frozen=True)
class Decision:
    strategy_id:str="LONG1"
    symbol:str="NEARUSDT"
    side:str="long"
    state:str="READY"
    production_ready:bool=True
    allowed_notional:float=15.0

def launch(folder):
    sock=str(Path(folder)/'redis.sock')
    p=subprocess.Popen(['redis-server','--port','0','--unixsocket',sock,
      '--unixsocketperm','600','--save','','--appendonly','yes',
      '--appendfsync','always','--daemonize','no','--dir',str(folder),
      '--maxmemory','24mb','--maxmemory-policy','noeviction'],
      stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    r=redis.Redis(unix_socket_path=sock,decode_responses=True,
                  socket_connect_timeout=.5,socket_timeout=2)
    for _ in range(70):
        try:
            if r.ping():return p,r
        except (redis.exceptions.RedisError,OSError):time.sleep(.06)
    p.terminate();p.wait(timeout=3);raise RuntimeError('test Redis down')

def end(p,r):
    try:r.shutdown(save=False)
    except Exception:pass
    p.wait(timeout=5)

class FakeOrderSink:
    """This sink never calls Binance; records ONLY synthetic source path."""
    def __init__(self):self.attempts=[]
    def place(self,_,**kwargs):
        self.attempts.append(kwargs)
        return {"status":"SYNTHETIC_ONLY"}

with TemporaryDirectory(prefix='stage22_socket_e2e_') as tmp:
    os.chmod(tmp,0o700)
    p,r=launch(tmp)
    try:
        k=IsolatedEpochFenceRisk(r)
        sink=FakeOrderSink()
        tm=1794948000000
        digest=local_evidence_digest({"kind":"SYNTHETIC_BROKER_EVIDENCE",
          "account_id":"sandbox","ts":tm},secret=b"TEST_ONLY")
        e=k.action("BEGIN")["epoch"]
        assert k.action("PUBLISH",epoch=e,digest=digest,
                        attested="LOCAL_RESEARCH_VERIFIED")["state"]=="READY"
        args=dict(epoch=e,digest=digest,strategy="LONG1",symbol="NEARUSDT",
                  side="long",now=tm,ttl=30000)
        # Profile proof and authoritative broker identity must be independently
        # verified in future. Test flags here are synthetic, not real sources.
        acc={"LONG1":"sandbox","SHORT1":"sandbox"}
        proof={"verified":True,"account_id":"sandbox"}
        snap={"account_id":"sandbox","complete":True,
              "positions_and_orders_verified":True,"source_authenticated":True,
              "epoch":e,"timestamp_ms":tm,"unknown_intents":False,
              "available_margin":"50"}
        def check(**updates):
            a=dict(two_accounts=acc,shared_identity=proof,
                   portfolio_snapshot=snap,central_decision=Decision(),
                   expected_epoch=e,strategy_id="LONG1",
                   symbol="NEARUSDT",side="long",now_ms=tm+100)
            a.update(updates)
            return evaluate_joint_candidate(**a)
        candidate=check()
        assert candidate.state=="READY_CANDIDATE_ONLY"
        reserved=k.action("RESERVE",request="A",token="token-A",**args)
        assert reserved["state"]=="READY" and reserved["live_order_authorized"] is False
        assert k.action("RESERVE",request="B",token="token-B",**args)["state"]=="REJECT"
        assert check(two_accounts=dict(acc,SHORT1="other")).state=="REJECT"
        assert check(portfolio_snapshot=dict(snap,source_authenticated=False)).state=="REJECT"
        assert check(portfolio_snapshot=dict(snap,unknown_intents=True)).state=="REJECT"
        assert check(central_decision=Decision(production_ready=False)).state=="REJECT"
        # Final safety must require same epoch and matching fencing token.
        def final_safety(*,passed,epoch,token,request,at_ms,account_match=True):
            if not passed or not account_match:return False
            if int(r.get(k.keys[1]))!=epoch:return False
            if r.get(k.keys[0])!="RESEARCH_OPEN":return False
            x=r.hget(k.keys[4],"LONG1")
            if not x:return False
            row=json.loads(x)
            return (row.get('request')==request and row.get('token')==token and
                    row.get('epoch')==epoch and at_ms<=row.get('expires_at',0))
        assert final_safety(passed=True,epoch=e,request="A",
                            token="token-A",at_ms=tm+100)
        assert not final_safety(passed=True,epoch=e,request="A",
                            token="wrong",at_ms=tm+100)
        assert not final_safety(passed=True,epoch=e,request="A",
                            token="token-A",at_ms=tm+30001)
        assert not final_safety(passed=True,epoch=e,request="A",
                            token="token-A",at_ms=tm+100,account_match=False)
        # Simulate stale final check: second capture closes before broker read.
        e2=k.action("BEGIN")["epoch"]
        assert e2>e
        assert not final_safety(passed=True,epoch=e,request="A",
                            token="token-A",at_ms=tm+200)
        assert k.action("COMMIT",request="A",token="token-A",
           position="synthetic-fill",**args)["state"]=="REJECT"
        # A fail closed gate never emits to even the fake sink.
        if final_safety(passed=True,epoch=e,request="A",
                         token="token-A",at_ms=tm+200):
            sink.place("sandbox",symbol="NEARUSDT")
        assert len(sink.attempts)==0
        # Redis outage and recovery: persisted CLOSED and unresolved exposure.
        end(p,r);p=None
        p,r=launch(tmp);k=IsolatedEpochFenceRisk(r)
        assert r.get(k.keys[0])=="CLOSED"
        assert int(r.get(k.keys[1]))==e2
        assert r.hlen(k.keys[4])==1
        assert k.action("PUBLISH",epoch=e2,digest=digest,
            attested="LOCAL_RESEARCH_VERIFIED")["reason"]=="unresolved_exposure"
        # Never unlock by deleting exposure or forging an exchange flat flag.
        print(json.dumps({"joint_risk_synthetic_candidate":True,
          "wrong_account_blocked":True,"missing_source_blocked":True,
          "unresolved_intent_blocked":True,"unauthorized_central_blocked":True,
          "duplicate_strategy_reserve_blocked":True,
          "wrong_fencing_token_blocked":True,"expired_reserve_blocked":True,
          "last_millisecond_epoch_change_blocked":True,
          "aof_restart_closed_with_unresolved_position":True,
          "synthetic_order_sink_calls":len(sink.attempts),
          "binance_order_calls":0,"production_redis_writes":0,
          "isolation":"unix_socket_port_zero",
          "live_order_authorized":False,
          "overall":"PASS"},sort_keys=True))
    finally:
        if p is not None:end(p,r)
