"""Validate Stage13 causal time order, portfolio mutual exclusion, no GO.

Research-only replay; never permits old pending to become new intent.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from collections import Counter
R=Path(__file__).resolve().parents[2]
d=json.loads((R/'research/results/LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
context=json.loads((R/'research/results/LONG1_STAGE12_103_BINANCE_CLOSED3M5M_CONTRA_PROXY_20261119.json').read_text())['events']
assert d['model_events']==len(d['events'])==len(context)==103
assert d['actual_fresh_model_or_intent_not_reproduced']
assert d['original_native_pending_may_expire_before_recovery']
assert d['historic_full_partial_minute_entry_unavailable']
assert d['true_live_whale_market_context_unavailable']
assert d['real_exchange_orders']==d['prod_redis_writes']==0
assert d['user_labels_not_used_as_trade_whitelist'] and d['conflicting_origins_and_entries_hard_rejected']
assert d['simulated_entry_at_next_open_after_closed_bar']
assert d['decisions']=={
 'CONFLICT_ORIGIN':1,'MODEL_GATE':1,'CONTRA_WAIT_30M':29,
 'ENTRY_PENDING_EXPIRED':40,'RESEARCH_READY_NO_REAL_INTENT':32}
assert d['ready_by_reference']=={'LONG_TARGET':7,'LONG_AVOID':18,'UNLABELLED':7}
bycontext={z['model_event_tr']:z for z in context}
for z in d['events']:
 assert not z['actual_trade_authorized']
 assert not z['actual_new_intent_verified'] and not z['partial_1m_entry_verified']
 assert not z['true_whale_market_context_reproduced']
 assert z['model_time_tr'] in bycontext
 if z['decision']=='RESEARCH_READY_NO_REAL_INTENT':
  m=int(datetime.fromisoformat(z['model_time_tr']).timestamp()*1000)
  assert z['closed_1m_decision_ms']>=z['contra_recovery_first_asof_ms']
  assert z['closed_1m_decision_ms']>m
  assert z['research_entry_ms']==z['closed_1m_decision_ms']
  assert z['research_entry_ms']>m
  assert z['proxy_1m_rechecks']<=5
  assert z['candidate_1m_features']['body']>=.22
  assert z['candidate_1m_features']['retrace']<=.35
  assert z['candidate_1m_features']['flow1']>=.03-1e-6
  assert z['candidate_1m_features']['r3']>0
  if z['proxy_origin_contra']:
   assert bycontext[z['model_time_tr']]['research_full_closed_recovery_found']
   assert bycontext[z['model_time_tr']]['research_recovery']['full_5m_recovered']
  assert 'fixed' in z and 'hybrid' in z
  assert all(z[p]['exit_idx']>=z['entry_idx'] for p in ('fixed','hybrid'))
for policy,book in d['exit_comparison'].items():
 assert policy in ('fixed','hybrid')
 main=book['pure_synthetic_single_position']
 sensitivity=book['real_broker_occupancy_sensitivity']
 assert main['opens']==18
 assert sensitivity['opens']==16
 assert main['cohorts']=={'LONG_TARGET':2,'LONG_AVOID':11,'UNLABELLED':5}
 assert sensitivity['cohorts']=={'LONG_TARGET':2,'LONG_AVOID':10,'UNLABELLED':4}
 assert 'CONFLICT_NO_TRADE' not in main['cohorts']
 assert len(set(main['model_times']))==18
 assert len(set(sensitivity['model_times']))==16
assert d['exit_comparison']['fixed']['pure_synthetic_single_position']['net_roi_points_total']==2.5265
assert d['exit_comparison']['hybrid']['pure_synthetic_single_position']['net_roi_points_total']==.737
assert d['exit_comparison']['fixed']['real_broker_occupancy_sensitivity']['net_roi_points_total']==1.7565
assert d['exit_comparison']['hybrid']['real_broker_occupancy_sensitivity']['net_roi_points_total']==-.033
print(json.dumps({'status':'PASS','models':103,'research_ready':32,
 'synthetic_book_opens':18,'real_broker_occupancy_veto_opens':16,
 'target_real_executions_confirmed':0,
 'conflict_opens':0,'fresh_intent_verified':False,
 'default_live_authority':False},sort_keys=True))
