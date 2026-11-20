"""Invariants on the same 84 research entries, no real execution."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_AVOID84_FIXED_TP022_AND_PREENTRY_GATES_20261120.json').read_text())
assert x['positions']==84 and x['source_original_strict_84_unchanged']
assert x['source_legacy_78_losses']==78 and x['source_legacy_6_wins']==6
assert x['same_aggtrade_archive_count']==819943
assert x['filters_use_only_asof_completed_1m_bars']
assert x['source_timestamps_used_for_diagnostics_only']
assert x['not_original_live_model_intents'] and x['not_live_3m5m_market_context']
assert x['tp_limit_touch_assumed_instant_execution_optimistic']
assert x['hard_tp_0p22_net_pp_after_fee']==-.02
assert x['hard_tp_0p22_not_net_profitable_at_assumed_fee']
assert x['real_orders']==x['prod_redis_writes']==0
assert len(x['three_loss_examples'])==3
case=x['fixed_tp_profiles']['0.22']
assert case['base']['n']==84 and len(case['trades'])==84
assert case['base']['HARD_TP_TOUCH_IDEAL_FILL']==43
assert case['base']['loss']==84 and case['base']['profitable']==0
assert case['base']['net_roi_pp_sum']==-60.63134
assert case['extra_0p10_roi_pp']['net_roi_pp_sum']==-69.03134
assert all(t['net_roi_pp']==-.02 for t in case['trades'] if t['reason']=='HARD_TP_TOUCH_IDEAL_FILL')
for key,vals in x['fixed_tp_profiles'].items():
 assert vals['base']['n']==84 and len(vals['trades'])==84
 assert vals['base']['profitable']+vals['base']['loss']+vals['base']['zero']==84
 assert vals['base']['HARD_TP_TOUCH_IDEAL_FILL']+vals['base'].get('TIMEOUT_LAST_TICK',0)+vals['base'].get('STOP_TICK',0)==84
 assert vals['extra_0p10_roi_pp']['net_roi_pp_sum']<vals['base']['net_roi_pp_sum']
assert len(x['preentry_gate_screen']['five_minute_strength_and_flow']['avoid_84']['rejected_3_target_times'])==3
assert x['preentry_gate_screen']['five_minute_strength_and_flow']['wanted_original_strict_book']['rejected']==60
assert x['preentry_gate_screen']['three_minute_flow_ge_0p25']['avoid_84']['rejected']==43
assert x['preentry_gate_screen']['three_minute_flow_ge_0p25']['wanted_original_strict_book']['rejected']==42
print(json.dumps({'status':'PASS','unchanged_avoid_entries':84,'fixed_0p22_net_losses':84,
 'tp_filled':43,'example_bad_entries':3,'asof_guard_not_live':True,'real_orders':0},sort_keys=True))
