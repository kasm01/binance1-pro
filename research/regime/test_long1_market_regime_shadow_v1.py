from research.regime.long1_market_regime_shadow_v1 import classify,PROFILE
sample=dict(return_3m=-.001,return_5m=-.002,return_15m=-.003,
 return_30m=-.004,flow15=-.5,asof_complete=True)
assert classify(sample)['regime']=='BEARISH'
assert classify(sample)['advisory']=='VETO_LONG'
sample=dict(return_3m=.002,return_5m=.003,return_15m=.004,return_30m=-.002,
 flow15=.45,asof_complete=True)
assert classify(sample)['regime']=='RECOVERY'
sample['return_30m']=.004
assert classify(sample)['advisory']=='RESEARCH_CANDIDATE'
sample['flow15']=-.40
assert classify(sample)['regime']=='UNCERTAIN'
for data in ({},dict(return_3m=float('nan')),None):
 assert classify(data)['regime']=='UNKNOWN'
sample['flow15']=.4;sample['asof_complete']=False
assert classify(sample)['regime']=='UNKNOWN'
sample['asof_complete']=True
assert classify(dict(sample,desired='LONG_TARGET',date='2026-11-15'))==classify(sample)
assert not PROFILE['orders_authorized']
print('PASS causal no-label, no-order, bearish, recovery, unknown tests')
