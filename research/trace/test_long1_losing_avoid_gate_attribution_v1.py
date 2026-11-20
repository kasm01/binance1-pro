import json
from pathlib import Path
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_AVOID84_RESEARCH_VS_LIVE_GATE_ATTRIBUTION_20261120.json').read_text())
assert x['summary_all']['count']==84
assert x['summary_fixed_tp035_losses']['count']==48
assert x['summary_fixed_tp035_wins']['count']==36
assert x['summary_fixed_tp035_losses']['mfe_below_0p22']==41
assert x['summary_fixed_tp035_losses']['model_same_minute']==2
assert x['summary_fixed_tp035_losses']['native_closed_shape_proxy_pass']==47
assert x['summary_fixed_tp035_wins']['model_same_minute']==0
assert x['native_entry_retrace_uses_directional_span_not_full_candle_range']
assert x['native_partial_minute_decisions_unavailable']
assert x['no_real_model_score_gate_attribution_for_84']
assert x['archived_model_same_minute_not_sufficient_for_true_intent_lineage']
assert x['no_actual_orders_for_84'] and x['real_orders']==x['production_redis_writes']==0
assert x['env_whitelisted_snapshot']['ENTRY_CONFIRM_SHADOW']=='0'
assert x['env_whitelisted_snapshot']['LONG_CONTRA_GUARD_ENABLE']=='1'
assert len(x['all_rows'])==84
assert len(x['fixed_tp035_losing_details'])==48
for r in x['all_rows']:
 assert all(r['research_closed1m_passed_gates'].values())
 assert not r['actual_fresh_model_intent_ancestry_verified']
 assert not r['actual_live_sniper_verified']
 assert not r['actual_live_entry_confirmation_verified']
 assert not r['actual_risk_master_order_authority_verified']
two=[r for r in x['fixed_tp035_losing_details'] if r['same_minute_archived_model_events']]
assert len(two)==2
assert all(r['same_minute_model_decisions']==['CONTRA_WAIT_30M'] for r in two)
three=[r for r in x['fixed_tp035_losing_details'] if any(r['entry_time_tr'].startswith(z) for z in ('2026-11-14T01:01','2026-11-14T18:28','2026-11-14T19:27'))]
assert len(three)==3 and all(r['same_minute_archived_model_events']==0 for r in three)
c=next(r for r in three if '19:27' in r['entry_time_tr'])
assert c['closed_bar_native_entry_shape_illustration']['native_retrace_ratio']==.5
assert c['closed_bar_native_entry_shape_illustration']['would_closed_bar_pass_native_shape_only']==False
print(json.dumps({'status':'PASS','fixed_tp035_losing_synthetic':48,
 'real_model_event_same_minute':2,'contra_wait_count':2,
 'confirmed_actual_orders_from_synthetic':0},sort_keys=True))
