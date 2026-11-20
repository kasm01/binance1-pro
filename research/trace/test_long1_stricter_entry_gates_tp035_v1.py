"""Check predeclared entry filter tightening on fixed original candidate pools."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_STRICT_ENTRY_TIGHTENING_TP035_GATE_COMPARISON_20261120.json').read_text())
assert x['original_source_avoid_count']==84
assert x['wanted_count']==102 and x['nov16_holdout_count']==61
assert x['only_completed_1m_features_asof'] and x['filters_not_specific_to_user_time_labels']
assert x['original_candidate_chronology_unchanged'] and x['no_rebooking_after_filtering']
assert x['not_full_market_context_sniper_model_intent'] and x['no_unseen_nov16_aggtrade_assumed']
assert x['wanted_holdout_use_5m_close_comparison_NOT_same_tp_simulation']
assert x['real_orders']==x['production_writes']==0
p=x['profiles']
assert len(p)==4
assert p['STRICT_UNCHANGED']['avoid_fixed_tp035_filtered_existing_book']['n']==84
assert p['STRICT_UNCHANGED']['avoid_fixed_tp035_filtered_existing_book']['wins']==36
assert p['STRICT_UNCHANGED']['avoid_fixed_tp035_filtered_existing_book']['losses']==48
assert p['MILD']['avoid_fixed_tp035_filtered_existing_book']['n']==74
assert p['MEDIUM']['avoid_fixed_tp035_filtered_existing_book']['n']==65
assert p['STRONG']['avoid_fixed_tp035_filtered_existing_book']['n']==49
for name,r in p.items():
 a=r['avoid_fixed_tp035_filtered_existing_book']
 b=r['wanted_original_5m_filtered_existing_book']
 h=r['holdout_nov16_original_5m_filtered_existing_book']
 assert a['n']+r['avoid_rejected']==84 and a['wins']+a['losses']==a['n']
 assert b['n']+r['wanted_rejected']==102
 assert h['n']+r['holdout_rejected']==61
 assert b['wins']+b['losses']==b['n'] and h['wins']+h['losses']==h['n']
 assert r['avoid_rejected_original_5m_wins']+r['avoid_rejected_original_5m_losses']==r['avoid_rejected']
 assert r['avoid_rejected_tp035_wins']+r['avoid_rejected_tp035_losses']==r['avoid_rejected']
 assert r['wanted_rejected_original_5m_wins']+r['wanted_rejected_original_5m_losses']==r['wanted_rejected']
 assert r['holdout_rejected_original_5m_wins']+r['holdout_rejected_original_5m_losses']==r['holdout_rejected']
 assert len(r['three_selected_bad_example_hours'])==r['three_selected_bad_examples_excluded']
assert p['MILD']['three_selected_bad_examples_excluded']==0
assert p['MEDIUM']['three_selected_bad_examples_excluded']==1
assert p['STRONG']['three_selected_bad_examples_excluded']==2
assert p['STRONG']['wanted_rejected_original_5m_wins']==32
print(json.dumps({'status':'PASS','frozen_profiles':4,'avoid_cohort':84,'wanted_cohort':102,'holdout_cohort':61,'real_orders':0},sort_keys=True))
