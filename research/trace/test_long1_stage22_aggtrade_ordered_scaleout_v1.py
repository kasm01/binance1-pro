"""Stage22 source conservation, sequential tick assumptions, no orders."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_STAGE22_REAL_AGGTRADE_022_035_TIERED_SCALEOUT_20261120.json').read_text())
assert x['asof_model_ready_candidates_from_stage13']==32
assert sum(x['official_aggtrade_archive_rows_by_utc_day'].values())==819943
assert x['aggtrade_intra_minute_ordering_observed'] and x['same_trade_stop_checked_before_arm']
assert x['tick_prices_not_orderbook_or_guaranteed_fills']
assert x['entry_next_one_minute_open_hypothetical_not_trade_fill']
assert x['tier_sells_first_trade_at_or_above_threshold']
assert x['trailing_stop_trade_price_proxy_not_real_order_fill']
assert x['no_native_stop_or_true_new_model_intent']
assert x['no_nov16_aggtrade_file_available_for_tick_holdout']
assert x['no_production_changes'] and x['live_binance_orders']==x['production_redis_writes']==0
assert x['four_bot_each_margin_usdt']==500 and x['eight_bot_each_margin_usdt']==250
assert len(x['profiles'])==3
assert sorted(float(z) for z in x['profiles']['requested_022_035_six_stage_partial'])==[0,.05,.10,.20]
for profile,cases in x['profiles'].items():
 for cost,case in cases.items():
  for series in ('no_broker_veto','historical_broker_occupancy_veto'):
   c=case[series]
   assert c['opens']==len(c['trades'])<=32
   assert abs(sum(v['net_roi_pp'] for v in c['trades'])-c['net_roi_pp_total'])<3e-5
   assert c['partial_fills']==sum(v['number_partial_sales'] for v in c['trades'])
   assert c['wins']+c['losses']==c['opens']
   for trade in c['trades']:
    assert 0<=trade['highest_armed_stage']<=6
    assert 0<=trade['first_tick_delay_ms']<60000
    assert abs(sum(v['closed_original_fraction'] for v in trade['fills'])-1)<1e-7
    assert trade['exit_idx']>=trade['entry_idx']
    times=[v['timestamp_ms'] for v in trade['fills']]
    assert times==sorted(times)
    stage_reasons=[v['reason'] for v in trade['fills'] if v['reason'].startswith('STAGE_')]
    assert len(stage_reasons)==len(set(stage_reasons))
    assert 0<=len(stage_reasons)<=6
    assert all(z['closed_original_fraction']>0 for z in trade['fills'])
  assert case['four_bot_fixed_500_usdt_one_long1_pnl']==round(
   5*case['no_broker_veto']['net_roi_pp_total'],5)
  assert case['eight_bot_fixed_250_usdt_one_long1_pnl']==round(
   2.5*case['no_broker_veto']['net_roi_pp_total'],5)
new=x['profiles']['requested_022_035_six_stage_partial']['0']['no_broker_veto']
assert new['opens']==20 and new['partial_fills']==31
assert new['exits']=={'TRAIL_TICK':18,'TIMEOUT':1,'ALL_STAGES_FILLED':1}
assert abs(new['net_roi_pp_total']+3.580807)<1e-7
assert x['profiles']['requested_022_035_six_stage_partial']['0.1']['no_broker_veto']['net_roi_pp_total']<-5.58
print(json.dumps({'status':'PASS','aggtrade_rows':819943,
 'replay_six_stage_partial_positions':20,'partial_sale_events':31,
 'tick_model_fee_sensitive':True,'real_orders':0},sort_keys=True))
