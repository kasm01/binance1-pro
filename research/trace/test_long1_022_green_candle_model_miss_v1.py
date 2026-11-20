"""Check whole-hour report consistency, price math, no invented orders."""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
R=Path(__file__).resolve().parents[2]
r=json.loads((R/'research/results/LONG1_70_WINDOWS_GREEN_022_ARM_AND_MISSING_MODEL_20261120.json').read_text())
assert r['user_windows']==len(r['windows'])==70
assert r['historical_model_events_103']==103
assert r['user_target_windows']==44 and r['user_avoid_windows']==26
assert len([w for w in r['windows'] if w['user_label']=='LONG_WANTED'])==44
assert len([w for w in r['windows'] if w['user_label']=='LONG_AVOID'])==26
assert r['arm_gross_roi_pp']==.22 and r['leverage']==3
assert abs(r['minimum_price_up_from_open_pct_for_022_3x_roi']-.22/3)<1e-12
assert r['theoretical_first_floor_net_roi_pp']==-.12
assert r['real_orders']==r['production_redis_writes']==0
assert not r['exact_model_intent_lineage_verified']
g=r['group_unique_counts']
assert g['LONG_WANTED']['green_1m_candles']==934
assert g['LONG_WANTED']['green_open_to_high_022_arms']==849
assert g['LONG_WANTED']['green_open_to_close_022_arms']==651
assert g['LONG_WANTED']['high_022_arm_no_long_model_same_minute']==841
assert g['LONG_WANTED']['close_022_arm_no_long_model_same_minute']==644
assert g['LONG_AVOID']['green_open_to_high_022_arms']==818
assert g['UNION_ALL_UNIQUE_CANDLES']['green_open_to_high_022_arms']==1651
assert r['total_target_windows_without_same_minute_model']==34
assert r['target_without_model_high022_hits_sum']==604
assert len(r['target_without_model_candle_details'])==34
for w in r['windows']:
 rows=w['green_open_to_high_022_details']+w['green_other_details']
 assert all(x['green'] for x in rows)
 assert sum(z['green_open_to_high_arm_022_hit'] for z in rows)==w['counts']['green_open_to_high_022_arms']
 assert len(rows)==w['counts']['green_1m_candles']
 for z in rows:
  assert datetime.fromisoformat(w['start_tr'])<=datetime.fromisoformat(z['start_tr'])
  assert datetime.fromisoformat(z['end_tr'])<=datetime.fromisoformat(w['end_tr'])
  assert z['close']>z['open']
  assert z['green_open_to_high_arm_022_hit']==(300*(z['high']/z['open']-1)>=.22-1e-10)
  assert z['green_open_to_close_arm_022_hit']==(300*(z['close']/z['open']-1)>=.22-1e-10)
  assert z['same_minute_observed_long_model_events']==len(z['same_minute_model_times'])
  assert z['signal_absence_in_same_minute']==(not z['same_minute_observed_long_model_events'])
  assert z['conflict_no_trade']==(len(z['user_window_labels'])>1)
assert sum(w['counts']['green_open_to_high_022_arms'] for w in r['windows'] if w['user_label']=='LONG_WANTED')==849
print(json.dumps({'status':'PASS','windows':70,'wanted':44,'avoid':26,
 'wanted_green':934,'wanted_high022':849,'wanted_close022':651,
 'wanted_high022_no_same_minute_model':841,'wanted_close022_no_same_minute_model':644,
 'wanted_full_windows_without_model':34,'hit_in_no_model_wanted_windows':604,
 'avoid_high022':818,'real_orders':0},sort_keys=True))
