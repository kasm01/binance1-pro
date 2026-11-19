"""Cross-validate retained MODEL/intent clock audit; no order permission."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_STAGE14_FRESH_INTENT_AND_11_AVOID_AUDIT_20261119.json').read_text())
s=json.loads((R/'research/results/LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
assert x['model_events']==103 and len(x['events'])==103
assert x['stage13_ready']==32 and x['source_legacy_trade_intent_rows_readonly']==112
assert x['source_retained_model_long_events']==103
assert x['no_fabricated_model_intent_lineage']
assert x['requires_real_new_intent_and_live_entry_context']
assert x['real_orders_sent']==x['production_redis_writes']==0
assert x['by_reference']['LONG_TARGET']=={
 'total_model_events':11,'research_ready':7,'fresh_model_observed':0,
 'legacy_intent_in_same_window':1,'both_temporal_not_exact':0,
 'no_observed_fresh_model_or_intent':6,'exact_authorized_open':0}
assert x['by_reference']['LONG_AVOID']=={
 'total_model_events':70,'research_ready':18,'fresh_model_observed':1,
 'legacy_intent_in_same_window':1,'both_temporal_not_exact':0,
 'no_observed_fresh_model_or_intent':16,'exact_authorized_open':0}
avoid=x['stage13_11_avoid_open_diagnostics']
assert avoid['11_hypothetical_open_count']==11
assert avoid['no_later_model_observed']==10
assert avoid['no_legacy_intent_in_window']==10
assert avoid['non_positive_net_fixed']==3
assert avoid['overlap_actual_broker']==1
assert avoid['temporal_model_and_intent_not_exact']==0
assert x['by_reference']['UNLABELLED']['both_temporal_not_exact']==1
assert sum(z['freshness_result']=='MODEL_AND_TRADE_INTENT_TEMPORAL_ONLY_NOT_EXACT_PARENT' for z in x['events'])==1
assert all(z['fresh_original_parent_intent_id_verified'] is False for z in x['events'])
assert all(z['model_intent_parent_exact_join'] is False for z in x['events'] if z['original_stage13_research_decision']=='RESEARCH_READY_NO_REAL_INTENT')
assert not any(z.get('historical_order_authority',False) for z in x['events'])
opened=set(s['exit_comparison']['fixed']['pure_synthetic_single_position']['model_times'])
assert len(opened)==18
hyp=[z for z in x['events'] if z['origin_model_tr'] in opened]
assert len(hyp)==18
assert sum(z['reference_label']=='LONG_AVOID' for z in hyp)==11
assert sum(z['reference_label']=='LONG_TARGET' for z in hyp)==2
assert sum(z['reference_label']=='CONFLICT_NO_TRADE' for z in hyp)==0
assert sum(z.get('stage13_fixed_net_roi_pp',0)<0 for z in hyp if z['reference_label']=='LONG_AVOID')==3
assert sum(z.get('stage13_fixed_net_roi_pp',0)>0 for z in hyp if z['reference_label']=='LONG_AVOID')==8
print(json.dumps({'status':'PASS','stage13_research_ready':32,
 'fresh_model_and_intent_same_window':1,
 'exact_model_to_intent_authorized':0,
 'avoid_hypothetical_positions':11,'avoid_negative':3,
 'conflicting_positions':0,'binance_orders':0},sort_keys=True))
