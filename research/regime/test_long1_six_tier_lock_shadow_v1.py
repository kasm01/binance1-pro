from research.regime.long1_six_tier_lock_shadow_v1 import LockState,update,TIERS
assert len(TIERS)==6
state=LockState()
assert update(state,.59,100)['active_tier']==0
assert update(state,.60,200)['active_tier']==1
assert abs(state.floor-.50)<1e-9
assert update(state,.94,300)['active_tier']==1
assert abs(state.floor-.84)<1e-9
assert update(state,.95,400)['active_tier']==2
assert abs(state.floor-.84)<1e-9   # never reduce original floor .84
assert update(state,1.20,500)['active_tier']==3
assert abs(state.floor-1.05)<1e-9
assert update(state,1.65,600)['active_tier']==4
assert abs(state.floor-1.45)<1e-9
assert update(state,2.00,700)['active_tier']==5
assert abs(state.floor-1.80)<1e-9
assert update(state,2.50,800)['active_tier']==6
assert abs(state.floor-2.30)<1e-9
assert update(state,2.35,900)['state']=='SHADOW_HOLD'
assert update(state,2.30,1000)['state']=='SHADOW_TRAIL_TRIGGER'
assert state.tier==5
print('PASS six tiers, monotonic ROI floor, activation, retrace without trade authority')
