"""Isolated unix-socket-only Redis with AOF, never the production Redis port.

All tests research-only; no real Binance reads or order permissions.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import json,os,subprocess,time
import redis
from research.staging.stage19_epoch_fencing_reservation_v1 import (
    IsolatedEpochFenceRisk,local_evidence_digest)

def boot(folder):
    sock=str(Path(folder)/"research.sock")
    args=["redis-server","--port","0","--unixsocket",sock,
          "--unixsocketperm","600","--save","","--appendonly","yes",
          "--appendfsync","always","--daemonize","no","--maxmemory","32mb",
          "--maxmemory-policy","noeviction","--loglevel","warning","--dir",folder]
    proc=subprocess.Popen(args,stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    conn=redis.Redis(unix_socket_path=sock,decode_responses=True,
                    socket_connect_timeout=.5,socket_timeout=2)
    for _ in range(80):
        try:
            if conn.ping():return proc,conn
        except (redis.exceptions.RedisError,OSError):
            time.sleep(.08)
    proc.terminate();proc.wait(timeout=5)
    raise RuntimeError("isolated Redis unavailable")

def stop(proc,client):
    try:client.shutdown(save=False)
    except (redis.exceptions.RedisError,OSError):pass
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate();proc.wait(timeout=5)

with TemporaryDirectory(prefix="stage19_isolated_socket_aof_") as temp:
    os.chmod(temp,0o700)
    p,r=boot(temp)
    try:
        proto=IsolatedEpochFenceRisk(r)
        seed={"symbol_universe":["NEARUSDT","INJUSDT"],
              "positions":[],"orders":[],"algos":[],
              "complete":True,"fresh":True,"source":"SIMULATED_ONLY"}
        digest=local_evidence_digest(seed,secret=b"offline-fixed-test-key-NOT-LIVE")
        assert digest==local_evidence_digest(seed,secret=b"offline-fixed-test-key-NOT-LIVE")
        assert digest!=local_evidence_digest(dict(seed,complete=False),
                                             secret=b"offline-fixed-test-key-NOT-LIVE")
        # Gate must remain closed on empty server and after restart.
        assert proto.action("RESERVE",epoch=1,digest=digest,request="before",
           strategy="LONG1",symbol="NEARUSDT",side="long",token="before")["state"]=="REJECT"
        start=proto.action("BEGIN")
        epoch1=start["epoch"]
        assert epoch1>=1
        assert proto.action("PUBLISH",epoch=epoch1,digest=digest)["state"]=="REJECT"
        assert proto.action("PUBLISH",epoch=epoch1,digest=digest,
                            attested="LOCAL_RESEARCH_VERIFIED")["state"]=="READY"
        # Two strategies get independent slots, same strategy race has one winner.
        kwargs=dict(epoch=epoch1,digest=digest,strategy="LONG1",
                    symbol="NEARUSDT",side="long")
        with ThreadPoolExecutor(max_workers=20) as workers:
            results=list(workers.map(
                lambda i:proto.action("RESERVE",request=f"race{i}",
                    token=f"token{i}",**kwargs),range(60)))
        winners=[i for i,x in enumerate(results) if x["state"]=="READY"]
        assert len(winners)==1,results
        win=winners[0];w=results[win]
        fence1=w["fence"]
        assert fence1>0
        assert w["live_order_authorized"] is False
        a=proto.action("RESERVE",request=f"race{win}",token=f"token{win}",**kwargs)
        assert a["state"]=="READY" and a["reason"]=="idempotent_reservation" and a["fence"]==fence1
        expired_replay=proto.action("RESERVE",request=f"race{win}",
           token=f"token{win}",now=1000000+30001,**kwargs)
        assert expired_replay["state"]=="REJECT"
        assert expired_replay["reason"]=="expired_idempotent_replay"
        assert proto.action("RESERVE",request=f"race{win}",token="forged",**kwargs)["reason"]=="request_id_conflict"
        assert proto.action("RESERVE",request="short",token="short-token",epoch=epoch1,
            digest=digest,strategy="SHORT1",symbol="INJUSDT",side="short")["state"]=="READY"
        assert proto.action("RESERVE",request="third",token="third",**kwargs)["state"]=="REJECT"
        # Wrong owner and missing independent exchange flat proof do not release.
        assert proto.action("RELEASE",request=f"race{win}",token="wrong",**kwargs,
            position="ISOLATED_TEST_EXCHANGE_FLAT")["state"]=="REJECT"
        assert proto.action("RELEASE",request=f"race{win}",token=f"token{win}",**kwargs)["state"]=="REJECT"
        # Reconciliation begins before slow downstream evidence; invalidate
        # existing grant (but preserve pending reservation to block re-open).
        e2=proto.action("BEGIN")["epoch"]
        assert e2>epoch1
        assert proto.action("PUBLISH",epoch=epoch1,digest=digest,
           attested="LOCAL_RESEARCH_VERIFIED")["reason"]=="epoch_stale_or_unissued"
        assert proto.action("COMMIT",request=f"race{win}",token=f"token{win}",
           position="position-synth",**kwargs)["state"]=="REJECT"
        assert proto.action("PUBLISH",epoch=e2,digest=digest,
           attested="LOCAL_RESEARCH_VERIFIED")["reason"]=="unresolved_exposure"
        assert proto.action("RESERVE",request="postepoch",token="new",
           epoch=e2,digest=digest,strategy="LONG1",symbol="NEARUSDT",
           side="long")["state"]=="REJECT"
        assert r.hlen(proto.keys[4])==2
        # Capture is durable across AOF restart, while state remains closed.
        stop(p,r);p=None
        p,r=boot(temp);proto=IsolatedEpochFenceRisk(r)
        assert int(r.get(proto.keys[1]))==e2
        assert int(r.get(proto.keys[3]))>=fence1
        assert r.get(proto.keys[0])=="CLOSED"
        assert r.hlen(proto.keys[4])==2
        assert proto.action("RESERVE",request="afterrestart",token="after",
           epoch=e2,digest=digest,strategy="LONG1",symbol="NEARUSDT",
           side="long")["state"]=="REJECT"
        e3=proto.action("BEGIN")["epoch"]
        assert e3>e2
        assert proto.action("PUBLISH",epoch=e3,digest=digest,
            attested="LOCAL_RESEARCH_VERIFIED")["reason"]=="unresolved_exposure"
        # A new empty risk world cannot admit old epoch/fence tokens.
        # Separate isolated Redis DB to simulate reconciled recovery and new cap.
        fresh=IsolatedEpochFenceRisk(r,prefix="research:stage19:recovered")
        clean_epoch=fresh.action("BEGIN")["epoch"]
        assert fresh.action("PUBLISH",epoch=clean_epoch,digest=digest,
            attested="LOCAL_RESEARCH_VERIFIED")["state"]=="READY"
        new=fresh.action("RESERVE",request="fresh",strategy="LONG1",
            symbol="NEARUSDT",side="long",epoch=clean_epoch,
            digest=digest,token="fresh")
        assert new["state"]=="READY"
        assert fresh.action("COMMIT",request="fresh",strategy="LONG1",
            symbol="NEARUSDT",side="long",epoch=clean_epoch,
            digest=digest,token="wrong",position="synthetic-fill")["state"]=="REJECT"
        assert fresh.action("COMMIT",request="fresh",strategy="LONG1",
            symbol="NEARUSDT",side="long",epoch=clean_epoch,
            digest=digest,token="fresh",position="synthetic-fill")["state"]=="READY"
        print(json.dumps({
            "isolated_redis":"unixsocket_port0_aof",
            "race_requests":60,"same_slot_winners":len(winners),
            "two_distinct_strategies_reserved":True,
            "same_request_idempotent":True,
            "expired_idempotent_replay_rejected":True,
            "wrong_owner_rejected":True,
            "late_old_epoch_publish_rejected":True,
            "late_old_epoch_commit_rejected":True,
            "unresolved_old_positions_block_reopen":True,
            "aof_restart_preserves_epoch_and_fence":True,
            "restart_gate_closed":True,
            "fake_verified_string_not_real_exchange_proof":True,
            "live_order_authorized":False,
            "production_redis_writes":0,
            "exchange_api_calls":0,
            "overall":"PASS",
        },sort_keys=True))
    finally:
        if p is not None:stop(p,r)
