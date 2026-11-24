"""Only exact transport parents may join Stage11 pending chain; never ORDER."""
import copy,json,subprocess,sys
from pathlib import Path
from research.trace.long1_stage22_pending_decision_chain_audit_v1 import audit_pairs,observe
from research.trace.test_long1_stage19_decision_evidence_join_v1 import WithTrace
from research.trace.test_long1_stage18_forward_only_v1 import Stub,data,baseline
from research.trace.long1_stage18_forward_only_source_audit_v1 import initial_state
ROOT=Path(__file__).resolve().parents[2]
def trace(*,intent,stage,action,ts,attempt='pending-test-1',origin='',new='',
          count=0,context=False,candle=False):
 return dict(schema='long1_entry_decision_audit.v1',source='ACTUAL_EXECUTOR_DECISION',
 symbol='NEARUSDT',side='long',intent_id=intent,stage=stage,action=action,
 ts_ms=ts,pending_attempt_id=attempt,pending_origin_intent_id=origin,
 pending_recheck_intent_id=new,pending_recheck_count=count,
 context_valid_asof=context,five_minute_recovered=context,
 fresh_intent_verified=context,
 market_context_3m_5m_recovery_verified=context,
 decision_candle_identity_verified=candle,advisory_only=True,order_authority=False)
origin=trace(intent='old-intent',stage='pending_store',action='pending',ts=100)
new=trace(intent='new-intent',stage='pending_recheck',action='ready',ts=200,
 origin='old-intent',new='new-intent',count=1)
contra=trace(intent='new-intent',stage='contra_trend',action='ready',ts=220,
 origin='old-intent',new='new-intent',count=1,context=True)
rows=[('1000-0',origin),('2000-0',new),('2200-0',contra)]
r=audit_pairs(trace_rows=rows,exact_new_intents={'old-intent','new-intent'})
assert r['pending_attempts_seen']==1 and r['pairs_with_diagnostic_identity_only']==1
assert 'NATIVE_CANDLE_IDENTITY_NOT_PROVEN' in r['reason_counts']
assert 'RISK_MASTER_FINAL_SAFETY_NOT_PROVEN' in r['reason_counts']
assert r['risk_master_live_order_authority_count']==0
# Plausible source/candle self-claims never provide independent live authority.
r2=audit_pairs(trace_rows=[(k,dict(v,decision_candle_identity_verified=True)) for k,v in rows],
 exact_new_intents={'old-intent','new-intent'})
assert r2['pairs_with_diagnostic_identity_only']==1 and r2['risk_master_live_order_authority_count']==0
def modified(*,index=1,field,value,accepted={'old-intent','new-intent'}):
 t=copy.deepcopy(rows)
 t[index][1][field]=value
 return audit_pairs(trace_rows=t,exact_new_intents=accepted)
assert modified(field='pending_origin_intent_id',value='other')['reason_counts']['PENDING_ORIGIN_CHANGED']==1
assert modified(field='pending_recheck_intent_id',value='other')['reason_counts']['RECHECK_INTENT_FIELD_MISMATCH']==1
assert modified(field='intent_id',value='old-intent')['reason_counts']['OLD_INTENT_REUSED']==1
assert modified(field='ts_ms',value=100)['reason_counts']['NOT_FRESH_AFTER_ORIGIN']==1
assert modified(field='pending_recheck_count',value=None)['reason_counts']['INVALID_RECHECK_COUNT']==1
assert modified(field='pending_attempt_id',value='other')['reason_counts']['MISSING_ATTEMPT_ID']==1
assert modified(field='advisory_only',value=False)['reason_counts']['INVALID_TRACE_SCHEMA_OR_PROVENANCE']==1
assert modified(field='order_authority',value=True)['reason_counts']['INVALID_TRACE_SCHEMA_OR_PROVENANCE']==1
assert audit_pairs(trace_rows=rows,exact_new_intents={'old-intent'})['reason_counts']['RECHECK_INTENT_NOT_EXACT']==1
assert audit_pairs(trace_rows=rows,exact_new_intents={'new-intent'})['reason_counts']['ORIGIN_INTENT_NOT_EXACT']==1
assert audit_pairs(trace_rows=[rows[1]],exact_new_intents={'old-intent','new-intent'})['reason_counts']['ORIGIN_MISSING_OR_AMBIGUOUS']==1
assert audit_pairs(trace_rows=[rows[0]],exact_new_intents={'old-intent','new-intent'})['reason_counts']['RECHECK_MISSING']==1
assert audit_pairs(trace_rows=rows[:2],exact_new_intents={'old-intent','new-intent'})['reason_counts']['CONTRA_RECOVERY_EVIDENCE_NOT_PROVEN']==1
d=copy.deepcopy(rows)
d.append(('2300-0',dict(new,ts_ms=230,pending_recheck_count=1)))
assert audit_pairs(trace_rows=d,exact_new_intents={'old-intent','new-intent'})['reason_counts']['DUPLICATE_RECHECK_COUNT']==1
class TraceReader(Stub):
 def xrevrange(self,name,count=10):
  if name=='telemetry:long1:entry_decision_trace:v1':
   return [(k,{'json':json.dumps(v)}) for k,v in rows]
  return super().xrevrange(name,count=count)
 def xlen(self,name):
  if name=='telemetry:long1:entry_decision_trace:v1':return len(rows)
  return super().xlen(name)
# Stage18 sees new-intent, but origin is only a fake trace, not exact source
snapshot=observe(TraceReader(data),initial_state(baseline),limit=100)
assert snapshot['pending']['exact_new_intent_count']==1
assert snapshot['pending']['reason_counts']['ORIGIN_INTENT_NOT_EXACT']==1
assert snapshot['pending']['live_order_authority_count']==0 if 'live_order_authority_count' in snapshot['pending'] else snapshot['pending']['risk_master_live_order_authority_count']==0
assert not snapshot['live_order_authorized']
cli=subprocess.run([sys.executable,str(ROOT/'research/trace/long1_stage22_pending_decision_chain_audit_v1.py')],capture_output=True,text=True,cwd=ROOT,timeout=8)
assert cli.returncode==0 and 'DISABLED' in cli.stdout
print(json.dumps({'status':'PASS','tamper_parent_origin_attempt_timestamp':True,
 'future_real_intent_pair_not_auto_proven':True,'no_timestamp_heuristic':True,
 'default_off':True,'order_authorized':0},sort_keys=True))
