"""Strict archived research comparison, no production writes or new data calls.

As-of V2 independent model-time shadow data compared to earlier common user
labels, 60m path counterfactual, and legacy approximate entry log attribution.
Not the new Stage8 exact trace on old events; does NOT evaluate trading P&L.
"""
from __future__ import annotations
import json
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]/"research/results"
FILES={
 'v2':'LONG1_MARKET_CONTEXT_V2_103_ASOF_20261111_15.json',
 'pending':'LONG1_MARKET_CONTEXT_V2_PENDING_RECHECK_103_20261111_15.json',
 'roi':'LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json',
 'funnel':'LONG1_FUNNEL_TRACE_READONLY_V1_20261111_15.json',
 'counts':'LONG1_SHARED_REFERENCE_STAGE_COUNTS_20261111_15_V1.json',
 'reference':'LONG1_SHARED_REFERENCE_TRACE_STAGE6_REPLAY_20261112_14.json'
}
data={k:json.loads((ROOT/v).read_text()) for k,v in FILES.items()}
assert all(data[k]['research_only'] for k in ('v2','pending'))
assert data['v2']['shadow_only'] and not data['pending']['no_real_order_authority'] is False
assert data['funnel']['read_only'] and data['counts']['read_only']
dates={'2026-11-12','2026-11-13','2026-11-14'}
slices={
 'v2':[x for x in data['v2']['full_results'] if x['ts_tr'][:10] in dates],
 'pending':[x for x in data['pending']['rows'] if x['origin_tr'][:10] in dates],
 'roi':[x for x in data['roi']['events'] if x['model_ts_tr'][:10] in dates],
 'funnel':[x for x in data['funnel']['model_event_trace']
     if datetime.fromtimestamp(x['ts_ms']/1000,ZoneInfo('Europe/Istanbul')).date().isoformat() in dates]
}
assert all(len(v)==89 for v in slices.values()),{k:len(v) for k,v in slices.items()}
def unique(rows,key):
 d={}
 for row in rows:
  ts=row[key]
  if ts in d:raise AssertionError('ambiguous source model time '+ts)
  d[ts]=row
 return d
pending=unique(slices['pending'],'origin_tr')
roi=unique(slices['roi'],'model_ts_tr')
model_funnel=unique(slices['funnel'],'close_id')
v2_close={x['close_id'] for x in slices['v2']}
assert len(model_funnel)==len(v2_close)==89
groups=defaultdict(lambda:Counter())
byday=defaultdict(Counter)
byreason=defaultdict(Counter)
example_times={'2026-11-12T01:36','2026-11-14T17:06',
 '2026-11-14T19:06','2026-11-14T23:57'}
examples=[]
for row in slices['v2']:
 ts=row['ts_tr']
 assert ts in pending and ts in roi
 follow=pending[ts];future=roi[ts]
 old=model_funnel[row['close_id']]
 assert datetime.fromtimestamp(old['ts_ms']/1000,ZoneInfo('Europe/Istanbul')).isoformat()==ts
 assert follow['label']==row['reference_label']==future['research_label']==old['reference_label']
 assert follow['origin_decision']==row['decision']
 assert future['close_id']==row['close_id']
 assert row['decision'] in ('PENDING','VETO_ADVISORY')
 assert row['first_hit_60m']==future['horizons']['60']['status']
 assert row['orders_authorized'] is False
 assert follow['orders_authorized'] is False
 lbl=row['reference_label']
 decision=row['decision']
 hit=row['first_hit_60m']
 groups[lbl]['events']+=1
 groups[lbl][decision]+=1
 groups[lbl]['first_hit_'+hit]+=1
 groups[lbl][decision+'_first_hit_'+hit]+=1
 if not row['flow_available']:groups[lbl]['missing_flow']+=1
 if follow['found_independent_model_with_recovery']:groups[lbl]['pending_recheck_preliminary_found']+=1
 byday[ts[:10]][lbl]+=1
 byreason[lbl][row['reason']]+=1
 if any(ts.startswith(prefix) for prefix in example_times):
  examples.append({
    'timestamp_tr':ts,'user_reference':lbl,
    'model_close_id':row['close_id'],
    'market_regime_v2':row['regime'],
    'market_decision_v2':decision,'market_reason_v2':row['reason'],
    'flow_asof_available':row['flow_available'],
    'future_60m_first_hit_counterfactual':hit,
    'pending_recheck_independent_model_recovery_found':
       follow['found_independent_model_with_recovery'],
    'legacy_entry_approximate_actions':old['approximate_entry_actions'],
    'legacy_attribution':old['attribution'],
    'stage8_exact_trace_historically_present':False,
    'exchange_fill_verified':False,
  })
