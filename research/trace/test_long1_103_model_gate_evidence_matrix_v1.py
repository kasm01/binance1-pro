from pathlib import Path
from collections import Counter
import json
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_103_REAL_MODEL_GATE_EVIDENCE_MATRIX_20261124.json').read_text())
assert x['archived_model_observations']==103
assert x['research_ready_no_live_order_authority']==32
assert x['historical_intents_not_proven']==285
assert x['historical_exact_source_intent_chain_count']==0
assert x['stage18_run_on_current_turn_new_intents']==0
assert x['two_avoidable_research_loss_examples_same_minute_model_events']==2
assert x['two_same_minute_model_decisions']==[['CONTRA_WAIT_30M'],['CONTRA_WAIT_30M']]
assert x['no_new_orders'] and x['redis_writes']==0
assert x['hindsight_labels_not_signal_features']
assert x['fresh_103_source_lineage_unproven']
assert x['no_entry_or_contra_production_modification']
assert len(x['model_event_rows'])==103
assert sum(x['stage13_research_decisions'].values())==103
assert sum(sum(v.values()) for v in x['by_hindsight_reference'].values())==103
for e in x['model_event_rows']:
 assert not e['actual_new_intent_parent_verified']
 assert not e['actual_order_authority_verified']
 assert not e['actual_whale_live_context_verified']
 assert e['next_action'] in ('NO_ORDER_AUTHORITY','RESEARCH_BLOCK_OR_PENDING')
assert sum(e['research_was_ready'] for e in x['model_event_rows'])==32
assert sum(e['research_contra_pending'] for e in x['model_event_rows'])==29
assert sum(e['research_entry_pending_expired'] for e in x['model_event_rows'])==40
print(json.dumps({'status':'PASS','model_events':103,'no_real_intent_parent':103,
 'actual_order_authorizations':0,'production_writes':0},sort_keys=True))
