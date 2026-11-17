from copy import deepcopy
from research.regime.long1_regime_pending_revalidation_v1 import check,PROFILE
o=dict(origin_ms=100000000,close_id=1000)
c=dict(asof_ms=100600000,micro_observed_ms=100595000,
 completed_3m_close_ms=100300000,completed_5m_close_ms=100500000,
 model_close_id=1002,flow15=.30,return_3m=.001,return_5m=.001,
 model_new_proof=True,entry_1m_fresh_support=True)
assert check(o,c)['state']=='SHADOW_REVALIDATED'
assert check(o,c)['orders_authorized'] is False
cases=[
 ('asof_ms',100000000,'REJECT'),
 ('asof_ms',102000001,'REJECT'),
 ('model_close_id',1000,'PENDING'),
 ('micro_observed_ms',100590000-35000,'PENDING'),
 ('micro_observed_ms',100700000,'PENDING'),
 ('completed_3m_close_ms',100000000,'PENDING'),
 ('completed_5m_close_ms',100000000,'PENDING'),
 ('model_new_proof',False,'PENDING'),
 ('entry_1m_fresh_support',False,'PENDING'),
 ('flow15',-.1,'PENDING'),
 ('return_3m',-.001,'PENDING'),
 ('return_5m',-.001,'PENDING'),
 ('flow15',float('nan'),'REJECT')]
for key,val,expect in cases:
 x=deepcopy(c);x[key]=val
 assert check(o,x)['state']==expect,(key,check(o,x))
assert check({},c)['state']=='REJECT'
assert check(o,{})['state']=='PENDING'
assert PROFILE['orders_authorized'] is False
print('PASS 17 fresh-model, elapsed time, 3m5m closed, flow, 1m and no-order assertions')
