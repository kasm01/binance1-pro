"""True research-only chain Stage27 double-pass -> Actual Master -> Stage26 Lua.

No exchange call, no production Redis, no independent attestation, no live order.
"""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import json,os,subprocess,time
import redis
from research.staging.stage27_broker_consistency_evidence_v1 import capture
from research.staging.stage26_joint_atomic_master_dry_v1 import AtomicResearch,policy_decision

T=1794948000000
def broker(*,broken=False):
    ticks=iter([T,T+600])
    def acc():
        return {"totalMarginBalance":"100","availableBalance":"80",
            "totalInitialMargin":"0",
                 "totalOpenOrderInitialMargin":"0",
                 "totalPositionInitialMargin":"0","positions":[]}
    def pos():
        if broken:raise TimeoutError("positionRisk offline")
        return []
    return capture(get_account=acc,get_all_position_risk=pos,
        get_open_orders=lambda s:[],get_open_algos=lambda s:[],
        clock_ms=lambda:next(ticks))
good=broker()
bad=broker(broken=True)
assert good.state=="CONSISTENT_READONLY_ONLY"
assert bad.state=="UNKNOWN"
assert good.fingerprint and not good.live_order_authorized
assert good.source_authenticated is False and good.independently_verified_account_id is False

with TemporaryDirectory(prefix="stage27_bridge_isolated_") as folder:
    os.chmod(folder,0o700)
    sock=str(Path(folder)/"redis.sock")
    p=subprocess.Popen(["redis-server","--port","0","--unixsocket",sock,
       "--unixsocketperm","600","--save","","--appendonly","no",
       "--maxmemory","20mb","--maxmemory-policy","noeviction","--dir",folder],
       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    r=redis.Redis(unix_socket_path=sock,decode_responses=True,
                  socket_connect_timeout=.5,socket_timeout=2)
    try:
        for _ in range(70):
            try:
                if r.ping():break
            except (redis.exceptions.RedisError,OSError):time.sleep(.05)
        else:raise RuntimeError("isolated Redis unavailable")
        stage=AtomicResearch(r,prefix="research:stage27:bridge")
        epoch=stage.action("BEGIN")["epoch"]
        assert stage.action("RESERVE",epoch=epoch,digest="0"*64,request="x",
           strategy="LONG1",symbol="NEARUSDT",side="long",owner="x",client_order_id="cx",
           approved_notional=46,requested_notional=50)["state"]=="REJECT"
        # A broken capture must never be promoted to an even TEST-only binding.
        if bad.state=="CONSISTENT_READONLY_ONLY":
            raise AssertionError("untrusted broker capture was promoted")
        assert r.get(stage.keys[0])=="CLOSED"
        # Research-only simulated harness: BIND_TEST explicitly takes arbitrary
        # digest/budget; this is NOT authenticated Binance authorizer.
        long=policy_decision(strategy="LONG1",symbol="NEARUSDT",side="long",
                  equity=100,positions=[])
        short=policy_decision(strategy="SHORT1",symbol="INJUSDT",side="short",
                  equity=100,positions=[])
        assert long.state==short.state=="READY"
        assert long.production_ready is False and short.production_ready is False
        bound=stage.action("BIND_TEST",epoch=epoch,digest=good.fingerprint,
                  requested_notional=92)
        assert bound["state"]=="READY" and bound["order_authorized"] is False
        a=dict(epoch=epoch,digest=good.fingerprint,request="intent-a",
            strategy="LONG1",symbol="NEARUSDT",side="long",owner="owner-a",
            client_order_id="order-a",requested_notional=50,
            approved_notional=long.allowed_notional)
        b=dict(epoch=epoch,digest=good.fingerprint,request="intent-b",
            strategy="SHORT1",symbol="INJUSDT",side="short",owner="owner-b",
            client_order_id="order-b",requested_notional=50,
            approved_notional=short.allowed_notional)
        accepted_a=stage.action("RESERVE",**a)
        accepted_b=stage.action("RESERVE",**b)
        assert accepted_a["state"]==accepted_b["state"]=="READY"
        assert accepted_a["order_authorized"] is False
        assert accepted_b["order_authorized"] is False
        assert stage.action("VALIDATE",**a,fence=accepted_a["fence"])["order_authorized"] is False
        assert stage.action("VALIDATE",**dict(a,owner="intruder"),fence=accepted_a["fence"])["state"]=="REJECT"
        print(json.dumps({"doublepass_readonly_candidate":True,
          "bad_broker_read_blocks_even_test_binding":True,
          "actual_central_dry_master":True,
          "joint_atomic_research_reservations":2,
          "owner_and_fence_bound":True,
          "source_authenticated":False,
          "live_order_authorized":False,"orders_sent":0,
          "production_redis_writes":0,"result":"PASS"},sort_keys=True))
    finally:
        try:r.shutdown(save=False)
        except (redis.exceptions.RedisError,OSError):pass
        p.wait(timeout=5)