assert len(examples)==4,len(examples)
refcounts=Counter(x['reference_label'] for x in slices['v2'])
assert dict(refcounts)==data['reference']['overall_reference_counts'],(refcounts,data['reference']['overall_reference_counts'])
assert refcounts=={'LONG_AVOID':67,'LONG_TARGET':7,'UNLABELLED':14,'CONFLICT_NO_TRADE':1}
totals=Counter()
for gr in groups.values():totals.update(gr)
assert totals['events']==89 and totals['VETO_ADVISORY']==22 and totals['PENDING']==67
assert totals['VETO_ADVISORY_first_hit_TP_FIRST']==14
assert totals['VETO_ADVISORY_first_hit_SL_FIRST']==0
assert totals['PENDING_first_hit_SL_FIRST']==4
assert totals['missing_flow']==48
assert totals['pending_recheck_preliminary_found']==0
# Reference stage-counts aggregates live-equivalent decision *logs* from same
# windows. They are NOT distinct MODEL-long decisions or position fills.
legacy_counts=defaultdict(Counter)
for row in data['counts']['daily']:
 if row['day'] not in dates:continue
 lbl=row['reference_label']
 for field in ('live_model_long','entry_open_decisions','entry_block_decisions',
               'entry_pending_decisions','contra_pending','pending_cleared'):
  legacy_counts[lbl][field]+=row[field]
 assert row['live_model_long']==byday[row['day']][lbl],(row['day'],lbl)
assert sum(v['live_model_long'] for v in legacy_counts.values())==89
assert sum(v['contra_pending'] for v in legacy_counts.values())==0
# Zero CONTRA_PENDING in this day/label aggregate does not show that no
# guard code ever ran; it means no logged positive guard pending in source.
output={
 'schema':'long1_20261112_14_v2_contra_pending_trace_research_v1',
 'window_tr':['2026-11-12','2026-11-14'],
 'model_events':89,
 'join_type':'EXACT_ARCHIVED_MODEL_EVENT_TIME_AND_CLOSE_ID_ONLY',
 'stage6_stage8_model_parent_id_available_in_legacy':False,
 'new_trace_id_legacy_verified_count':0,
 'v2_shadow_only':True,
 'by_user_reference':{k:dict(v) for k,v in sorted(groups.items())},
 'by_day':{k:dict(v) for k,v in sorted(byday.items())},
 'v2_reason_by_user_reference':{k:dict(v) for k,v in sorted(byreason.items())},
 'v2_totals':dict(totals),
 'legacy_operational_stage_counts_by_user_reference':
    {k:dict(v) for k,v in sorted(legacy_counts.items())},
 'four_fast_reversal_examples':sorted(examples,key=lambda e:e['timestamp_tr']),
 'contra_pending_logs_in_same_three_day_reference_counts':0,
 'pending_recheck_model_followup_proofs':0,
 'pending_recheck_full_candle_independent_verification':False,
 'pending_recheck_one_minute_entry_confirmation_verified':False,
 'first_hit_hypothetical_not_actual_trade':True,
 'historical_user_reference_not_live_filter':True,
 'profit_lock_native_stop_funding_spread_real_fees_not_replayed':True,
 'net_fee_adjusted_pnl_not_measured':True,
 'binance_order_calls':0,'production_redis_writes':0,
 'live_order_authorized':False
}
path=ROOT/'LONG1_V2_CONTRA_PENDING_12_14_TRACE_COMPARISON_20261118.json'
path.write_text(json.dumps(output,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({
 'status':'PASS','model_events':89,'veto':totals['VETO_ADVISORY'],
 'pending':totals['PENDING'],'flow_missing':totals['missing_flow'],
 'hypothetical_veto_tp_first':totals['VETO_ADVISORY_first_hit_TP_FIRST'],
 'hypothetical_veto_sl_first':totals['VETO_ADVISORY_first_hit_SL_FIRST'],
 'hypothetical_pending_sl_first':totals['PENDING_first_hit_SL_FIRST'],
 'recheck_recovery_count':totals['pending_recheck_preliminary_found'],
 'legacy_contra_pending':0,'four_examples':len(examples),
 'production_redis_writes':0,'exchange_orders':0
},sort_keys=True))
