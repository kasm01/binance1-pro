"""Reconcile event counts, future outcomes, asof rule definitions, conflicts."""
import json
from pathlib import Path
from collections import Counter
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_AVOID_ASOF_GATE_COMPARISON_20261120.json').read_text())
assert x['source_model_events']==103 and x['real_model_long_avoid_events']==70
assert sum(z['events'] for z in x['actual_model_avoid_future_5m_by_stage'].values())==70
assert len(x['avoid_windows'])==26
assert x['real_orders']==x['redis_writes']==0
assert x['no_true_new_model_or_intent_generated']
assert x['no_future_high_used_to_generate_trigger']
assert x['eligible_closed_green_minute_trigger']
assert x['user_labels_reporting_only_conflicts_hard_veto']
assert x['native_live_quality_partial_sniper_whale_unavailable']
assert x['green_close_arm_022_groups']['LONG_AVOID']['count']==581
assert x['green_close_arm_022_groups']['LONG_WANTED']['count']==638
assert x['green_close_arm_022_groups']['CONFLICT']['count']==13
assert len(x['green_close_arm_022_rows'])==1232
assert x['green_close_arm_022_groups']['LONG_AVOID']['all_strict_1m_and_5m_proxy_positive']==95
assert x['strict_avoid_candidates_before_dedupe']==89
assert x['strict_avoid_nonoverlap_5m_candidates']==78
assert x['strict_avoid_nonoverlap_5m_measures']['5m_end_net_positive_after_fee']==6
assert x['strict_avoid_nonoverlap_5m_measures']['5m_mfe_022_seen']==41
assert x['strict_avoid_nonoverlap_5m_measures']['5m_mfe_035_seen']==34
assert x['strict_avoid_nonoverlap_5m_measures']['5m_mfe_080_seen']==15
assert sum(z['count'] for z in x['avoid_windows'])==581
assert all(z['groups']=='LONG_AVOID' and not z['broker_occupied']
  for z in x['strict_avoid_nonoverlap_rows'])
for row in x['green_close_arm_022_rows']:
 assert row['not_an_executable_signal']
 assert row['feats']['closed_green_arm']
 assert row['entry_proxy_next_open_tr']==row['minute_close_tr']
 assert row['groups'] in ('LONG_AVOID','LONG_WANTED','CONFLICT')
 assert (len(row['labels'])>1)==(row['groups']=='CONFLICT')
 assert row['outcome_5m']['mfe_roi_pp']>=row['outcome_5m']['mae_roi_pp']
assert set(x['actual_model_avoid_future_5m_by_stage'])=={
 'MODEL_GATE','CONTRA_WAIT_30M','ENTRY_PENDING_EXPIRED','RESEARCH_READY_NO_REAL_INTENT'}
print(json.dumps({'status':'PASS','real_model_avoid_events':70,'windows_avoid':26,
 'asof_green_trigger':581,'strict_market_filter_pass':95,
 'nonoverlap_no_broker':78,'net_positive_fifth_close':6,
 'real_orders':0,'production_writes':0},sort_keys=True))
