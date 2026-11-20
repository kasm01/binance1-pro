"""Reconcile all 28 misses, cohorts, and fail-closed candidate-only semantics."""
from pathlib import Path
import json
from collections import Counter
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_MEDIUM_REJECTED_28_CONTEXT_RESCUE_AUDIT_20261120.json').read_text())
assert x['original_entries_frozen'] and x['user_wanted_avoid_labels_for_reporting_only']
assert x['no_lookahead_in_trigger'] and x['not_rebooked_after_filter_rejection']
assert x['closed_5x1m_return_not_native_5m_market_context']
assert x['not_actual_model_score_or_live_sniper']
assert x['not_actual_035_tp_for_wanted_holdout']
assert x['research_gates_not_applied_to_production']
assert x['real_orders']==x['production_writes']==0
a=x['rejected_wanted']
assert len(a)==28
assert sum(z['old_fifth_close_win'] for z in a)==21
assert sum(z['after_entry_gross_arm035_mfe'] for z in a)==25
assert sum(z['passed_medium_rescue'] for z in a)==4
assert sum(x['rejected_wanted_first_failed_gate_order'].values())==28
assert all(z['failed_medium_conditions'] for z in a)
for name,r in x['results_by_profile'].items():
 for cohort,total in (('avoid',84),('wanted',102),('holdout',61)):
  q=r[cohort]
  assert q['count']+q['excluded']==total
  assert len(q['kept_indices'])==q['count']
  assert q['wins']+q['losses']==q['count']
  assert q['excluded_original_fifth_close_profitable']+q['excluded_original_fifth_close_losing']==q['excluded']
assert x['results_by_profile']['MEDIUM_PLUS_STRONG_CONTEXT_MILD']['avoid']['count']==65
assert x['results_by_profile']['MEDIUM_PLUS_STRONG_CONTEXT_MILD']['wanted']['count']==78
assert x['results_by_profile']['MEDIUM_PLUS_STRONG_CONTEXT_MILD']['holdout']['count']==47
assert x['results_by_profile']['MEDIUM_PLUS_STRONG_CONTEXT_MILD']['wanted']['net_roi_pp_sum']<x['results_by_profile']['MEDIUM']['wanted']['net_roi_pp_sum']
print(json.dumps({'status':'PASS','rejected_wanted':28,'rejected_wanted_positive':21,'after_entry_arm035':25,
 'rescued_wanted':4,'avoid_unchanged':True,'live_orders':0},sort_keys=True))
