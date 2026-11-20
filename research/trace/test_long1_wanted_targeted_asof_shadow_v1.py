import json
from pathlib import Path
R=Path(__file__).resolve().parents[2]
x=json.loads((R/'research/results/LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json').read_text())
assert x['target_651_was_green_candle_count_not_trades']
assert x['market_filters_have_no_calendar_labels']
assert x['nov16_frozen_rules']
assert x['retrospective_avoid_labels_not_available_to_live_strategy']
assert x['must_not_use_clock_whitelist_for_wanted']
assert x['real_orders']==x['prod_redis_writes']==0
assert x['no_model_production_novel_events']
assert x['stop_and_actual_profitlock_not_tested']
assert x['development']['wanted_delta_book']==8
assert x['development']['avoid_delta_book']==4
assert x['development']['book_strict']['entries']==305
assert x['development']['book_strict_plus_bull_extra']['entries']==325
assert x['nov16_holdout']['book_strict']['entries']==61
assert x['nov16_holdout']['book_strict_plus_bull_extra']['entries']==64
assert x['nov16_holdout']['book_strict_plus_bull_extra']['sum_net_roi_pp_at_5m_close'] < x['nov16_holdout']['book_strict']['sum_net_roi_pp_at_5m_close']
assert x['development_extra_by_reference']['LONG_AVOID']['additional_closed_1m_candidates']>0
for period in ('development','nov16_holdout'):
 r=x[period]
 assert r['strict_pool']>0
 assert r['extra_pool']>0
 assert len(r['all_candidates'])==r['strict_pool']+r['extra_pool']
 for k in ('book_strict','book_strict_plus_bull_extra'):
  z=r[k]
  assert z['entries']==len(z['trades'])
  assert all(t['cohort']!='CONFLICT' for t in z['trades'])
  assert all(t['gross_mfe_5m_roi_pp']>=t['gross_mae_5m_roi_pp'] for t in z['trades'])
  assert abs(sum(t['end_5m_net_roi_pp'] for t in z['trades']) - z['sum_net_roi_pp_at_5m_close'])<.00003
  assert z['positive_5m_close']<=z['entries']
  for t in z['trades']:
   assert t['features']['green_arm']
   if t['source']=='BULL_CONTEXT_EXTRA':
    assert t['features']['r5']>=.20-1e-6 and t['features']['r3']>=.12-1e-6
print(json.dumps({'status':'PASS','avoid_unchanged_requirement_met':False,
 'wanted_extra_independent_entries':8,'avoid_extra_independent_entries':4,
 'holdout_worse':True,'live_change':False},sort_keys=True))
