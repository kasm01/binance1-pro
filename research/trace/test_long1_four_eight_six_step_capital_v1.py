"""Four/eight fixed capital caps; Stage13 unchanged and 6-stage no ORDER."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_2000USDT_4BOT_8BOT_6STAGE_SIM_20261120.json').read_text())
assert x['model_events']==103 and x['research_ready']==32
assert x['account_balance_usdt']==2000 and x['leverage']==3
assert x['allocation_is_fixed_capital_envelope_not_live_full_margin_mandate']
assert x['full_2000_allocated_leaves_no_unreserved_cash_buffer']
assert x['same_coin_global_one_position_risk_master_invariant']
assert x['aggregate_8_bots_replay_not_valid_from_one_long1_data_series']
assert x['hard_tp_0p80_caps_6_step_upside']
assert x['dynamic_tp_raises_only_after_prior_full_1m_close']
assert x['dynamic_tp_cancel_replace_instantaneous_optimistic']
assert x['soft_tp_0p80_is_not_guaranteed_exit_at_0p80']
assert x['live_new_model_intent_not_reproduced']
assert x['real_orders_sent']==x['redis_writes']==0
assert x['six_stage_user_first_arm']==[[.22,.10],[.40,.10],[.60,.12],[.80,.15],[1.10,.18],[1.50,.20]]
assert len(x['profiles'])==6
for name,prof in x['profiles'].items():
 assert len(prof['four_eight_allocation_scenarios'])==2
 p=prof['parameters']
 if p['tiers']:assert len(p['tiers'])==6
 for allocation in prof['four_eight_allocation_scenarios']:
  n=allocation['bot_count'];margin=2000/n
  assert allocation['balance_per_bot_usdt']==margin
  assert allocation['allocation_pct_of_total_balance']==100/n
  assert allocation['position_notional_per_bot_if_full_allocation_usdt']==margin*3
  assert allocation['total_nominal_if_all_bots_use_full_balance_usdt']==6000
  assert abs(allocation['stop_net_usdt_if_filled']-(-margin*.0921))<.000001
  assert abs(allocation['stop_pct_of_total_account']-(margin*.0921/2000*100))<.000001
  if p['tiers'] and name.endswith('arm_0p22'):
   assert allocation['first_floor_net_after_fee_roi_pp']==-.12
 for key in ('one_coin_single_position_book','broker_occupancy_veto_sensitivity'):
  q=prof[key];ts=q['trades']
  assert len(ts)==q['trades_count']
  assert q['trades_count']<=32
  assert not any(t['research_label']=='CONFLICT_NO_TRADE' for t in ts)
  assert abs(sum(t['net_roi_pp'] for t in ts)-q['total_net_roi_pp'])<.000025
  assert all(t['exit_idx']>=t['entry_idx'] for t in ts)
control=x['profiles']['hard_tp_0p80_no_trail_control']
assert control['one_coin_single_position_book']['total_net_roi_pp']==.29285
assert control['one_coin_single_position_book']['trades_count']==19
requested=x['profiles']['hard_tp_0p80_6stage_first_arm_0p22']
assert requested['one_coin_single_position_book']['total_net_roi_pp']==-1.69099
assert requested['one_coin_single_position_book']['trades_count']==19
soft=x['profiles']['soft_tp_0p80_6stage_runner_first_arm_0p22']
assert soft['one_coin_single_position_book']['total_net_roi_pp']==6.64643
assert soft['one_coin_single_position_book']['trades_count']==19
assert soft['broker_occupancy_veto_sensitivity']['total_net_roi_pp']==8.05152
print(json.dumps({'status':'PASS','profiles':len(x['profiles']),
 'four_bot_each_margin':500,'eight_bot_each_margin':250,
 'first_floor_net_after_fee_roi_pp':-.12,
 'requested_hard_tp_synthetic_roi_pp':-1.69099,
 'soft_runner_synthetic_roi_pp':6.64643,
 'one_coin_single_position':True,'real_orders':0},sort_keys=True))
