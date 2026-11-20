"""Actual Stage6/7 pure parent functions, old pending provenance, no IO."""
from copy import deepcopy
from orchestration.trace.long1_lineage_v1 import MODEL_CLOSE_KIND,candidate_parent
from orchestration.trace.long1_candidate_intent_lineage_v1 import candidate_intent_parent
from orchestration.trace.long1_execution_lineage_v1 import new_pending_origin,preserve_pending_origin
from orchestration.trace.long1_fresh_intent_source_chain_v1 import exact_new_chain,research_fresh_reentry
import json
SIGNAL_STREAM='signals_stream_long1'
CANDIDATE_STREAM='candidates_stream_long1'
s={'symbol':'NEARUSDT','side_candidate':'long','producer_id':'heavy_engine',
 'event_id':'signal-new','model_evaluation_id':'eval-new',
 'model_close_id':1794706000,'model_close_id_kind':MODEL_CLOSE_KIND}
c={'candidate_id':'candidate-new','symbol':'NEARUSDT','side':'long'}
c.update(candidate_parent(s,SIGNAL_STREAM,'1794706000000-0'))
it={'symbol':'NEARUSDT','side':'long','intent_id':'intent-new'}
it.update(candidate_intent_parent(candidate=dict(c,_source_stream_id='1794706001000-0'),
 candidate_stream=CANDIDATE_STREAM))
args=dict(signal=s,signal_stream=SIGNAL_STREAM,signal_stream_id='1794706000000-0',
 candidate=c,candidate_stream=CANDIDATE_STREAM,
 candidate_stream_id='1794706001000-0',intent=it,
 origin_model_evaluation_id='eval-old',origin_intent_id='intent-old')
ok=exact_new_chain(**args)
assert ok['source_chain_exact'] and not ok['real_order_authorized']
failures=[
 {'signal':dict(s,model_evaluation_id='eval-old')},
 {'intent':dict(it,intent_id='intent-old')},
 {'signal_stream_id':'1794706000000-9'},
 {'candidate_stream_id':'1794706001000-9'},
 {'candidate':dict(c,parent_trace_id='long1:forged')},
 {'candidate':dict(c,model_evaluation_id='eval-forged')},
 {'candidate':dict(c,source_signal_stream_id='1794706000000-9')},
 {'intent':dict(it,parent_trace_id='long1:bad')},
 {'intent':dict(it,source_candidate_stream_id='1794706001000-9')},
 {'intent':dict(it,model_evaluation_id='eval-forged')},
 {'signal':dict(s,producer_id='unknown')},
 {'candidate':dict(c,symbol='INJUSDT')},
 {'intent':dict(it,side='short')},
 {'intent':{k:v for k,v in it.items() if k!='source_candidate_id'}},
 {'candidate':{k:v for k,v in c.items() if k!='model_evaluation_id'}},
]
for j,delta in enumerate(failures):
 test=exact_new_chain(**dict(args,**delta))
 assert not test['source_chain_exact'] and not test['real_order_authorized'],j
old={'symbol':'NEARUSDT','side':'long',
 'intent_id':'intent-old','model_evaluation_id':'eval-old'}
old.update(new_pending_origin(old))
new=dict(it,model_evaluation_id='eval-new')
merged=preserve_pending_origin(old,new)
merged.update(symbol='NEARUSDT',side='long')
assert merged['pending_origin_intent_id']=='intent-old'
assert merged['pending_recheck_intent_id']=='intent-new'
assert merged['pending_attempt_id']==old['pending_attempt_id']
evidence=dict(
 origin_closed_3m_ms=1800000000000,new_closed_3m_ms=1800000180000,
 new_closed_5m_ms=1800000300000,observed_at_ms=1800000360000,
 closed_3m_source_verified=True,closed_5m_source_verified=True,
 contra_recovery_3m5m_confirmed=True,new_1m_sniper_pass=True,
 new_1m_entry_confirmation_pass=True,original_pending_expired=True,
 no_conflicting_window=True,broker_position_flat_verified=True,
 shared_risk_permission=True)
joined=research_fresh_reentry(origin=old,recheck=merged,evidence=evidence,
 **{k:v for k,v in args.items() if not k.startswith('origin_')})
assert joined['source_chain']['source_chain_exact']
assert joined['reentry_provenance']['provenance_complete']
assert not joined['real_order_authorized']
assert not joined['reentry_provenance']['live_order_authorized']
for changed in failures:
 altered={k:v for k,v in args.items() if not k.startswith('origin_')}
 altered.update(changed)
 r=research_fresh_reentry(origin=old,recheck=merged,evidence=evidence,**altered)
 assert r['reentry_provenance']['status']=='NO_GO'
# A stale expiration false remains NO_GO even when source chain is valid
bad=research_fresh_reentry(origin=old,recheck=merged,
 evidence=dict(evidence,original_pending_expired=False),
 **{k:v for k,v in args.items() if not k.startswith('origin_')})
assert bad['reentry_provenance']['status']=='NO_GO'
print(json.dumps({'status':'PASS','actual_stage6_stage7_parent_funcs':True,
 'source_tamper_cases':len(failures),'expired_pending_fail_closed':True,
 'intent_model_reused_rejected':True,'full_source_proof_grants_real_order':False,
 'production_redis_writes':0,'exchange_orders':0},sort_keys=True))
