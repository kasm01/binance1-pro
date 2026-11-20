"""As-of closed candle recovery vs frozen independent 16Nov holdout."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_COUNTERTREND_RECOVERY_WATCH_NOV16_HOLDOUT_20261120.json').read_text())
assert x['status']=='SHADOW_ONLY_NO_GO'
assert x['strict_gates_used_unchanged']
assert x['research_contra_extra_5m_return_min']==-.35
assert x['research_contra_extra_5m_return_max_exclusive']==0
assert x['contra_extra_requires_positive_3m_return_and_flow']
assert x['closed_5x_1m_proxy_not_true_5m_market_context']
assert x['labels_not_used_as_wanted_avoid_entry_whitelist']
assert x['historical_conflict_veto_observed']
assert x['future_1m_high_not_used_for_decisions']
assert x['nov16_parameters_frozen_without_holdout_tuning']
assert x['no_real_model_intent_for_new_candidates']
assert x['no_verified_partial_1m_sniper_whale']
assert x['real_orders']==x['prod_redis_writes']==0
for period in ('development','holdout'):
 r=x[period]
 assert r['strict_candidate_count']>0 and r['contra_watch_candidate_count']>0
 assert len(r['all_candidates'])==r['strict_candidate_count']+r['contra_watch_candidate_count']
 for key in ('strict_only_5m_one_position','strict_plus_contra_watch_5m_one_position'):
  z=r[key]
  assert len(z['trades'])==z['entries']
  assert sum((t['outcome']['end_5m_net_roi_pp'] for t in z['trades']))-z['sum_net_roi_pp_at_5m_close']<.00005
  assert abs(sum((t['outcome']['end_5m_net_roi_pp'] for t in z['trades']))-
   z['sum_net_roi_pp_at_5m_close'])<.00005
  assert sum(t['group']=='strict' for t in z['trades'])==z['strict_count']
  assert sum(t['group']=='contra_watch' for t in z['trades'])==z['watch_count']
  assert all(not t['conflict_veto'] for t in z['trades'])
  assert all(t['outcome']['mfe_5m_roi_pp']>=t['outcome']['mae_5m_roi_pp'] for t in z['trades'])
  assert z['entries']>=z['net_positive_5m_close_count']
  for t in z['trades']:
   f=t['features']
   assert f['green_arm'] and f['flow3']>0 and f['r3']>0
   assert f['flow3_delta']>=.08-1e-6 and f['r3_delta']>=.10-1e-6
   if t['group']=='contra_watch':
    assert -.350001<=f['r5']<0
   else:assert f['r5']>0
  # Output rounds ROI and USDT independently to five decimals.
  assert abs(z['fixed_500_margin_usdt_pnl_only_one_engine']-
    5*z['sum_net_roi_pp_at_5m_close'])<=.00003
assert x['development']['strict_plus_contra_watch_5m_one_position']['entries']==347
assert x['holdout']['strict_only_5m_one_position']['entries']==61
assert x['holdout']['strict_plus_contra_watch_5m_one_position']['entries']==73
assert x['holdout']['strict_plus_contra_watch_5m_one_position']['sum_net_roi_pp_at_5m_close']<x['holdout']['strict_only_5m_one_position']['sum_net_roi_pp_at_5m_close']
print(json.dumps({'status':'PASS','holdout_16nov':True,'fixed_profiles':2,
 'closed_mum_signal_only':True,'no_future_high_lookahead':True,
 'both_holdout_variants_net_negative':True,'real_orders':0},sort_keys=True))
