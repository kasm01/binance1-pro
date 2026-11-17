from research.regime.long1_market_context_v2_shadow import classify
def mk(a=-.006,b=-.008,c=-.005,d=-.007,f=-.4):
 return dict(return_3m=a,return_5m=b,return_15m=c,return_30m=d,flow15=f,asof_complete=True)
assert classify(mk())['decision']=='VETO_ADVISORY'
assert classify(mk(f=None))['decision']=='VETO_ADVISORY'
assert classify(mk(f=.5))['decision']=='PENDING'
assert classify(mk(a=.002,b=.001,c=.002,d=.001,f=.3))['decision']=='READY_CANDIDATE'
assert classify(mk(a=.002,b=.001,c=.002,d=.001,f=None))['decision']=='PENDING'
assert classify(mk(a=-.003,b=-.001,c=-.002,d=-.002,f=-.1))['decision']=='PENDING'
assert classify(mk(a=.001,b=-.022,c=-.013,d=-.018,f=.5))['decision']=='PENDING'
assert classify(mk(a=float('nan')))['regime']=='UNKNOWN'
assert classify(None)['regime']=='UNKNOWN'
assert classify(dict(mk(),asof_complete=False))['decision']=='PENDING'
assert classify(dict(mk(),human_label='LONG_WANTED',timestamp='2026-11-14T17:06'))==classify(mk())
assert all(not classify(x)['orders_authorized'] for x in (mk(),mk(f=None),mk(f=.5),None))
print('PASS 12 causal V2 research policy checks')
