"""Stage21 six partial take profit: exact sum fractions, no orders."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_2000USDT_4_8BOT_022_035_SIX_STAGE_PARTIAL_REPLAY_20261120.json').read_text())
assert x['research_ready']==32 and x['model_signals']==103
assert x['account_balance_usdt']==2000 and x['leverage']==3
assert x['allocation_four_bot_each_usdt']==500
assert x['allocation_eight_bot_each_usdt']==250
assert x['user_first_two_tiers']==[[.22,.10],[.35,.10]]
assert x['six_partial_sale_fractions_of_original']==[.10,.15,.15,.20,.20,.20]
assert x['net_early_first_floor_0p22_minus_0p10_minus_fee']==-.12
assert abs(x['net_early_second_floor_0p35_minus_0p10_minus_fee']-.01)<1e-10
assert x['no_hard_0p80_tp_so_higher_stages_possible']
assert x['tier_scaleout_trigger_after_1m_close_fill_next_open']
assert x['old_model_and_intent_lineage_unverified']
assert x['real_exchange_orders_sent']==x['production_redis_writes']==0
assert x['not_four_eight_bot_portfolio_replay']
assert len(x['results'])==4
a=x['results']['requested_0p22_0p35_six_step_partial']['single_coin_single_position']
assert a['opened']==19 and a['total_slice_fills']==73
assert abs(a['total_net_roi_pp']-4.489056)<1e-7
b=x['results']['requested_0p22_0p35_runner_no_scaleout']['single_coin_single_position']
assert b['opened']==19 and b['total_slice_fills']==0
assert abs(b['total_net_roi_pp']-6.646442)<1e-7
for name,prof in x['results'].items():
 for k in ('single_coin_single_position','existing_real_broker_occupancy_veto'):
  book=prof[k]
  assert book['opened']==len(book['trades'])
  assert abs(book['total_net_roi_pp']-sum(t['total_net_roi_pp'] for t in book['trades']))<2e-5
  assert book['total_slice_fills']==sum(t['number_of_partial_fills'] for t in book['trades'])
  for t in book['trades']:
   assert t['exit_idx']>=t['entry_idx']
   assert 0<=t['stages_reached']<=6
   assert sum(f['closed_original_fraction'] for f in t['fills'])>=(1-1e-7)
   assert abs(sum(f['closed_original_fraction'] for f in t['fills'])-1)<1e-7
   assert len([f for f in t['fills'] if f['reason'].startswith('TIER_')])<=6
   # No exact same tier collected twice.
   reasons=[f['reason'] for f in t['fills'] if f['reason'].startswith('TIER_')]
   assert len(reasons)==len(set(reasons))
   for f in t['fills']:
    assert 0<f['closed_original_fraction']<=1
    assert f['at_bar']>=t['entry_idx']
 for num in (4,8):
  z=prof['allocation'][str(num)]
  assert z['per_bot_margin_cap_usdt']==2000/num
  assert z['account_allocation_pct']==100/num
  assert z['per_bot_notional_3x_usdt']==6000/num
  assert abs(z['long1_research_summed_pnl_usdt'] -
     z['per_bot_margin_cap_usdt']*prof['single_coin_single_position']['total_net_roi_pp']/100)<1e-5
  assert z['single_full_margin_price_stop_with_fee_usdt']==round(-z['per_bot_margin_cap_usdt']*.0921,5)
print(json.dumps({'status':'PASS','candidate_count':32,'model_events':103,
 'six_stages':6,'user_first_two_arms':[.22,.35],
 'scaleout_original_fraction_total_each_trade':1,
 'one_coin_single_position':True,
 'partial_profile_trade_count':19,'partial_fills':73,
 'positive_development_roi_not_live_approved':True,
 'real_orders':0,'prod_redis_writes':0},sort_keys=True))
