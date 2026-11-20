"""Predeclared marginal tightening, diagnostic on frozen strict entry cohorts.

No historical WANTED/AVOID labels used for selection. Track false rejections
and holdout; preserve exact original 84 AVOID entries and fixed TP35
same fill proxy per candidate. Rebooking after filtering not simulated:
results are *filtered original cohort*, not newly executable book.
"""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[2];OUT=R/'research/results'
src=json.loads((OUT/'LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json').read_text())
tp=json.loads((OUT/'LONG1_AVOID84_FIXED_TP022_AND_PREENTRY_GATES_20261120.json').read_text())
avoid=[v for v in src['development']['book_strict']['trades'] if v['cohort']=='LONG_AVOID']
wanted=[v for v in src['development']['book_strict']['trades'] if v['cohort']=='LONG_WANTED']
hold=src['nov16_holdout']['book_strict']['trades']
assert len(avoid)==84 and len(wanted)==102 and len(hold)==61
source84=json.loads((OUT/'LONG1_84_AVOID_AGGTRADE_6STAGE_REVERSAL_ANALYSIS_20261120.json').read_text())['trades']
tp35=tp['fixed_tp_profiles']['0.35']['trades']
assert len(tp35)==84
# all requirements are incremental to ALREADY passed strict profile:
# original strict body >=.22 retrace <=.35 flow1 >=.03,
# flow3>0; flow3 delta >=.08; r3 delta >=.10; 5m price>0.
profiles={
 'STRICT_UNCHANGED':dict(body=.22,retrace=.35,flow1=.03,flow3=0.,flow3delta=.08,r5=0.),
 'MILD':dict(body=.25,retrace=.32,flow1=.05,flow3=.03,flow3delta=.09,r5=.03),
 'MEDIUM':dict(body=.28,retrace=.30,flow1=.07,flow3=.06,flow3delta=.10,r5=.06),
 'STRONG':dict(body=.33,retrace=.25,flow1=.10,flow3=.12,flow3delta=.12,r5=.10),
}
def passing(f,c):
 return (f['body']>=c['body'] and f['retrace']<=c['retrace'] and
 f['flow1']>=c['flow1'] and f['flow3']>c['flow3'] and
 f['flow3delta']>=c['flow3delta'] and f['r5']>c['r5'])
def subset(rows,c):
 return [i for i,z in enumerate(rows) if passing(z['features'],c)]
def count(values):
 return {'n':len(values),'wins':sum(z>0 for z in values),
 'losses':sum(z<0 for z in values),
 'net_roi_pp_sum':round(sum(values),6)}
base_wanted=[z['end_5m_net_roi_pp'] for z in wanted]
base_hold=[z['end_5m_net_roi_pp'] for z in hold]
result={}
for name,c in profiles.items():
 ia=subset(avoid,c);iw=subset(wanted,c);ih=subset(hold,c)
 av=[tp35[j]['net_roi_pp'] for j in ia]
 oldprof=[z['end_5m_net_roi_pp'] for z in avoid]
 withheld=[j for j in range(84) if j not in set(ia)]
 three=[source84[j]['entry_next_open_tr'] for j in withheld if any(source84[j]['entry_next_open_tr'].startswith(prefix) for prefix in
 ('2026-11-14T01:01','2026-11-14T18:28','2026-11-14T19:27'))]
 result[name]={
 'settings':c,
 'avoid_fixed_tp035_filtered_existing_book':count(av),
 'avoid_rejected':len(withheld),
 'avoid_rejected_original_5m_wins':sum(oldprof[j]>0 for j in withheld),
 'avoid_rejected_original_5m_losses':sum(oldprof[j]<0 for j in withheld),
 'avoid_rejected_tp035_wins':sum(tp35[j]['net_roi_pp']>0 for j in withheld),
 'avoid_rejected_tp035_losses':sum(tp35[j]['net_roi_pp']<0 for j in withheld),
 'three_selected_bad_examples_excluded':len(three),
 'three_selected_bad_example_hours':three,
 'wanted_original_5m_filtered_existing_book':count([base_wanted[j] for j in iw]),
 'wanted_rejected':len(wanted)-len(iw),
 'wanted_rejected_original_5m_wins':sum(v>0 for j,v in enumerate(base_wanted) if j not in set(iw)),
 'wanted_rejected_original_5m_losses':sum(v<0 for j,v in enumerate(base_wanted) if j not in set(iw)),
 'holdout_nov16_original_5m_filtered_existing_book':count([base_hold[j] for j in ih]),
 'holdout_rejected':len(hold)-len(ih),
 'holdout_rejected_original_5m_wins':sum(v>0 for j,v in enumerate(base_hold) if j not in set(ih)),
 'holdout_rejected_original_5m_losses':sum(v<0 for j,v in enumerate(base_hold) if j not in set(ih))}
out={'schema':'long1_original_strict_84_102_61_three_tighten_gates_shadow_v1',
 'original_source_avoid_count':84,'wanted_count':102,'nov16_holdout_count':61,
 'only_completed_1m_features_asof':True,
 'filters_not_specific_to_user_time_labels':True,
 'original_candidate_chronology_unchanged':True,
 'no_rebooking_after_filtering':True,
 'not_full_market_context_sniper_model_intent':True,
 'no_unseen_nov16_aggtrade_assumed':True,
 'avoid_5m_aggtrade_tp035_optimistic_fill':True,
 'wanted_holdout_use_5m_close_comparison_NOT_same_tp_simulation':True,
 'all_profiles_fixed_upfront_no_holdout_selection':True,
 'fee_3x_roi_pp':.24,
 'real_orders':0,'production_writes':0,
 'profiles':result}
(OUT/'LONG1_STRICT_ENTRY_TIGHTENING_TP035_GATE_COMPARISON_20261120.json').write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'status':'PASS','profiles':result,'orders':0},sort_keys=True))
