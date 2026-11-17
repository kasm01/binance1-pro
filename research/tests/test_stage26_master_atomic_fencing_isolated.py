"""Actual CentralRiskMaster decisions + actual Redis Lua, isolated port0/AOF.

No production Redis, no exchange data, no order authorization.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
import json,os,subprocess,time
import redis
from research.staging.stage26_joint_atomic_master_dry_v1 import AtomicResearch,policy_decision
from orchestration.risk.central_risk_master import PositionExposure

def boot(root):
    sock=str(Path(root)/'db.sock')
    p=subprocess.Popen(['redis-server','--port','0','--unixsocket',sock,
      '--unixsocketperm','600','--save','','--appendonly','yes',
      '--appendfsync','always','--daemonize','no','--dir',root,
      '--maxmemory','24mb','--maxmemory-policy','noeviction'],
      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    r=redis.Redis(unix_socket_path=sock,decode_responses=True,
      socket_connect_timeout=.5,socket_timeout=3)
    for _ in range(65):
        try:
            if r.ping():return p,r
        except (redis.exceptions.RedisError,OSError):time.sleep(.06)
    p.terminate();p.wait(timeout=4)
    raise RuntimeError('isolation_socket_unavailable')
def halt(p,r):
    try:r.shutdown(save=False)
    except (redis.exceptions.RedisError,OSError):pass
    p.wait(timeout=5)

with TemporaryDirectory(prefix='stage26_master_fenced_AOF_') as folder:
    os.chmod(folder,0o700)
    proc,r=boot(folder)
    try:
        risk=AtomicResearch(r)
        long=policy_decision(strategy='LONG1',symbol='NEARUSDT',
                             side='long',equity=100,positions=[])
        short=policy_decision(strategy='SHORT1',symbol='INJUSDT',
                             side='short',equity=100,positions=[])
        assert long.state==short.state=='READY'
        assert long.production_ready is False and short.production_ready is False
        assert round(long.allowed_notional,3)==round(short.allowed_notional,3)==46
        digest=sha256(b'STAGE26_SYNTHETIC_LOCAL_EVIDENCE_NOT_ATTESTED').hexdigest()
        e=risk.action('BEGIN')['epoch']
        assert risk.action('RESERVE',epoch=e,digest=digest,
           request='A',strategy='LONG1',symbol='NEARUSDT',side='long',
           owner='ownedA',client_order_id='cidA',approved_notional=46,
           requested_notional=50)['state']=='REJECT'
        assert risk.action('BIND_TEST',epoch=e,digest=digest,requested_notional=92)['state']=='READY'
        data=lambda i:dict(epoch=e,digest=digest,request=f'long-{i}',
           strategy='LONG1',symbol='NEARUSDT',side='long',
           owner=f'owner-{i}',client_order_id=f'cid-{i}',
           approved_notional=long.allowed_notional,requested_notional=50)
        with ThreadPoolExecutor(max_workers=20) as pool:
            outcomes=list(pool.map(lambda i:risk.action('RESERVE',**data(i)),range(60)))
        winners=[i for i,v in enumerate(outcomes) if v['state']=='READY']
        assert len(winners)==1,(len(winners),outcomes)
        chosen=winners[0]
        a=data(chosen)
        accepted=outcomes[chosen]
        assert accepted['order_authorized'] is False
        assert accepted['fence']==1
        same=risk.action('RESERVE',**a)
        assert same['state']=='READY' and same['fence']==accepted['fence']
        assert risk.action('RESERVE',**dict(a,owner='wrong'))['reason']=='identity_conflict'
        b=dict(epoch=e,digest=digest,request='short-1',strategy='SHORT1',
               symbol='INJUSDT',side='short',owner='short-owner',
               client_order_id='short-cid',approved_notional=short.allowed_notional,
               requested_notional=50)
        accepted_b=risk.action('RESERVE',**b)
        assert accepted_b['state']=='READY' and accepted_b['fence']>accepted['fence']
        assert r.hlen(risk.keys[3])==2
        # Test a second isolated epoch/namespace with a tighter portfolio cap.
        # First 46 accepted; concurrent SECOND strategy must be denied if
        # total exceeds 80, despite its individually approved Master amount.
        constrained=AtomicResearch(r,prefix='research:stage26:budget80')
        cap_epoch=constrained.action('BEGIN')['epoch']
        assert constrained.action('BIND_TEST',epoch=cap_epoch,digest=digest,
                      requested_notional=80)['state']=='READY'
        first=constrained.action('RESERVE',**dict(a,epoch=cap_epoch))
        assert first['state']=='READY'
        over=constrained.action('RESERVE',**dict(b,epoch=cap_epoch))
        assert over['state']=='REJECT' and over['reason']=='portfolio_budget_exhausted'
        assert r.hlen(constrained.keys[3])==1
        # Both Final Safety candidates validate only exact same epoch,
        # owner, client order id and fence, still NO exchange authority.
        assert risk.action('VALIDATE',**a,fence=accepted['fence'])['state']=='READY'
        assert risk.action('VALIDATE',**a,fence=accepted_b['fence'])['state']=='REJECT'
        assert risk.action('VALIDATE',**dict(a,client_order_id='forged'),fence=accepted['fence'])['state']=='REJECT'
        assert risk.action('VALIDATE',**dict(a,now=1030001),fence=accepted['fence'])['reason']=='reservation_expired'
        # Failed/uncertain real order would quarantine instead of releasing.
        frozen=risk.action('QUARANTINE',**a,fence=accepted['fence'])
        assert frozen['state']=='READY'
        assert r.hlen(risk.keys[7])==1
        assert r.get(risk.keys[0])=='CLOSED'
        e2=risk.action('BEGIN')['epoch']
        assert e2>e
        assert risk.action('BIND_TEST',epoch=e2,digest=digest,requested_notional=92)['reason']=='unresolved_or_invalid_snapshot'
        assert risk.action('VALIDATE',**b,fence=accepted_b['fence'])['state']=='REJECT'
        halt(proc,r);proc=None
        proc,r=boot(folder);risk=AtomicResearch(r)
        assert int(r.get(risk.keys[1]))==e2
        assert int(r.get(risk.keys[5]))==accepted_b['fence']
        assert r.get(risk.keys[0])=='CLOSED'
        assert r.hlen(risk.keys[7])==1
        assert r.hlen(risk.keys[3])==1
        print(json.dumps({'actual_CentralRiskMaster_policy':True,
         'synthetic_long_short_approved_notional':[long.allowed_notional,short.allowed_notional],
         'policy_production_ready':False,'concurrent_long_requests':60,
         'single_long_winner':len(winners)==1,'separate_short_slot':True,
         'atomic_cross_strategy_budget_cap_enforced':True,
         'fencing_strict':True,'idempotent':True,'expired_final_safety_rejected':True,
         'unknown_order_quarantine_sticky':True,
         'stale_epoch_rejected':True,'redis_AOF_restart_closed':True,
         'live_order_authorized':False,'exchange_orders':0,
         'production_redis_writes':0,'result':'PASS'},sort_keys=True))
    finally:
        if proc is not None:halt(proc,r)
