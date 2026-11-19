"""Offline verification of as-of entry and pending outputs."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[2]
j=json.loads((R/'research/results/LONG1_ACTUAL_ENTRY_GATE_MICRO_20261115_0018.json').read_text())
assert j['actual_entry_confirmation_method_used']
assert j['production_env_changed'] is False
assert j['live_order_authority'] is False and j['production_redis_writes']==0
assert j['source_micro_snapshot_count']==12
assert j['profiles']['production']['action_counts']=={'open':1,'pending':10,'block':1}
assert j['profiles']['candidate_shadow']['action_counts']=={'open':2,'pending':9,'block':1}
assert j['profiles']['production']['current_sniper_and_entry_open_snapshots']==1
assert j['profiles']['candidate_shadow']['shadow_sniper_and_entry_open_snapshots']==2
assert j['pending_window_actual_classifier']['old_pending_state_at_new_candle']=='expired'
assert j['pending_window_actual_classifier']['fresh_independent_model_intent_required_for_any_open']
assert not j['full_trade_ready_proven']
assert not j['parameter_change_proved_profitable']
micro=j['future_barrier_counterfactual_on_micro_ready']
assert micro['independent_intent_after_00_18_not_verified']
assert len(micro['scenarios'])==2
assert all(v['future_60m_barrier_status']=='TP_FIRST' and v['net_roi_after_illustrative_0p08pct_notional_fees']==1.01 for v in micro['scenarios'])
assert all(v['order_eligibility_not_established'] for v in micro['scenarios'])
assert all(v['micro_price_execution_not_proven'] for v in micro['scenarios'])
w=json.loads((R/'research/results/LONG1_TARGET_CONFLICT_SHADOW_PROFILE_SWEEP_20261119.json').read_text())
assert w['conflict_portfolio_new_orders']==0 and w['conflict_policy']=='HARD_REJECT'
print(json.dumps({'result':'PASS','asof_micro_snapshots':12,
 'production_ready_snapshots':1,'shadow_ready_snapshots':2,
 'old_pending_next_minute_expired':True,
 'new_model_intent_attested':False,'all_gates_open_attested':False,
 'hypothetical_60m_first_hit':'TP_FIRST',
 'conflict_portfolio_new_orders':0,'real_orders_sent':0,'prod_redis_writes':0},sort_keys=True))
