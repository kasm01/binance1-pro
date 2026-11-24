"""Stage21 no-lookahead, multi-horizon flow veto, and no fake provenance."""
from pathlib import Path
import json
from research.trace.long1_stage21_context_flow_pending_evidence_v1 import (
 load_flow,window_at,context_diagnostic,status_fresh)
from research.trace.long1_stage20_closed_candle_pending_shadow_v1 import (
 load_archive,completed_asof)
R=Path(__file__).resolve().parents[2]
flow=load_flow();bars=load_archive()
assert len(flow)==len(bars)==8640
t=sorted(bars)[5000]
# evaluate at exact 1m open: last 1m candle closed at t-1
d=t
f=window_at(flow,decision_ms=d,minutes=15)
assert f['valid'] and f['close_ms']==t-1
assert f['start_ms']==t-15*60000
f_more=window_at(flow,decision_ms=d+59999,minutes=15)
assert f_more['start_ms']==t-14*60000
f_next=window_at(flow,decision_ms=d+60000,minutes=15)
assert f_next['start_ms']==t-14*60000
missing=flow.copy();missing.pop(t-60000)
assert not window_at(missing,decision_ms=t,minutes=3)['valid']
c3=completed_asof(bars,asof_ms=t,minutes=3)
c5=completed_asof(bars,asof_ms=t,minutes=5)
goodc={'valid':True,'close_ms':t-1,'o':3.0,'c':3.1}
goodf={'valid':True,'close_ms':t-1,'signed_ratio':.1}
neg=dict(goodf,signed_ratio=-.01)
def test(**kw):
 args=dict(c3=goodc,c5=goodc,f3=goodf,f5=goodf,
           f15=goodf,f60=goodf,decision_ms=t)
 args.update(kw);return context_diagnostic(**args)
assert test()=='ARCHIVE_RESEARCH_SUPPORT_ONLY'
assert test(f15=neg)=='15M_60M_CONTEXT_NEGATIVE'
assert test(f60=neg)=='15M_60M_CONTEXT_NEGATIVE'
assert test(f3=neg)=='3M_5M_BUYER_FLOW_WEAK'
assert test(f5=neg)=='3M_5M_BUYER_FLOW_WEAK'
assert test(c5=dict(goodc,c=2.9))=='PRICE_REVERSAL_NOT_SUPPORTED'
assert test(c3={'valid':False})=='MISSING_SOURCE_FAIL_CLOSED'
assert test(f15=dict(goodf,close_ms=t+1))=='FUTURE_DATA_FAIL_CLOSED'
p=status_fresh(orig=t-600000,new=t,observed=t,close3=t-1,close5=t-1)
assert p['status']=='NO_GO' and not p['live_order_authorized']
assert 'exact_parent_chain_not_attested' in p['missing_or_invalid']
assert 'shared_risk_unverified' in p['missing_or_invalid']
x=json.loads((R/'research/results/LONG1_STAGE21_FLOW_CONTEXT_PENDING_PROOF_20261124.json').read_text())
assert x['model_events']==103
assert x['stage13_ready_proxies']==32
assert x['archive_flow_diagnostics']=={'15M_60M_CONTEXT_NEGATIVE':20,
 'PRICE_REVERSAL_NOT_SUPPORTED':12}
assert x['real_order_authority_count']==0
assert x['production_redis_writes']==x['binance_api_calls']==x['additional_services']==0
assert not x['native_pending_origin_and_new_intent_proven']
assert len(x['details'])==103
for row in x['details']:
 assert not row['real_order_authority']
 if row['investigated']:
  assert row['pending_provenance_status']=='NO_GO'
  for h in (3,5,15,60):
   assert row['archive_flow'+str(h)]['close_ms']<=row['research_decision_asof_ms']
print(json.dumps({'status':'PASS','model_count':103,'evaluated':32,'strong_price_weak_broad_flow':20,
 'native_intent_and_risk_blocked':True,'future_data_blocked':True,'orders':0},sort_keys=True))
