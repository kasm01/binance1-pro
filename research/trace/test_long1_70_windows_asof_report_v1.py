"""Stage13 103 replay by 70 user windows, no label-based trade decisions."""
import json
from pathlib import Path
from datetime import datetime
from collections import Counter
R=Path(__file__).resolve().parents[2]
d=json.loads((R/'research/results/LONG1_70_USER_WINDOWS_ASOF_SIMULATION_20261120.json').read_text())
r=json.loads((R/'research/results/LONG1_FOUR_FAST_REVERSAL_1M_60M_EXCURSIONS_20261120.json').read_text())
s=json.loads((R/'research/results/LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
assert d['user_interval_count']==len(d['windows'])==70
assert d['model_events_total']==len(s['events'])==103
assert d['by_label']['LONG_WANTED']['windows']==44
assert d['by_label']['LONG_AVOID']['windows']==26
assert d['by_label']['LONG_WANTED']['without_model_long']==34
assert d['by_label']['LONG_AVOID']['without_model_long']==10
assert d['by_label']['LONG_WANTED']['fixed_book_opens_from_window_sums']==2
assert d['by_label']['LONG_AVOID']['fixed_book_opens_from_window_sums']==11
assert d['conflict_no_trade_maintained'] and d['user_window_labels_not_used_for_entry_gate']
assert d['real_binance_orders']==d['real_redis_writes']==0
assert d['live_order_authority'] is False
for w in d['windows']:
 assert w['exact_reentry_proven']==0
 assert w['model_long_in_origin_window']>=w['research_ready_origin_window']>=w['fixed_single_position_opens_from_origin_window']
 assert len(w['entries_from_window_origins'])==w['model_long_in_origin_window']
 for e in w['entries_from_window_origins']:
  assert e['exact_source_reentry_authorized'] is False
  if e['stage13_decision']=='RESEARCH_READY_NO_REAL_INTENT':
   assert datetime.fromisoformat(e['hypothetical_entry_tr'])>datetime.fromisoformat(e['model_time_tr'])
assert len(r['events'])==4 and r['total_events']==4
assert r['intrabar_high_low_order_unknown'] and r['expost_future_range_not_entry_approval']
assert r['real_orders']==r['production_redis_writes']==0
assert r['actual_order_authority'] is False
expect=['ENTRY_PENDING_EXPIRED','CONTRA_WAIT_30M','CONTRA_WAIT_30M','CONTRA_WAIT_30M']
assert [x['decision'] for x in r['events']]==expect
for x in r['events']:
 assert x['real_model_intent_entry_attested'] is False
 assert x['actual_order_or_fill'] is False
 for mins in ('1','3','5','15','30','60'):
  assert x['future_horizon_minutes'][mins]['max_gross_long_roi_pp']>=x['future_horizon_minutes'][mins]['min_gross_long_roi_pp']
 assert datetime.fromisoformat(x['hypothetical_next_1m_open_time_tr'])>datetime.fromisoformat(x['model_time_tr'])
assert all(x['future_horizon_minutes']['15']['max_gross_long_roi_pp']<1.25 for x in r['events'])
print(json.dumps({'status':'PASS','windows':70,'model_events':103,
 'target_windows_without_model':34,'avoid_windows_without_model':10,
 'fixed_synthetic_opens':18,'four_timepoints_no_stage13_entry':True,
 'order_authority':False,'exchange_orders':0},sort_keys=True))
