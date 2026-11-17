"""Stage26 real AOF Redis records + Stage28 real evidence binder + Stage29 journal.

ALL broker responses synthetic, no exchange/order calls, no production Redis.
Covers lost POST response, 404, late exchange fill, protected stop, old epoch,
missing stop, duplicate audit, restart and unknown-sticky risk.
"""
from __future__ import annotations
import json,os,subprocess,time
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import redis
from research.staging.stage26_joint_atomic_master_dry_v1 import AtomicResearch,policy_decision
from research.staging.stage29_unknown_submit_recovery_journal_v1 import IsolatedRecoveryJournal
import orchestration.risk as pkg
pkg.__path__.append(str(Path.home()/'binance1/orchestration/risk'))
path=Path.home()/'binance1/research/staging/stage28_reservation_exact_broker_bridge_v1.py'
spec=importlib.util.spec_from_file_location('stage29_short_exact_binding',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assess=m.assess_stage28

def boot(folder):
    sock=str(Path(folder)/'sandbox.sock')
    process=subprocess.Popen(['redis-server','--port','0','--unixsocket',sock,
          '--unixsocketperm','600','--save','','--appendonly','yes',
          '--appendfsync','always','--maxmemory','24mb',
          '--maxmemory-policy','noeviction','--daemonize','no','--dir',folder],
          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=redis.Redis(unix_socket_path=sock,decode_responses=True,
            socket_connect_timeout=.5,socket_timeout=2)
    for _ in range(80):
        try:
            if client.ping():return process,client
        except (redis.exceptions.RedisError,OSError):time.sleep(.06)
    process.terminate();process.wait(timeout=4)
    raise RuntimeError('isolated Redis could not start')
def shutdown(p,r):
    try:r.shutdown(save=False)
    except (redis.exceptions.RedisError,OSError):pass
    p.wait(timeout=5)

with TemporaryDirectory(prefix='stage29_unknown_aof_only_') as folder:
    os.chmod(folder,0o700)
    p,r=boot(folder)
    try:
        risk=AtomicResearch(r,prefix='research:stage29:risk')
        journal=IsolatedRecoveryJournal(r,risk.keys)
        epoch=risk.action('BEGIN')['epoch']
        assert risk.action('BIND_TEST',epoch=epoch,digest='d'*64,
                           requested_notional=92)['state']=='READY'
        intents={}
        for strategy,symbol,side,bs,ps,stop_side,qty in (
                ('LONG1','NEARUSDT','long','BUY','LONG','SELL','2'),
                ('SHORT1','INJUSDT','short','SELL','SHORT','BUY','-2')):
            central=policy_decision(strategy=strategy,symbol=symbol,side=side,
                                     equity=100,positions=[])
            assert central.state=='READY' and not central.production_ready
            order_identity='entry-'+strategy
            rid='intent-'+strategy
            owner='owner-'+strategy
            got=risk.action('RESERVE',epoch=epoch,digest='d'*64,request=rid,
                strategy=strategy,symbol=symbol,side=side,owner=owner,
                client_order_id=order_identity,requested_notional=50,
                approved_notional=central.allowed_notional)
            assert got['state']=='READY'
            record=json.loads(r.hget(risk.keys[3],strategy))
            ledger=dict(intent_id=rid,reservation_owner=owner,owner=strategy,
                 reservation_id=f"epoch-{epoch}-fence-{got['fence']}",
                 epoch=epoch,fence=got['fence'],symbol=symbol,side=bs,
                 client_order_id=order_identity,stage='UNKNOWN',
                 original_qty='2',filled_qty='0',
                 client_algo_id='native-'+strategy)
            intents[strategy]=(record,ledger,
                dict(symbol=symbol,clientOrderId=order_identity,orderId=123,
                     side=bs,status='FILLED',origQty='2',executedQty='2'),
                [dict(symbol=symbol,orderId=123,id=1,qty='2')],
                [dict(symbol=symbol,positionSide=ps,positionAmt=qty)],
                [dict(symbol=symbol,clientAlgoId='native-'+strategy,
                  algoId=543,side=stop_side,positionSide=ps,
                  orderType='STOP_MARKET',closePosition=True,
                  workingType='MARK_PRICE',algoStatus='NEW')])
        assert r.hlen(risk.keys[3])==2

        def evidence(strategy,mode,stage=None):
            reserve,orig,order,fills,positions,stops=intents[strategy]
            ledger=dict(orig,stage=stage) if stage else dict(orig)
            if stage=='FILLED':ledger['filled_qty']='2'
            def get_order(symbol,cid):
                if mode=='network':raise TimeoutError('POST result missing')
                if mode=='404':raise ValueError('Binance order not found yet')
                if mode=='partial':
                    return dict(order,status='PARTIALLY_FILLED',executedQty='1')
                return order
            def get_fills(symbol,orderid):
                return fills if mode!='incomplete_fills' else []
            return assess(reservation=reserve,ledger=ledger,
                 read_order=get_order,read_fills=get_fills,
                 read_positions=lambda s:positions,
                 read_open_orders=lambda s:[],
                 read_open_algo=lambda s:[] if mode=='stop_missing' else stops,
                 expected_epoch=epoch,expected_fence=reserve['fence'],
                 now_ms=1000150)

        def observe(strategy,mode,event,*,stage=None):
            reserve,led,*_=intents[strategy]
            ticket=journal.begin()
            assert ticket['state']=='READY'
            proof=evidence(strategy,mode,stage)
            rec=journal.record(intent_id=led['intent_id'],strategy=strategy,
               owner=led['reservation_owner'],client_order_id=led['client_order_id'],
               reservation_epoch=epoch,reservation_fence=reserve['fence'],
               observation_epoch=ticket['observation_epoch'],event_id=event,
               evidence=proof,started_ms=1000000,finished_ms=1000200)
            assert rec['state']=='READY',(event,rec)
            assert not rec['can_resubmit'] and not rec['can_release'] and not rec['can_commit']
            assert r.get(risk.keys[0])=='CLOSED'
            assert r.hlen(risk.keys[3])+r.hlen(risk.keys[7])==2
            assert r.hexists(risk.keys[7],strategy)
            return rec,proof,ticket['observation_epoch']
        # First two independent network faults freeze and quarantine BOTH.
        first_long=observe('LONG1','network','long-lost-post')
        first_short=observe('SHORT1','404','short-not-found')
        assert first_long[1]['state']==first_short[1]['state']=='UNKNOWN_FREEZE'
        assert r.hlen(risk.keys[7])==2 and r.xlen(journal.keys[7])==2
        assert risk.action('RESERVE',epoch=epoch,digest='d'*64,
          request='repeat',strategy='LONG1',symbol='NEARUSDT',side='long',
          owner='new',client_order_id='new',requested_notional=50,
          approved_notional=46)['state']=='REJECT'
        # Crash/restart with AOF: quarantine, audit and CLOSED state are durable.
        shutdown(p,r);p=None
        p,r=boot(folder)
        risk=AtomicResearch(r,prefix='research:stage29:risk')
        journal=IsolatedRecoveryJournal(r,risk.keys)
        assert r.get(risk.keys[0])=='CLOSED'
        assert r.hlen(risk.keys[7])==2
        assert r.xlen(journal.keys[7])==2
        assert r.xlen(journal.keys[8])==2
        assert int(r.get(journal.keys[4]))==2
        # Existing UNKNOWN journal: broker later reports full fill;
        # do NOT rewrite journal or COMMIT without independently verified repair.
        late_fill=observe('SHORT1','filled','short-late-fill')
        assert late_fill[1]['state']=='RECOVERED_FILL_PENDING_JOURNAL'
        # Synthetic repaired FILLED journal with same immutable ownership
        # can observe correct native STOP, but never auto release/commit.
        matched=observe('SHORT1','filled','short-native-stop',stage='FILLED')
        assert matched[1]['state']=='PROTECTED_EVIDENCE_ONLY'
        missing=observe('SHORT1','stop_missing','short-no-stop',stage='FILLED')
        assert missing[1]['state']=='FREEZE_UNPROTECTED'
        assert missing[0]['max_severity']==6
        # Another newer positive cannot erase earlier missing-stop severity.
        later_positive=observe('SHORT1','filled','short-positive-later',stage='FILLED')
        assert later_positive[0]['max_severity']==6
        # Old observation arriving after newer positive: preserve latest
        # chronological observation but record late severe hazard.
        reserve,led,*_=intents['SHORT1']
        stale=journal.record(intent_id=led['intent_id'],strategy='SHORT1',
           owner=led['reservation_owner'],client_order_id=led['client_order_id'],
           reservation_epoch=epoch,reservation_fence=reserve['fence'],
           observation_epoch=missing[2],event_id='short-delayed-stop-hazard',
           evidence=missing[1],started_ms=1000000,finished_ms=1000200)
        assert stale['state']=='READY'
        latest=json.loads(r.hget(journal.keys[6],led['intent_id']))
        assert latest['latest_observation_epoch']==later_positive[2]
        assert latest['max_severity']==6
        # Idempotent audit replay does not create an extra event; forgery fails.
        event_count=r.xlen(journal.keys[7])
        repeat=journal.record(intent_id=led['intent_id'],strategy='SHORT1',
           owner=led['reservation_owner'],client_order_id=led['client_order_id'],
           reservation_epoch=epoch,reservation_fence=reserve['fence'],
           observation_epoch=missing[2],event_id='short-delayed-stop-hazard',
           evidence=missing[1],started_ms=1000000,finished_ms=1000200)
        assert repeat['reason']=='idempotent_evidence_event'
        assert r.xlen(journal.keys[7])==event_count
        forged=journal.record(intent_id=led['intent_id'],strategy='SHORT1',
           owner='different-owner',client_order_id=led['client_order_id'],
           reservation_epoch=epoch,reservation_fence=reserve['fence'],
           observation_epoch=missing[2],event_id='forged-owner',
           evidence=missing[1],started_ms=1000000,finished_ms=1000200)
        assert forged['state']=='REJECT'
        invalid_fence=journal.record(intent_id=led['intent_id'],strategy='SHORT1',
           owner=led['reservation_owner'],client_order_id=led['client_order_id'],
           reservation_epoch=epoch,reservation_fence=9999,
           observation_epoch=missing[2],event_id='forged-fence',
           evidence=missing[1],started_ms=1000000,finished_ms=1000200)
        assert invalid_fence['state']=='REJECT'
        assert r.hlen(risk.keys[7])==2 and r.hlen(risk.keys[3])==0
        assert r.get(risk.keys[0])=='CLOSED'
        assert risk.action('BIND_TEST',epoch=epoch,digest='d'*64,
                           requested_notional=92)['state']=='REJECT'
        print(json.dumps({
            'stage26_actual_reserved_strategies':2,
            'first_unknown_and_404_quarantined':True,
            'AOF_restart_keeps_both_quarantines':True,
            'late_broker_fill_requires_journal_repair':True,
            'native_stop_protected_evidence_only':True,
            'missing_stop_sticky_high_severity':True,
            'late_hazard_keeps_latest_observation_epoch':True,
            'duplicate_audit_idempotent':True,
            'forged_owner_or_fence_rejected':True,
            'durable_audit_events':r.xlen(journal.keys[7]),
            'durable_hazard_outbox':r.xlen(journal.keys[8]),
            'risk_gate':'CLOSED',
            'automatic_commits':0,'automatic_releases':0,
            'resubmits':0,'real_binance_calls':0,
            'production_redis_writes':0,'result':'PASS'},sort_keys=True))
    finally:
        if p is not None:shutdown(p,r)
