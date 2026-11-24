"""Check frozen event identity, as-of gates, 3x fees and ordered fills."""
from pathlib import Path
import json
from research.trace.replay_long1_stage23_model103_tp035_execution_proxy_v1 import (
 exit_replay,candidates,STAGE13,STAGE20,STAGE21,OUT,ROOT,tms,bars)
x=json.loads((OUT/'LONG1_STAGE23_MODEL103_TP035_EXECUTION_PROXY_SIM_20261124.json').read_text())
assert x['source_real_model_event_count']==103
assert x['stage13_research_ready']==32
assert x['stage20_price_recovery_proxy']==20
assert x['stage21_all_flows_and_price_support_proxy']==0
assert x['production_proven_order_authority']==0
assert x['real_orders_sent']==x['production_redis_writes']==0
assert x['source_tick_count']==819943
assert x['fee_3x_roi_pp_assumption'] if 'fee_3x_roi_pp_assumption' in x else x['assumed_roundtrip_fee_roi_pp']==.24
assert x['stop_is_price_minus_2p99_percent_not_roi_minus_2p99']
assert x['risk_master_global_coin_lock_not_reconstructed']
assert x['fill_at_limit_touch_optimistic']
assert len(x['candidate_details'])==32
for z in x['candidate_details']:
 assert z['research_proxy_entry_ms'] in bars
 assert abs(bars[z['research_proxy_entry_ms']]-z['research_entry_price'])<1e-10
 assert not z['full_model_intent_sniper_entry_risk_authority_verified']
 assert z['exits']['5m_extra_0.00']['trade_horizon_complete']
 a=z['exits']['5m_extra_0.00'];b=z['exits']['5m_extra_0.10']
 assert abs((a['net_roi_pp']-b['net_roi_pp'])-.10)<.00001
 if a['reason']=='TP035_TOUCH_IDEAL_LIMIT_FILL':
  assert a['net_roi_pp']==.11
  assert b['net_roi_pp']==.01
  assert z['research_proxy_entry_ms']<=a['exit_ms']<z['research_proxy_entry_ms']+300000
# 5m and 60m book reconstruct from exact returned exits, no overlap.
for p,scenarios in x['scenarios'].items():
 for name,v in scenarios.items():
  assert v['booked_nonoverlap']<=v['eligible']
  assert v['wins']+v['losses']==v['booked_nonoverlap']
  assert len(v['model_times'])==v['booked_nonoverlap']
  assert v['real_orders_placed']==0
  assert v['mean_net_roi_per_booked_trade'] is None or v['booked_nonoverlap']>0
  assert abs(v['assumed_500usdt_margin_sum_pnl_usdt']-v['net_roi_points_sum']*5)<.00011
  if p in ('STAGE21_PRICE_PLUS_SIGNED_FLOW_3_5_15_60','PRODUCTION_PROVEN_END_TO_END'):
   assert v['booked_nonoverlap']==0
base=x['scenarios']['STAGE13_1M_ONLY']
hold=x['scenarios']['STAGE20_PRICE_FRESH_3M5M']
assert (base['5m_extra_0.00_broker_occupancy_False']['booked_nonoverlap'],
        base['5m_extra_0.00_broker_occupancy_False']['wins'],
        base['5m_extra_0.00_broker_occupancy_False']['losses'])==(20,14,6)
assert base['5m_extra_0.00_broker_occupancy_False']['net_roi_points_sum']==-3.460451
assert base['60m_extra_0.00_broker_occupancy_False']['net_roi_points_sum']==-4.191478
assert base['5m_extra_0.10_broker_occupancy_False']['net_roi_points_sum']==-5.460451
assert hold['5m_extra_0.00_broker_occupancy_False']['net_roi_points_sum']==-3.628773
assert hold['60m_extra_0.00_broker_occupancy_False']['net_roi_points_sum']==-3.510511
# No trade before model arrival, no synthetic entry can be claimed as real.
from datetime import datetime
for z in x['candidate_details']:
 assert z['research_proxy_entry_ms']>=int(datetime.fromisoformat(z['model_time_tr']).timestamp()*1000)
print(json.dumps({'status':'PASS','model_events':103,'research_candidates':32,
 'stage20_candidates':20,'stage21_candidates':0,'baseline_5m_trades':20,
 'baseline_5m_net_roi_pp':-3.460451,'production_orders':0},sort_keys=True))
