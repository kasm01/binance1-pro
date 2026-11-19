"""Fail-closed validation of simulated LONG1 settings and conflict portfolio.

Must never grant live authority from retrospective user window labels.
No REST, Redis or order calls.
"""
from __future__ import annotations
import json
from pathlib import Path
from collections import Counter
R=Path(__file__).resolve().parents[2]
A=json.loads((R/'research/results/LONG1_TARGET_CONFLICT_SHADOW_PROFILE_SWEEP_20261119.json').read_text())
W=json.loads((R/'research/results/LONG1_WHALE_THRESHOLD_045_055_065_STAGE_SHADOW_20261119.json').read_text())
B=json.loads((R/'research/results/LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())
SET=json.loads((R/'research/staging/long1_research_only_settings_v1.json').read_text())
assert A['wanted_events']==11 and A['conflict_model_events']==1
assert A['production_redis_writes']==0 and A['live_order_permission'] is False
assert A['simulation_lookahead_for_selection'] is True
assert A['real_whale_sniper_entry_gates_reproduced'] is False
assert A['dynamic_stop_or_native_stop_reproduced'] is False
assert A['conflict_portfolio_new_orders']==0
assert A['conflict_observed_long_already_open'] is True
assert A['conflict_policy']=='HARD_REJECT'
c=A['conflict_isolated_fictitious_long']
assert c['status']=='TP_FIRST' and c['net_roi_pct_fee_illustration']==1.01
assert SET['production_env_modified'] is False
assert SET['live_authority'] is False
assert SET['hard_no_trade_when_common_user_reference_conflicts'] is True
assert 'shared_joint_risk_live_guard' in SET['unchanged_safety']
assert SET['reference_current_settings']['MASTER_MAX_POS']==1
assert SET['reference_current_settings']['LONG_CONTRA_GUARD_ENABLE']==1
assert SET['reference_current_settings']['LONG_ROLLING_MODEL_GATE_ENABLE']==1
assert SET['candidate_shadow_not_released']['MASTER_WHALE_BOOST_THR']==.55
assert SET['candidate_shadow_not_released']['SNIPER_ENTRY_MAX_CANDLE_PROGRESS']==.75
assert SET['candidate_shadow_not_released']['ENTRY_CONFIRM_MIN_QUALITY']==.48
assert SET['candidate_shadow_not_released']['ENTRY_CONFIRM_MAX_RETRACE_RATIO']==.60
assert len(SET['parameter_changes_not_validated_by_replay'])==4
assert W['TOP5_rows_tested']==18
assert W['veto_counts_by_threshold']=={'0.45':10,'0.55':10,'0.65':1}
assert W['decision_code_not_modified'] and W['live_orders']==0
assert B['opened_positions']==10 and B['not_opened_intents']==102
assert B['conflict_segments']==7 and all(x['real_open_count']==0 for x in B['conflict_coverage'])
assert sum(x['realized_price_pnl_usdt']>0 for x in B['trades'])==8
assert sum(x['realized_price_pnl_usdt']<0 for x in B['trades'])==2
expected={
 'reference_fixed125_1m':(9,2,9.09),
 'reference_fixed125_delayed_1bar':(9,2,9.09),
 'reference_fixed125_delayed_2bar':(9,2,9.09),
 'shadow_fixed060_1m':(10,1,3.6),
 'shadow_fixed095_1m':(10,1,7.1)
}
for name,(opens,skips,roi) in expected.items():
 item=A['profiles'][name]
 assert len(item['individual_events'])==12
 assert item['isolated_11_by_status']=={'TP_FIRST':11}
 assert item['sequential_single_position_opened']==opens
 assert item['sequential_skipped_busy']==skips
 assert abs(item['sequential_net_roi_pp_sum_not_capital_return']-roi)<1e-8
 assert sum(x['label']=='CONFLICT_NO_TRADE' for x in item['individual_events'])==1
 assert all(x['hypothetical_exchange_fill'] is False for x in item['individual_events'])
print(json.dumps({'status':'PASS','wanted_events':11,
 'conflict_model_events':1,'profiles':len(expected),
 'existing_verified_long':10,'conflicts_which_opened':0,
 'all_profiles_hypothetical':True,
 'live_parameter_edits':0,'live_orders':0},sort_keys=True))
