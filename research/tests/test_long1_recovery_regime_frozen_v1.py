from copy import deepcopy
from research.long1_recovery_regime_frozen_v1 import assess,FROZEN_PROFILE
example=dict(score=.4955,flow15=.4,one_min_support=True,
  shadow_record_present=True,all_shadow_checks={'whale_ok':True},
  price_features=dict(return_3m=.003,return_5m=.002,
   return_9m=.004,return_15m=.001,
   three_m_higher_low=True,five_m_higher_low=True))
a=assess(example)
assert a['status']=='SHADOW_READY_CANDIDATE'
assert not a['order_authorized'] and not a['production_authorized']
for feature,value in [('score',.494),('flow15',-.2),('one_min_support',False),('shadow_record_present',False)]:
 v=deepcopy(example);v[feature]=value
 assert assess(v)['status']!='SHADOW_READY_CANDIDATE',feature
for feature,value in [('return_3m',0),('return_5m',-.01),('return_9m',0),('return_15m',0),('three_m_higher_low',False),('five_m_higher_low',False)]:
 v=deepcopy(example);v['price_features'][feature]=value
 assert assess(v)['status']!='SHADOW_READY_CANDIDATE',feature
v=deepcopy(example);v['score']=float('nan')
assert assess(v)['status']=='REJECT'
v=deepcopy(example);v['all_shadow_checks']={}
assert assess(v)['status']=='PENDING'
v=deepcopy(example);v['price_features']=None
assert assess(v)['status']=='REJECT'
# Must be label-and-time independent: same features, any user label/time.
v=deepcopy(example);v.update(wanted='',avoid='do_not_trade',local_ts='2026-11-15T06:45+03:00')
assert assess(v)==a
assert FROZEN_PROFILE['research_only'] and not FROZEN_PROFILE['production_authorized']
print('PASS 16 invariant and fail-closed assertions, no label/time inputs, no order authority')
