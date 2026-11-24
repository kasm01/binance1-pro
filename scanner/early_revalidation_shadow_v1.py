"""1/3/5-minute post-WATCH revalidation: research only, no READY or Telegram.

The snapshot MUST be measured at a completed future close; no forward data.
Checkpoint classification is NOT an executable buy/sell signal.
"""
from __future__ import annotations
from scanner.extreme_momentum_v1 import MS,number
from scanner.taker_flow_quality_shadow_v1 import assess_flow

CHECKPOINTS=(1,3,5)

def revalidate(event,bars,*,checkpoint):
 result={'schema':'early_revalidation_shadow.v1','checkpoint_min':checkpoint,
   'state':'PENDING_RECHECK','reason':'not_evaluated',
   'ready':False,'telegram_ready':False,'order_authorized':False,
   'advisory_only':True}
 if checkpoint not in CHECKPOINTS:
  result.update(state='REVALIDATION_UNVERIFIED',reason='unsupported_checkpoint');return result
 if (not isinstance(event,dict) or event.get('direction') not in ('LONG','SHORT') or
     type(event.get('reference_close_ms')) is not int):
  result.update(state='REVALIDATION_UNVERIFIED',reason='invalid_origin');return result
 ref=number(event.get('reference_price'))
 if ref is None or ref<=0:
  result.update(state='REVALIDATION_UNVERIFIED',reason='bad_reference_price');return result
 target=event['reference_close_ms']+checkpoint*MS
 if not isinstance(bars,list) or not bars:
  result.update(state='REVALIDATION_UNVERIFIED',reason='missing_history');return result
 # Explicitly slice to target close, so the later 5m bar cannot affect a 1m decision.
 prefix=[r for r in bars if isinstance(r,dict) and type(r.get('t')) is int
         and r['t']+MS<=target]
 if not prefix or prefix[-1]['t']+MS!=target:
  result.update(state='REVALIDATION_UNVERIFIED',reason='checkpoint_not_closed');return result
 future=[r for r in prefix if event['reference_close_ms']<=r['t']<target]
 if len(future)!=checkpoint or any(r['t']!=event['reference_close_ms']+i*MS
                                   for i,r in enumerate(future)):
  result.update(state='REVALIDATION_UNVERIFIED',reason='future_gap_or_duplicate');return result
 for r in future:
  o=number(r.get('o'));h=number(r.get('h'));l=number(r.get('l'));c=number(r.get('c'))
  if None in (o,h,l,c) or min(o,h,l,c)<=0 or l>min(o,c) or h<max(o,c,l):
   result.update(state='REVALIDATION_UNVERIFIED',reason='invalid_ohlc');return result
 sign=1 if event['direction']=='LONG' else -1
 close=future[-1]['c']
 directional_close=sign*100*(close/ref-1)
 if sign==1:
  adverse=100*(min(r['l'] for r in future)/ref-1)
  favorable=100*(max(r['h'] for r in future)/ref-1)
 else:
  adverse=100*(1-max(r['h'] for r in future)/ref)
  favorable=100*(1-min(r['l'] for r in future)/ref)
 # This is aggressor flow measured AT THE checkpoint (not at origin).
 flow=assess_flow(prefix,event['direction'],observed_at_ms=target)
 result.update(directional_terminal_pct=round(directional_close,4),
   adverse_excursion_pct=round(adverse,4),
   favorable_excursion_pct=round(favorable,4),
   checkpoint_close_ms=target,flow_state=flow['state'],
   directional_taker_imbalance_3m=flow.get('directional_taker_imbalance_3m'))
 if flow['state']=='FLOW_UNVERIFIED':
  result.update(state='PENDING_RECHECK',reason='taker_data_not_verified')
 elif (directional_close<=-.40 and adverse<=-.50) or (
       flow['state']=='FLOW_OPPOSING' and directional_close<=-.15):
  result.update(state='INVALIDATE_RESEARCH',reason='early_adverse_move_and_or_opposing_flow')
 elif (directional_close>=.20 and adverse>-.50 and
       flow['state']=='FLOW_SUPPORTIVE'):
  result.update(state='CONTINUE_OBSERVE',reason='direction_and_taker_flow_still_aligned')
 else:
  result.update(state='PENDING_RECHECK',reason='mixed_price_path_or_taker_pressure')
 return result
