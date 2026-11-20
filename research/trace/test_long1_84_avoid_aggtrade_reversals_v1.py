"""Reconcile original 84 fixed entries and printed tick outcome economics."""
import json
from pathlib import Path
from collections import Counter
R=Path(__file__).resolve().parents[2]
p=R/'research/results/LONG1_84_AVOID_AGGTRADE_6STAGE_REVERSAL_ANALYSIS_20261120.json'
x=json.loads(p.read_text());r=x['trades']
src=json.loads((R/'research/results/LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json').read_text())
fixed=[a for a in src['development']['book_strict']['trades'] if a['cohort']=='LONG_AVOID']
assert len(r)==len(fixed)==84
assert sum(x['input_archive_rows_by_utc_day'].values())==819943
assert x['six_arm_roi_thresholds']==[.22,.35,.50,.70,1.,1.4]
assert x['six_sale_fractions_original_position']==[.10,.15,.15,.20,.20,.20]
assert x['fee_3x_roi_pp_per_fraction']==.24
assert x['all_eighty_four_same_entries_across_profiles']
assert x['original_user_avoid_is_reporting_cohort_not_live_trade_gate']
assert x['no_real_new_model_intent_or_exact_market_context_proof']
assert x['live_orders']==x['production_redis_writes']==0
assert x['all']['positions']==84 and x['legacy_78_losing']['positions']==78
assert x['legacy_6_winning']['positions']==6
assert abs(x['all']['legacy_total_net_roi_pp']+95.179392)<1e-6
assert x['all']['five_minute_partial_wins']==11
assert x['all']['five_minute_partial_losses']==73
assert abs(x['all']['five_minute_partial_total_net_roi_pp']+61.308135)<1e-6
assert x['legacy_78_losing']['peak_5m_ge_0.22']==37
assert x['legacy_78_losing']['peak_5m_ge_0.35']==30
assert x['legacy_78_losing']['mfe_5m_buckets']['MFE_0_to_0p22']==41
assert x['all']['five_minute_partial_partial_sale_events']==67
assert x['all']['five_minute_partial_extra_0p10_total_net_roi_pp']<-69.7
assert sum(z['five_minute_price_path']['worst_after_peak_roi_pp']<0
 for z in r if not z['legacy_original_profitable'])==77
for row,f in zip(r,fixed):
 assert row['entry_next_open_tr'].endswith('+03:00')
 assert row['origin_close_tr'].endswith('+03:00')
 assert row['legacy_fifth_close_net_roi_pp']==f['end_5m_net_roi_pp']
 assert row['origin_close_tr']==row['entry_next_open_tr']
 assert row['entry_price_assumed']>0
 for horizon in ('five_minute_price_path','sixty_minute_price_path'):
  q=row[horizon];assert q['trade_count']>0
  assert q['peak_roi_pp']>=q['trough_roi_pp']
  assert q['peak_roi_pp']>=q['worst_after_peak_roi_pp']
  assert q['peak_to_worst_after_peak_drawdown_roi_pp']>=-1e-6
 for k in ('five_minute_partial','five_minute_runner','five_minute_partial_extra_0p10','sixty_minute_partial_OVERLAPPING_SENSITIVITY_ONLY'):
  q=row[k]
  assert sum(p['original_position_fraction'] for p in q['fills'])>1-1e-8
  assert abs(sum(p['original_position_fraction'] for p in q['fills'])-1)<1e-8
  assert all(p['original_position_fraction']>0 for p in q['fills'])
  assert q['partial_sales']<=6
  assert abs(q['net_roi_pp']-sum(p['original_position_fraction']*p['net_roi_pp_on_closed_piece'] for p in q['fills']))<3e-6
print(json.dumps({'status':'PASS','fixed_entries':84,'old_losses':78,'old_wins':6,
 'new_wins':11,'new_losses':73,'peak_under_first_arm':41,
 'stop_native_tested':False,'real_orders':0},sort_keys=True))
