"""Read-only evidence matrix: real archived MODEL versus research gate decisions.

Inputs previously produced research outputs only; NO order authority. Four
critical distinctions: archived real MODEL != actual order, research READY
!= live Entry READY, temporal proximity != parent ID lineage,
historical reference WANTED/AVOID != live signal input.
"""
from pathlib import Path
from collections import Counter,defaultdict
import json
R=Path(__file__).resolve().parents[2];O=R/'research/results'
stage=json.loads((O/'LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
retained=json.loads((O/'LONG1_STAGE17_RETAINED_SOURCE_CHAIN_READONLY_20261120.json').read_text())
forward=json.loads((O/'LONG1_STAGE18_FORWARD_ONLY_LAST_AUDIT_20261120.json').read_text())
source=json.loads((O/'LONG1_AVOID84_RESEARCH_VS_LIVE_GATE_ATTRIBUTION_20261120.json').read_text())
events=stage['events'];assert len(events)==103
counts=Counter(v['decision'] for v in events)
assert dict(counts)=={'RESEARCH_READY_NO_REAL_INTENT':32,'ENTRY_PENDING_EXPIRED':40,
 'CONTRA_WAIT_30M':29,'MODEL_GATE':1,'CONFLICT_ORIGIN':1}
assert retained['counts']=={'NOT_PROVEN':285}
assert retained['records_read']=={'candidates_stream_long1':894,'signals_stream_long1':2473,'trade_intents_stream_long1':285}
assert forward['new_intent_batch_records']==0
matrix=[]
for event in events:
 d=event['decision'];label=event['label']
 matrix.append({'model_time_tr':event['model_time_tr'],
   'retrospective_label_only':label,
   'research_stage13_gate_decision':d,
   'model_score_gate_pass_research':event['model_score_pass'],
   'research_was_ready':d=='RESEARCH_READY_NO_REAL_INTENT',
   'research_entry_pending_expired':d=='ENTRY_PENDING_EXPIRED',
   'research_contra_pending':d=='CONTRA_WAIT_30M',
   'actual_new_intent_parent_verified':event.get('actual_new_intent_verified',False),
   'actual_partial_1m_entry_ready_verified':event.get('partial_1m_entry_verified',False),
   'actual_whale_live_context_verified':event.get('true_whale_market_context_reproduced',False),
   'actual_order_authority_verified':event.get('actual_trade_authorized',False),
   'risk_master_and_broker_fill_not_reproduced':True,
   'next_action':'NO_ORDER_AUTHORITY' if d=='RESEARCH_READY_NO_REAL_INTENT' else 'RESEARCH_BLOCK_OR_PENDING'})
assert all(not z['actual_new_intent_parent_verified'] and not z['actual_order_authority_verified'] for z in matrix)
byref=defaultdict(Counter)
for r in matrix:byref[r['retrospective_label_only']][r['research_stage13_gate_decision']]+=1
avoid_synth_matches=[t for t in source['fixed_tp035_losing_details'] if t['same_minute_archived_model_events']>0]
assert len(avoid_synth_matches)==2
assert all(t['same_minute_model_decisions']==['CONTRA_WAIT_30M'] for t in avoid_synth_matches)
out={'schema':'long1_archived103_real_model_gate_evidence_and_source_lineage_v1',
 'archived_model_observations':103,
 'stage13_research_decisions':dict(counts),
 'by_hindsight_reference':{k:dict(v) for k,v in byref.items()},
 'research_ready_no_live_order_authority':32,
 'historical_intent_stream_length':285,
 'historical_signal_stream_length':2473,
 'historical_candidate_stream_length':894,
 'historical_exact_source_intent_chain_count':0,
 'historical_intents_not_proven':285,
 'stage18_last_archived_baseline_intent_id':forward['baseline_stream_ids']['trade_intents_stream_long1'],
 'stage18_last_archived_forward_new_intents':0,
 'stage18_run_on_current_turn_new_intents':0,
 'stage18_current_turn_cli_invocation':'--audit-forward --max-records 3000 WITHOUT --advance; Redis read only; same baseline and 0 new intents',
 'two_avoidable_research_loss_examples_same_minute_model_events':len(avoid_synth_matches),
 'two_same_minute_model_decisions':[t['same_minute_model_decisions'] for t in avoid_synth_matches],
 'research_recovery_not_actual_live_gate_reconstruction':True,
 'fresh_103_source_lineage_unproven':True,
 'hindsight_labels_not_signal_features':True,
 'actual_order_open_count_in_this_study':0,
 'no_model_score_threshold_change':True,
 'no_entry_or_contra_production_modification':True,
 'risk_master_final_safety_not_bypassed':True,
 'no_new_orders':True,'redis_writes':0,
 'live_services_not_started':True,
 'no_paid_external_market_requests':True,
 'model_event_rows':matrix}
p=O/'LONG1_103_REAL_MODEL_GATE_EVIDENCE_MATRIX_20261124.json'
p.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'status':'PASS','total':103,'decisions':dict(counts),
 'by_research_label':{k:dict(v) for k,v in byref.items()},
 'historic_verified_intents':0,'new_verified_intents':0,
 'real_orders':0},sort_keys=True))
