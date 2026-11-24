"""Stage20 offline 3m/5m asof candle and freshness invariants."""
import copy,json,subprocess,sys
from pathlib import Path
from research.trace.long1_stage20_closed_candle_pending_shadow_v1 import (
 load_archive,completed_asof,pending_revalidation,compute)
R=Path(__file__).resolve().parents[2]
bars=load_archive()
assert len(bars)==8640
ts=sorted(bars)
# UTC source timestamps are full 1m bar OPEN; latest UTC 5m close.
anchor=((ts[2500]+300000)//300000)*300000
decision=anchor+60000
c3=completed_asof(bars,asof_ms=decision,minutes=3)
c5=completed_asof(bars,asof_ms=decision,minutes=5)
assert c3['valid'] and c5['valid']
assert c3['close_ms']<=decision and c5['close_ms']<=decision
assert c3['source_1m_count']==3 and c5['source_1m_count']==5
assert not c3['independently_live_exchange_verified']
assert c3['close_ms']==c3['start_ms']+180000-1
assert c5['close_ms']==c5['start_ms']+300000-1
# No future candle, even if observation 1ms before close.
assert completed_asof(bars,asof_ms=c5['close_ms']-1,minutes=5)['close_ms']<c5['close_ms']
assert completed_asof(bars,asof_ms=c5['close_ms'],minutes=5)['close_ms']==c5['close_ms']
# Missing 1m internal source means target 3/5m cannot be declared closed.
bad=bars.copy()
bad.pop(c5['start_ms']+60000)
assert not completed_asof(bad,asof_ms=decision,minutes=5)['valid']
# Tampered source verification cannot pass.
bad=bars.copy()
bad[c3['start_ms']]=dict(bad[c3['start_ms']],source_verified_1m=False)
assert not completed_asof(bad,asof_ms=decision,minutes=3)['valid']
# Force a purely synthetic favorable candle to test identity logic.
up3=dict(c3,valid=True,o=3.0,c=3.1)
up5=dict(c5,valid=True,o=3.0,c=3.1)
origin=min(c3['close_ms'],c5['close_ms'])-600000
def verify(**kw):
 args=dict(origin_ms=origin,decision_ms=decision,
           origin_intent_id='intent-old',recheck_intent_id='intent-new',
           closed3=up3,closed5=up5)
 args.update(kw)
 return pending_revalidation(**args)
yes=verify()
assert yes['status']=='RESEARCH_CANDLE_PROXY_READY_NOT_LIVE'
assert not yes['order_authority'] and not yes['real_intent_parent_verified']
assert verify(recheck_intent_id='intent-old')['reason']=='original_intent_reused'
assert verify(origin_intent_id='')['reason']=='missing_intent_identity'
assert verify(closed3={'valid':False})['reason']=='missing_closed_candle'
assert verify(closed5=dict(up5,close_ms=decision+1))['reason']=='future_candle'
assert verify(origin_ms=min(c3['close_ms'],c5['close_ms']))['reason']=='not_new_closed_3m5m'
assert verify(closed3=dict(up3,c=2.9))['reason']=='proxy_candle_not_up'
assert verify(decision_ms=0)['reason']=='invalid_times'
# Even a positive proxy is NEVER a verified partial 1m Entry or Risk Master.
x=json.loads((R/'research/results/LONG1_STAGE20_ASOF_3M5M_CANDLE_PENDING_EVIDENCE_20261124.json').read_text())
assert x['model_events']==103 and x['source_1m_bars']==8640
assert x['stage13_research_ready_count']==32
assert x['research_3m5m_proxy_reason_counts']=={
 'closed_3m5m_after_origin_on_proxy':20,
 'not_new_closed_3m5m':4,
 'proxy_candle_not_up':8}
assert x['fresh_intent_verified_count']==0
assert x['native_entry_verified_count']==0
assert x['shared_risk_authorized_count']==0
assert x['live_order_authorized_count']==0
assert x['prod_redis_writes']==x['real_orders']==0
assert len(x['research_event_rows'])==103
for e in x['research_event_rows']:
 assert not e['order_authority']
 if e['proxy_evaluable']:
  assert e['archive_3m_closed']['valid']
  assert e['archive_5m_closed']['valid']
  assert e['archive_3m_closed']['close_ms']<=e['research_1m_entry_decision_ms']
  assert e['archive_5m_closed']['close_ms']<=e['research_1m_entry_decision_ms']
  assert not e['research_proxy_revalidation']['order_authority']
print(json.dumps({'status':'PASS','model_events':103,'research_ready':32,
  'research_proxy_up':20,'research_proxy_not_up':8,'not_new_candle_pair':4,
  'candle_future_guard':True,'missing_or_tampered_bar_guard':True,
  'original_intent_reuse_blocked':True,'real_orders':0},sort_keys=True))
