from pathlib import Path
import json,subprocess,sys
from research.trace.long1_stage19_decision_evidence_join_v1 import (
    classify,correlate,observe,resolve_new_exact_intents)
from research.trace.test_long1_stage18_forward_only_v1 import Stub,baseline,data
from research.trace.long1_stage18_forward_only_source_audit_v1 import initial_state
ROOT=Path(__file__).resolve().parents[2]
def tr(**over):
 d=dict(schema='long1_entry_decision_audit.v1',source='ACTUAL_EXECUTOR_DECISION',
        symbol='NEARUSDT',side='long',intent_id='intent-new',
        advisory_only=True,order_authority=False,
        decision_candle_identity_verified=False,
        stage='entry_confirmation',action='open')
 d.update(over)
 return d
assert classify(source_exact=False,record=tr(),expected_intent_id='intent-new')=='NO_EXACT_SOURCE_PARENT'
assert classify(source_exact=True,record=None,expected_intent_id='intent-new')=='TRACE_MISSING'
assert classify(source_exact=True,record=tr(intent_id='another'),expected_intent_id='intent-new')=='TRACE_INTENT_NOT_EXACT'
assert classify(source_exact=True,record=tr(order_authority=True),expected_intent_id='intent-new')=='TRACE_PRIVILEGE_INVALID'
assert classify(source_exact=True,record=tr(),expected_intent_id='intent-new')=='TRACE_INTENT_EXACT_CANDLE_UNPROVEN'
assert classify(source_exact=True,record=tr(decision_candle_identity_verified=True),expected_intent_id='intent-new')=='TRACE_INTENT_EXACT_INDEPENDENT_CANDLE_PROOF_MISSING'
assert classify(source_exact=True,record=tr(stage='contra_trend',action='ready',decision_candle_identity_verified=True,market_context_3m_5m_recovery_verified=False),expected_intent_id='intent-new')=='RECOVERY_NOT_PROVEN'
a=correlate(exact_intents=['intent-new'],trace_rows=[('100-0',tr()),('101-0',tr(intent_id='unrelated')),('102-0',tr(action='pending'))])
assert a['intents_with_trace']==1 and a['full_order_authority_proven']==0
assert a['intent_reason_counts']['TRACE_INTENT_EXACT_CANDLE_UNPROVEN']==2
assert a['trace_records_discarded_reason']['TRACE_INTENT_NOT_IN_EXACT_SOURCE_SET']==1
class WithTrace(Stub):
 def xrevrange(self,name,count=10):
  if name=='telemetry:long1:entry_decision_trace:v1':
   return [('1794707004000-0',{'json':json.dumps(tr())})]
  return super().xrevrange(name,count=count)
 def xlen(self,name):
  if name=='telemetry:long1:entry_decision_trace:v1':return 1
  return super().xlen(name)
live=observe(WithTrace(data),initial_state(baseline),limit=100)
assert live['stage18_source_chain_counts']=={'EXACT_SOURCE_ONLY_NO_ORDER_AUTHORITY':1}
assert live['stage18_new_intent_batches']==1
assert live['entry_trace_stream_length']==1
assert live['trace']['exact_source_intent_count']==1
assert live['trace']['intents_with_trace']==1
assert live['trace']['intent_reason_counts']=={'TRACE_INTENT_EXACT_CANDLE_UNPROVEN':1}
assert not live['order_authority'] and live['redis_writes']==0
# Identity tamper must downgrade exact source even if trace says OPEN.
import copy
tampered=copy.deepcopy(data)
tampered['trade_intents_stream_long1'][-1][1]['items'][0]['parent_trace_id']='wrong_parent'
invalid=observe(WithTrace(tampered),initial_state(baseline),limit=100)
assert invalid['trace']['exact_source_intent_count']==0
assert invalid['trace']['intents_with_trace']==0
assert not invalid['order_authority']
# Duplicate intent IDs do not become 'two fresh events' / cannot auto-promote.
dup=copy.deepcopy(data)
dup['trade_intents_stream_long1'][-1][1]['items'].append(copy.deepcopy(dup['trade_intents_stream_long1'][-1][1]['items'][0]))
ids,proof=resolve_new_exact_intents(Stub(dup),initial_state(baseline),limit=100)
assert not ids and proof['ambiguous_duplicate_intent_ids_rejected']==1

result=subprocess.run([sys.executable,str(ROOT/'research/trace/long1_stage19_decision_evidence_join_v1.py')],cwd=ROOT,capture_output=True,text=True,timeout=8)
assert result.returncode==0 and 'DISABLED' in result.stdout
print(json.dumps({'status':'PASS','stage18_source_exact_can_be_observed':1,
 'stage19_no_unsafe_parent_promotion':True,'unmatched_trace_blocked':True,
 'closed_candle_unproven':True,'default_no_io':True,'real_orders':0},sort_keys=True))
