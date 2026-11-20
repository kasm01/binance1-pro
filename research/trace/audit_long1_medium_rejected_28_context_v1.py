"""Audit 28 rejected WANTED candidates and context-sensitive rescue without labels.

Study compares original STRICT and MEDIUM as-of gate on frozen 84 AVOID,
102 WANTED and 61 independent Nov16. Conditional addback only when
strong 3m flow and completed 5m return, using original mild shape.
Reports cohort effects, NOT a live guard or reconstructed actual 5m TP.
"""
from __future__ import annotations
from pathlib import Path
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
import json
R=Path(__file__).resolve().parents[2];O=R/'research/results';TR=ZoneInfo('Europe/Istanbul')
S=json.loads((O/'LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json').read_text())
T=json.loads((O/'LONG1_STRICT_ENTRY_TIGHTENING_TP035_GATE_COMPARISON_20261120.json').read_text())
tp=json.loads((O/'LONG1_AVOID84_FIXED_TP022_AND_PREENTRY_GATES_20261120.json').read_text())['fixed_tp_profiles']['0.35']['trades']
cohorts={k:[z for z in S['development']['book_strict']['trades'] if z['cohort']==tag]
         for k,tag in (('avoid','LONG_AVOID'),('wanted','LONG_WANTED'))}
cohorts['holdout']=S['nov16_holdout']['book_strict']['trades']
assert list(map(len,cohorts.values()))==[84,102,61]
cfg=T['profiles']
def gate(f,c):
 return f['body']>=c['body'] and f['retrace']<=c['retrace'] and f['flow1']>=c['flow1'] and f['flow3']>c['flow3'] and f['flow3delta']>=c['flow3delta'] and f['r5']>c['r5']
def relevant(time_ms):
 return datetime.fromtimestamp(time_ms/1000,TR).isoformat()
def mild_recovery(f):
 # Proposed only for diagnosis: boost market strength (completed 5m>=0.2%)
 # and sustained flow3>=0.25, while requiring MILD-shaped entry.
 return gate(f,cfg['MILD']['settings']) and f['r5']>=.20 and f['flow3']>=.25
def medium_with_rescue(f):
 return gate(f,cfg['MEDIUM']['settings']) or mild_recovery(f)
def eval_cohort(key, fn):
 rows=cohorts[key];keep=[i for i,r in enumerate(rows) if fn(r['features'])]
 if key=='avoid':
  outcomes=[tp[i]['net_roi_pp'] for i in keep]
 else:
  outcomes=[rows[i]['end_5m_net_roi_pp'] for i in keep]
 missing=[i for i in range(len(rows)) if i not in set(keep)]
 return {'count':len(keep),'excluded':len(missing),
  'net_roi_pp_sum':round(sum(outcomes),6),
  'wins':sum(v>0 for v in outcomes),'losses':sum(v<0 for v in outcomes),
  'excluded_original_fifth_close_profitable':sum(rows[i]['end_5m_net_roi_pp']>0 for i in missing),
  'excluded_original_fifth_close_losing':sum(rows[i]['end_5m_net_roi_pp']<0 for i in missing),
  'kept_indices':keep}
funcs={'STRICT':lambda f:True,
 'MILD':lambda f:gate(f,cfg['MILD']['settings']),
 'MEDIUM':lambda f:gate(f,cfg['MEDIUM']['settings']),
 'MEDIUM_PLUS_STRONG_CONTEXT_MILD':medium_with_rescue}
results={name:{key:eval_cohort(key,fn) for key in cohorts} for name,fn in funcs.items()}
reject=[]
for z in cohorts['wanted']:
 if gate(z['features'],cfg['MEDIUM']['settings']):continue
 f=z['features'];failing=[name for name,rule in
 (('body_min_0p28',f['body']>=.28),('retrace_max_0p30',f['retrace']<=.30),
  ('flow1_min_0p07',f['flow1']>=.07),('flow3_min_0p06',f['flow3']>.06),
  ('flow3_improvement_min_0p10',f['flow3delta']>=.10),
  ('closed5m_return_min_0p06pct',f['r5']>.06)) if not rule]
 reject.append({'close_tr':relevant(z['time_ms']),
 'old_five_minute_net_roi_pp':z['end_5m_net_roi_pp'],
 'old_fifth_close_win':z['end_5m_net_roi_pp']>0,
 'five_minute_gross_mfe_roi_pp':z['gross_mfe_5m_roi_pp'],
 'after_entry_gross_arm035_mfe':z['gross_mfe_5m_roi_pp']>=.35,
 'failed_medium_conditions':failing,
 'passed_medium_rescue':mild_recovery(f),
 'features':f})
assert len(reject)==28
firstfail=Counter(next(iter(z['failed_medium_conditions'])) for z in reject)
allfail=Counter(k for z in reject for k in z['failed_medium_conditions'])
out={'schema':'long1_medium_rejected28_counterfactual_bull_recovery_v1',
 'original_entries_frozen':True,
 'user_wanted_avoid_labels_for_reporting_only':True,
 'no_lookahead_in_trigger':True,
 'not_rebooked_after_filter_rejection':True,
 'closed_5x1m_return_not_native_5m_market_context':True,
 'not_actual_model_score_or_live_sniper':True,
 'not_actual_035_tp_for_wanted_holdout':True,
 'research_gates_not_applied_to_production':True,
 'fee_3x_roi_pp_assumed':.24,
 'holdout_guard_hypothesis_derived_after_previous_research':True,
 'holdout_not_pristine_for_further_model_selection':True,
 'real_orders':0,'production_writes':0,
 'rejected_wanted':reject,
 'rejected_wanted_first_failed_gate_order':dict(firstfail),
 'rejected_wanted_all_failed_gates':dict(allfail),
 'results_by_profile':results}
p=O/'LONG1_MEDIUM_REJECTED_28_CONTEXT_RESCUE_AUDIT_20261120.json'
p.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
summary={name:{key:{k:v for k,v in z.items() if k!='kept_indices'} for key,z in cases.items()} for name,cases in results.items()}
print(json.dumps({'status':'PASS','rejected_28_wins':sum(z['old_fifth_close_win'] for z in reject),
 'rejected_28_arm035':sum(z['after_entry_gross_arm035_mfe'] for z in reject),
 'first_failed':dict(firstfail),'all_failed':dict(allfail),
 'rescued_from_28':sum(z['passed_medium_rescue'] for z in reject),
 'profiles':summary,'orders':0},sort_keys=True))
