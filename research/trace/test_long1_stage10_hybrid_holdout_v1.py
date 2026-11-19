"""Frozen LONG1 hybrid comparison and 16 Nov independent date invariants."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[2]
A=json.loads((R/'research/results/LONG1_103_ASOF_HYBRID_SIX_TIER_REPLAY_20261119.json').read_text())
B=json.loads((R/'research/results/LONG1_NOV16_FROZEN_STRICT_HOLDOUT_20261119.json').read_text())
C=json.loads((R/'research/results/LONG1_NOV16_FROZEN_HYBRID_HOLDOUT_20261119.json').read_text())
D=json.loads((R/'research/staging/long1_research_only_settings_v2.json').read_text())
assert A['orders_sent']==A['prod_redis_writes']==0
assert A['use_same_asof_preselected_model_entries']
assert A['tier_trigger_price']=='complete_1m_candle_close'
assert A['trailing_fill']=='following_1m_open_after_trigger'
assert A['sl_priority_within_bar'] and A['no_real_partial_m1_entry_sniper_whale']
expected={
 'strict_recovery':{'fixed_tp':(20,-21.954),'hybrid_six_tier_cap125_next_open':(20,-18.795),'six_tier_runner_next_open':(19,-17.685)},
 'balanced_pending':{'fixed_tp':(36,-31.533),'hybrid_six_tier_cap125_next_open':(39,-17.331),'six_tier_runner_next_open':(37,-6.115)},
 'cautious_relaxation':{'fixed_tp':(43,-44.475),'hybrid_six_tier_cap125_next_open':(47,-24.551),'six_tier_runner_next_open':(45,-11.639)}
}
for profile,policies in expected.items():
 data=A['results'][profile]
 assert len(data['fixed_tp']['paired_events']) in (32,59,81)
 n=len(data['fixed_tp']['paired_events'])
 for name,(count,net) in policies.items():
  v=data[name]
  assert len(v['paired_events'])==n
  assert v['single_position']['opened']==count
  assert abs(v['single_position']['roi_pp_sum_not_equity_growth']-net)<1e-5
  assert all(x['hypothetical_only'] for x in v['single_events'])
  assert all(x['reference_label']!='CONFLICT_NO_TRADE' for x in v['single_events'])
assert B['model_evaluations']==419 and B['long_signals']==24
assert B['signals_ready']==5 and B['single_position_opens']==4
assert B['exit_counts']=={'TP_FIRST':4} and B['net_roi_pp_sum']==4.04
assert B['param_changed_after_holdout'] is False
assert C['frozen_before_holdout'] and C['candidate_gate_unchanged']
assert C['profiles']['hybrid_cap125']['opened']==4
assert C['profiles']['hybrid_cap125']['net_roi_pp_sum']==4.04
assert C['profiles']['runner_uncapped']['opened']==4
assert abs(C['profiles']['runner_uncapped']['net_roi_pp_sum']-3.3039)<1e-5
assert C['real_exchange_orders']==C['prod_redis_writes']==0
assert not D['safety']['order_authority']
print(json.dumps({'status':'PASS','development_models':103,
 'holdout_model_evaluations':419,'holdout_long_signals':24,
 'holdout_hypothetical_opens':4,'holdout_hybrid_roi_pp':4.04,
 'production_params_changed':False,'orders_sent':0},sort_keys=True))
