"""Exact 70 user-provided TRT windows: summarize frozen Stage13 research replay.

The windows are AFTER-the-fact labels for evaluation only. They are NOT
features, rules, whitelists or entry gates. Calculate every entry twice
as origin-window and actual fill-window to expose pending spillovers.
Report zero-model windows without pretending all market opportunities absent.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter,defaultdict
import json
R=Path(__file__).resolve().parents[2];OUT=R/'research/results'
REF=json.loads((R/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json').read_text())
P=json.loads((OUT/'LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
A=json.loads((OUT/'LONG1_STAGE14_FRESH_INTENT_AND_11_AVOID_AUDIT_20261119.json').read_text())
assert len(REF['user_intervals'])==70 and len(P['events'])==103
tr=ZoneInfo('Europe/Istanbul')
why={x['origin_model_tr']:x for x in A['events']}
book={p:set(P['exit_comparison'][p]['pure_synthetic_single_position']['model_times']) for p in ('fixed','hybrid')}
broker={p:set(P['exit_comparison'][p]['real_broker_occupancy_sensitivity']['model_times']) for p in ('fixed','hybrid')}
def dt(ms):return datetime.fromtimestamp(ms/1000,tr)
def is_in(t,win):return datetime.fromisoformat(win['start_tr'])<=t<datetime.fromisoformat(win['end_tr'])
def details(e):
 z=why[e['model_time_tr']]
 out={'model_time_tr':e['model_time_tr'],
      'stage13_decision':e['decision'],'stage13_model_label':e['label'],
      'contra_origin':e['proxy_origin_contra'],
      'fresh_model_observed_in_recovery_window':z.get('independent_later_model_above_rolling_count',0)>0,
      'fresh_intent_observed_in_recovery_window':z.get('legacy_trade_intent_rows_in_window',0)>0,
      'exact_source_reentry_authorized':False}
 if e['decision']=='RESEARCH_READY_NO_REAL_INTENT':
  out.update({
     'hypothetical_entry_tr':dt(e['research_entry_ms']).isoformat(),
     'start_to_entry_min':round((e['research_entry_ms']/1000-
           datetime.fromisoformat(e['model_time_tr']).timestamp())/60,3),
     'fixed_net_roi_pp':e['fixed']['net_roi_points'],
     'hybrid_net_roi_pp':e['hybrid']['net_roi_points'],
     'fixed_exit_reason':e['fixed']['exit_reason'],
     'hybrid_exit_reason':e['hybrid']['exit_reason'],
     'fixed_book_selected':e['model_time_tr'] in book['fixed'],
     'hybrid_book_selected':e['model_time_tr'] in book['hybrid'],
     'broker_occupancy_fixed_selected':e['model_time_tr'] in broker['fixed']})
 return out
wins=[]
for n,w in enumerate(REF['user_intervals'],1):
 rows=[e for e in P['events'] if is_in(datetime.fromisoformat(e['model_time_tr']),w)]
 ready=[e for e in rows if e['decision']=='RESEARCH_READY_NO_REAL_INTENT']
 selected={p:[e for e in ready if e['model_time_tr'] in book[p]] for p in ('fixed','hybrid')}
 actual_entry=[e for e in P['events'] if e['decision']=='RESEARCH_READY_NO_REAL_INTENT'
     and is_in(dt(e['research_entry_ms']),w)]
 conflict_origins=sum(e['decision']=='CONFLICT_ORIGIN' for e in rows)
 wins.append({'number':n,'user_label':w['user_label'],
     'start_tr':w['start_tr'],'end_tr':w['end_tr'],
     'model_long_in_origin_window':len(rows),
     'model_decision_counts':dict(Counter(e['decision'] for e in rows)),
     'research_ready_origin_window':len(ready),
     'hypothetical_entry_inside_window_from_any_origin':len(actual_entry),
     'fixed_single_position_opens_from_origin_window':len(selected['fixed']),
     'hybrid_single_position_opens_from_origin_window':len(selected['hybrid']),
     'fixed_net_roi_pp_sum':round(sum(e['fixed']['net_roi_points'] for e in selected['fixed']),5),
     'hybrid_net_roi_pp_sum':round(sum(e['hybrid']['net_roi_points'] for e in selected['hybrid']),5),
     'exact_reentry_proven':0,'conflict_origin_rejected':conflict_origins,
     'entries_from_window_origins':[details(e) for e in rows]})
# origin windows may overlap. Avoid double-counting unique MODEL occurrences.
all_windows=[e for e in P['events'] if any(
    is_in(datetime.fromisoformat(e['model_time_tr']),w) for w in REF['user_intervals'])]
assert len(all_windows)<=103
# Known 4 timestamp pinpoints as requested previously. Match exact 1m bucket
# as diagnostic (not a new MODEL inference/entry event).
pins=['2026-11-12T01:36:00+03:00','2026-11-14T17:06:00+03:00',
      '2026-11-14T19:06:00+03:00','2026-11-14T23:57:00+03:00']
pin_report=[]
for t in pins:
 d=datetime.fromisoformat(t)
 aligned=[e for e in P['events'] if datetime.fromisoformat(e['model_time_tr']).replace(second=0,microsecond=0)==d]
 hits=[(w['user_label'],w['start_tr'],w['end_tr']) for w in REF['user_intervals'] if is_in(d,w)]
 pin_report.append({'time_tr':t,'reference_windows':[list(x) for x in hits],
    'observed_model_long_in_same_minute':len(aligned),
    'same_minute_model_events':[details(e) for e in aligned],
    'absence_of_model_event_does_not_prove_no_market_opportunity':True})
by_label={}
for label in ('LONG_WANTED','LONG_AVOID'):
 ws=[w for w in wins if w['user_label']==label]
 by_label[label]={'windows':len(ws),'with_any_model_long':sum(w['model_long_in_origin_window']>0 for w in ws),
    'without_model_long':sum(w['model_long_in_origin_window']==0 for w in ws),
    'model_events_count_with_overlap_double_count_possible':sum(w['model_long_in_origin_window'] for w in ws),
    'research_ready_window_sums':sum(w['research_ready_origin_window'] for w in ws),
    'fixed_book_opens_from_window_sums':sum(w['fixed_single_position_opens_from_origin_window'] for w in ws),
    'hybrid_book_opens_from_window_sums':sum(w['hybrid_single_position_opens_from_origin_window'] for w in ws),
    'fixed_net_roi_pp_window_sums':round(sum(w['fixed_net_roi_pp_sum'] for w in ws),4),
    'hybrid_net_roi_pp_window_sums':round(sum(w['hybrid_net_roi_pp_sum'] for w in ws),4)}
summary={'schema':'long1_70_user_window_stage13_14_simulation_report_v1',
 'market':'Binance Futures NEARUSDT','user_interval_count':70,'model_events_total':103,
 'timezone':'Europe/Istanbul','asof_closed_1m_entry_after_3m5m_proxy':True,
 'source_ref':'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json',
 'stage13_source':'research/results/LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json',
 'fee_assumption_roundtrip_notional':0.0008,
 'leverage':3,'fixed_gross_tp_roi_pp':1.25,'price_stop_pct':2.99,
 'max_hold_minutes':60,'funding_slippage_extra_not_included':True,
 'user_window_labels_not_used_for_entry_gate':True,
 'entry_time_may_differ_from_origin_window':True,
 'stage13_30m_recovery_is_future_research_not_real_pending_authority':True,
 'historical_new_model_intent_lineage_unproven':True,
 'conflict_no_trade_maintained':True,
 'real_binance_orders':0,'real_redis_writes':0,'live_order_authority':False,
 'by_label':by_label,
 'stage13_unique_model_decisions':P['decisions'],
 'stage13_full_book':{z:{k:{kk:vv for kk,vv in v.items() if kk!='model_times'}
    for k,v in x.items()} for z,x in P['exit_comparison'].items()},
 'pinpoints':pin_report,'windows':wins}
p=OUT/'LONG1_70_USER_WINDOWS_ASOF_SIMULATION_20261120.json'
p.write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','windows':70,'by_label':by_label,
  'pinpoints':[{k:v for k,v in x.items() if k!='same_minute_model_events'} for x in pin_report],
  'full_book':summary['stage13_full_book'],
  'real_orders':0},ensure_ascii=False,sort_keys=True))
