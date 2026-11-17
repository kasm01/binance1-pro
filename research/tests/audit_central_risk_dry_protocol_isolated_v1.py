"""Central dry reservation protocol adversarial TEST using only in-memory FakeRedis.
No live Redis writes, no service restart, no order. Documents current behavior.
"""
import json,time,sys
sys.path.insert(0,'.')
from scripts.central_risk_enforce_dry_service import _handle,RESERVATION_HASH,SNAPSHOT_KEY
class FakeRedis:
    def __init__(self,equity=100):
        self.s={SNAPSHOT_KEY:json.dumps(dict(ts=time.time(),
          exposure_health=dict(status='OK',freeze_new_entries=False),
          account=dict(mtm_equity=equity),portfolio_state=dict(equity_peak=equity,mode='NORMAL',recovery_successes=0),
          positions=[]))}
        self.h={}
    def get(self,key):return self.s.get(key)
    def hgetall(self,key):return self.h.get(key,{}).copy()
    def hset(self,key,field,value):self.h.setdefault(key,{})[field]=value
    def hdel(self,key,field):
        target=self.h.setdefault(key,{})
        val=1 if field in target else 0
        target.pop(field,None)
        return val
def request(id,strategy='LONG1',symbol='NEARUSDT',action='EVALUATE_OPEN',**kw):
    return dict(request_id=id,request_mode='DRY_RUN',action=action,strategy_id=strategy,
      symbol=symbol,side='long' if strategy=='LONG1' else 'short',
      market_context_multiplier=1.0,reserve=True,**kw)
r=FakeRedis()
a=_handle(r,request('r1'))
assert a['state']=='READY'
original=json.loads(r.h[RESERVATION_HASH]['LONG1'])
# Current API has no idempotent journal: duplicate request is refused due existing reservation.
duplicate=_handle(r,request('r1'))
# RELEASE has no ownership token, even when supplied request_mode='LIVE'
bad=_handle(r,dict(action='RELEASE',request_mode='LIVE',strategy_id='LONG1',request_id='unowned'))
remaining_after_bad='LONG1' in r.h[RESERVATION_HASH]
# A second open after unauthorized release is re-approved
again=_handle(r,request('r2'))
# A late release by first intent can release second intent reservation.
late=_handle(r,dict(action='RELEASE',request_mode='DRY_RUN',strategy_id='LONG1',request_id='r1'))
remaining_after_late='LONG1' in r.h[RESERVATION_HASH]
# Short opens from the same shared capital snapshot with a new slot.
short=_handle(r,request('s1',strategy='SHORT1',symbol='INJUSDT'))
print(json.dumps(dict(
  first=dict(state=a['state'],allowed=a['decision']['allowed_notional'],owner=original['request_id']),
  replay_same_request=dict(state=duplicate['state'],reason=duplicate['decision']['reason_codes']),
  release_live_unowned=dict(state=bad['state'],released=not remaining_after_bad),
  open_after_unowned_release=dict(state=again['state'],owner=json.loads(r.h[RESERVATION_HASH]['SHORT1'])['request_id'] if 'LONG1' not in r.h[RESERVATION_HASH] else 'LONG1'),
  release_old_after_new=dict(state=late['state'],new_reservation_still_there=remaining_after_late),
  short_independent_budget=dict(state=short['state'],allowed=short['decision']['allowed_notional']),
  protocol_has_commit_action=False,
  risk='dryrun_only_PRODUCTION_NOT_AUTHORIZED'
),indent=2))
assert duplicate['state']=='REJECT'
assert not remaining_after_bad
assert not remaining_after_late
assert short['state']=='READY'
print('PASS isolated reproduction of unowned RELEASE, stale RELEASE, and non-idempotent duplicate request')
