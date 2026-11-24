import tempfile,unittest
from pathlib import Path
from scanner.early_revalidation_shadow_v1 import revalidate
from scanner.watch_outcomes_v1 import OutcomeLedger
from scanner.extreme_momentum_v1 import MS
START=1800000000000-(1800000000000%MS)
EVENT={'symbol':'TESTUSDT','direction':'LONG','reference_close_ms':START,
       'reference_price':10.0}
def bars(direction='LONG',taker_share=.7,step=.002):
 p=10.;out=[]
 for i in range(-65,6):
  o=p;p*=1+(step if direction=='LONG' else -step)
  out.append({'t':START+i*MS,'o':o,'h':max(p,o)*1.0002,
     'l':min(p,o)*.9998,'c':p,'quote_volume':1000.,
     'taker_buy_quote_volume':taker_share*1000})
 return out
class Test(unittest.TestCase):
 def test_continue_observe_is_never_entry_ready(self):
  b=bars()
  for p in (1,3,5):
   x=revalidate(EVENT,b,checkpoint=p)
   assert x['state']=='CONTINUE_OBSERVE',x
   assert x['ready'] is False and x['order_authorized'] is False
 def test_invalidate_adverse_origin(self):
  b=bars(step=-.005,taker_share=.35)
  x=revalidate(EVENT,b,checkpoint=3)
  assert x['state']=='INVALIDATE_RESEARCH',x
 def test_future_leakage_impossible(self):
  b=bars()
  first=revalidate(EVENT,b,checkpoint=1)
  mod=list(b)
  mod[-1]=dict(mod[-1],c=300,h=300)
  assert revalidate(EVENT,mod,checkpoint=1)==first
 def test_gap_and_missing_taker_fail_closed(self):
  b=bars();b[-4]=dict(b[-4],t=b[-4]['t']-MS)
  assert revalidate(EVENT,b,checkpoint=5)['state']=='REVALIDATION_UNVERIFIED'
  b=bars();b[-2].pop('taker_buy_quote_volume')
  assert revalidate(EVENT,b,checkpoint=5)['state']=='PENDING_RECHECK'
  assert revalidate(EVENT,b[:-3],checkpoint=5)['state']=='REVALIDATION_UNVERIFIED'
 def test_ledger_restart_saves_checkpoints_and_no_trade(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'early.json';a=OutcomeLedger(p)
   early={'state':'EARLY_CANDIDATE_SHADOW','symbol':'TESTUSDT',
    'direction':'LONG','last_completed_1m_close_ms':START,
    'ready':False,'telegram_ready':False,'order_authorized':False}
   assert a.observe_early('TESTUSDT','LONG',early,
      reference_close_ms=START,reference_price=10.)=='OBSERVED'
   b=bars()
   assert a.revalidate_early('TESTUSDT',b[:-4],last_close_ms=START+2*MS)==1
   assert set(a.events[0]['revalidation_checkpoints'])=={'1'}
   restore=OutcomeLedger(p)
   assert restore.revalidate_early('TESTUSDT',b,last_close_ms=START+6*MS)==2
   checks=restore.events[0]['revalidation_checkpoints']
   assert set(checks)=={'1','3','5'}
   assert all(x['ready'] is False and x['order_authorized'] is False for x in checks.values())
   assert restore.events[0]['trade_executed'] is False
   assert sum(restore.summary()['revalidation_state_counts_by_minute']['1'].values())==1
   assert sum(restore.summary()['revalidation_state_counts_by_minute']['3'].values())==1
   assert sum(restore.summary()['revalidation_state_counts_by_minute']['5'].values())==1
if __name__=='__main__':unittest.main()
