"""Stage15 isolated tests: only real pending window classifier, pure provenance."""
from __future__ import annotations
from copy import deepcopy
from unittest.mock import patch
import json,os
from core.trade_executor import TradeExecutor
from orchestration.trace.long1_execution_lineage_v1 import new_pending_origin,preserve_pending_origin
from orchestration.trace.long1_fresh_reentry_validator_v1 import verify_fresh_reentry

def run():
    origin={'symbol':'NEARUSDT','side':'long','intent_id':'old-intent',
        'model_evaluation_id':'model-eval-old','parent_trace_id':'long1:origin'}
    minted=new_pending_origin(origin)
    a=dict(origin,**minted)
    new=dict(origin,intent_id='new-intent',model_evaluation_id='model-eval-new')
    b=preserve_pending_origin(a,new)
    b.update(symbol='NEARUSDT',side='long')
    assert b['pending_origin_intent_id']=='old-intent'
    assert b['pending_recheck_intent_id']=='new-intent'
    assert b['pending_attempt_id']==a['pending_attempt_id']
    evidence={
        'exact_model_signal_candidate_intent_chain':True,
        'fresh_model_evaluation_attested':True,
        'origin_closed_3m_ms':1800000000000,
        'new_closed_3m_ms':1800000180000,
        'new_closed_5m_ms':1800000300000,
        'observed_at_ms':1800000360000,
        'closed_3m_source_verified':True,'closed_5m_source_verified':True,
        'contra_recovery_3m5m_confirmed':True,
        'new_1m_sniper_pass':True,'new_1m_entry_confirmation_pass':True,
        'original_pending_expired':True,'no_conflicting_window':True,
        'broker_position_flat_verified':True,'shared_risk_permission':True}
    good=verify_fresh_reentry(origin=a,recheck=b,evidence=evidence)
    assert good['provenance_complete'] and not good['live_order_authorized']
    scenarios=[
      ('same_intent',dict(b,intent_id='old-intent')),
      ('same_model',dict(b,model_evaluation_id='model-eval-old')),
      ('model_missing',dict(b,model_evaluation_id='')),
      ('origin_changed',dict(b,pending_origin_intent_id='new-intent')),
      ('pending_mismatch',dict(b,pending_attempt_id='pending-invented')),
      ('fresh_intent_not_proven',dict(b,pending_recheck_intent_id='old-intent')),
      ('wrong_symbol',dict(b,symbol='INJUSDT')),
      ('wrong_side',dict(b,side='short'))]
    for name,wrong in scenarios:
      out=verify_fresh_reentry(origin=a,recheck=wrong,evidence=evidence)
      assert out['status']=='NO_GO' and not out['live_order_authorized'],name
    for key in list(evidence):
      if type(evidence[key]) is bool:
        bad=dict(evidence,**{key:False})
      elif key=='observed_at_ms':
        bad=dict(evidence,observed_at_ms=evidence['origin_closed_3m_ms'])
      else:
        bad=dict(evidence,**{key:0})
      out=verify_fresh_reentry(origin=a,recheck=b,evidence=bad)
      assert out['status']=='NO_GO' and not out['live_order_authorized'],key
    # Not even convincing timestamps without proof of exact parentage.
    assert not verify_fresh_reentry(origin=a,recheck=b,
       evidence=dict(evidence,exact_model_signal_candidate_intent_chain=False))['provenance_complete']
    # Real native expired confirmation PENDING cannot be carried to a new 1m candle.
    t=TradeExecutor.__new__(TradeExecutor)
    with patch.dict(os.environ,{'SNIPER_ENTRY_MIN_CANDLE_PROGRESS':'0.05'}):
      for kind in ('confirmation','early'):
        x,age=t._classify_long_pending_window(created_candle_id=1000,
          current_candle_id=1001,progress=.25,max_pending_progress=.6,
          pending_kind=kind)
        assert (x,age)==('expired',1)
      x,age=t._classify_long_pending_window(created_candle_id=1000,
          current_candle_id=1002,progress=.25,max_pending_progress=.6,
          pending_kind='late')
      assert (x,age)==('expired',2)
    return {'status':'PASS','fresh_identity_gate_cases':len(scenarios),
       'evidence_field_failclosed_cases':len(evidence),
       'native_expiry_cases':3,'provenance_grants_order':False,
       'live_orders':0,'prod_redis_writes':0}
if __name__=='__main__':print(json.dumps(run(),sort_keys=True))
