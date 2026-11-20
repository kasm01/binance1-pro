"""Micro TP research invariants: no live changes, fee/stop and replay parity."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[2]
p=json.loads((R/'research/results/LONG1_MICRO_TP_103_ASOF_PROFILE_COMPARISON_20261120.json').read_text())
assert p['entry_candidates']==32
assert p['leverage']==3 and p['fee_roundtrip_roi_pp_assumed']==.24
assert p['fixed_tp_touch_fill_optimistic']
assert p['stop_first_if_both_seen'] and p['trailing_only_confirmed_1m_close_next_open']
assert p['entry_exit_date_same_data_not_independent_holdout']
assert p['live_orders']==p['production_redis_writes']==0
assert not p['stage13_model_intent_not_verified'] is False
assert len(p['profiles'])==8
books={name:prof['synthetic_single_position'] for name,prof in p['profiles'].items()}
expected={'fixed_0p40':-3.34148,'fixed_0p60':-2.10715,
 'fixed_0p80':.29285,'fixed_1p00':-.72347,
 'fixed_1p25':2.52653,
 'micro_0p40_arm_0p10_gb_tp_0p80':-.06558,
 'micro_0p50_arm_0p12_gb_tp_1p00':-2.013,
 'six_tier_legacy_tp_1p25':.737}
for k,v in expected.items():
 assert abs(books[k]['total_net_roi_pp']-v)<.00001,(k,books[k]['total_net_roi_pp'],v)
 for outcome in (p['profiles'][k]['synthetic_single_position'],
                 p['profiles'][k]['existing_broker_occupancy_veto_sensitivity']):
  assert outcome['count']==len(outcome['individual_trades'])
  assert abs(outcome['total_net_roi_pp']-sum(
    t['net_roi_pp'] for t in outcome['individual_trades']))<.00002
  assert all(t['exit_idx']>=t['entry_idx'] for t in outcome['individual_trades'])
  assert all(t['exit_reason'] in ('TP_FIRST','TP_GAP','STOP_GAP',
     'SL_FIRST','TRAIL_NEXT_OPEN','TIMEOUT') for t in outcome['individual_trades'])
assert books['fixed_0p40']['total_net_roi_pp']<0
assert books['fixed_0p60']['total_net_roi_pp']<0
assert books['fixed_0p80']['total_net_roi_pp_extra_cost_0p10_per_trade']<0
print(json.dumps({'status':'PASS','profiles':8,
 'old_baseline_reproduced':True,
 'small_tp_0p4_0p6_net_negative':True,
 'fixed_0p80_sensitive_to_extra_cost':True,
 'production_settings_modified':False,'orders':0},sort_keys=True))
