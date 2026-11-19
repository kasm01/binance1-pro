"""LONG1 historical exact-vs-temporal revalidation and false-open attribution.

Never equate Stage13 research READY (future 3m5m recovery without new intent)
with real executor READY. Separates actual later MODEL signals, independent
legacy TRADE INTENTS and exact lineage identities, using read-only Redis.
The join for old MODEL -> intent remains unproven even on clock overlap.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from bisect import bisect_right,bisect_left
from collections import Counter,defaultdict
import json,redis
R=Path(__file__).resolve().parents[2]
B=R/'research/results'
stage=json.loads((B/'LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
events=stage['events'];assert len(events)==103
model=json.loads((B/'LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json').read_text())['events']
assert len(model)==103
models=sorted([(int(datetime.fromisoformat(v['model_ts_tr']).timestamp()*1000),v) for v in model],key=lambda x:x[0])
mts=[t for t,_ in models]
r=redis.Redis(decode_responses=True,socket_timeout=5,socket_connect_timeout=3)
t_intents=[]
for sid,vals in r.xrange('trade_intents_stream_long1',min='1794326400000-0',max='1794787200000-0'):
 data=json.loads(vals.get('json') or '{}')
 for z in data.get('items') or []:
  if z.get('symbol')!='NEARUSDT' or str(z.get('side') or '').lower()!='long':continue
  t=int(sid.split('-')[0])
  t_intents.append({'ts_ms':t,'redis_id':sid,'intent_id':z.get('intent_id')})
t_intents.sort(key=lambda x:x['ts_ms'])
itimes=[z['ts_ms'] for z in t_intents]
def range_models(a,b):
 if b<a:return []
 return [(t,v) for t,v in models[bisect_left(mts,a):bisect_right(mts,b)]]
def range_intents(a,b):
 if b<a:return []
 return t_intents[bisect_left(itimes,a):bisect_right(itimes,b)]
out=[]
for z in events:
 start=int(datetime.fromisoformat(z['model_time_tr']).timestamp()*1000)
 res={'origin_model_tr':z['model_time_tr'],'reference_label':z['label'],
  'original_stage13_research_decision':z['decision'],
  'original_model_time_ms':start,'fresh_original_parent_intent_id_verified':False,
  'binance_actual_orders_from_this_replay':0}
 if z['decision']!='RESEARCH_READY_NO_REAL_INTENT':
  res['freshness_result']='NOT_RESEARCH_READY'
 else:
  recovered=z['contra_recovery_first_asof_ms']
  last_allowed=z['closed_1m_decision_ms']
  independent_models=range_models(max(start+1,recovered),last_allowed)
  independent_valid_models=[(t,v) for t,v in independent_models
       if float(v['model_score'])>=float(v['actual_rolling_threshold'])]
  legacy_intents=range_intents(max(start+1,recovered),last_allowed)
  res.update({
    'recovery_3m5m_proxy_time_ms':recovered,
    'candidate_decision_full_1m_close_ms':last_allowed,
    'research_entry_time_ms':z['research_entry_ms'],
    'elapsed_from_origin_to_recovery_min':round((recovered-start)/60000,3),
    'independent_later_model_count':len(independent_models),
    'independent_later_model_above_rolling_count':len(independent_valid_models),
    'independent_later_model_times_tr':[v['model_ts_tr'] for _,v in independent_valid_models],
    'legacy_trade_intent_rows_in_window':len(legacy_intents),
    'legacy_trade_intent_ids_in_window':[v['intent_id'] for v in legacy_intents[:10]],
    'freshness_result':(
       'MODEL_AND_TRADE_INTENT_TEMPORAL_ONLY_NOT_EXACT_PARENT'
       if independent_valid_models and legacy_intents
       else 'FRESH_MODEL_ONLY_INTENT_UNPROVEN'
       if independent_valid_models
       else 'LEGACY_INTENT_ONLY_MODEL_UNPROVEN'
       if legacy_intents else 'NO_OBSERVED_FRESH_MODEL_OR_INTENT'
    ),
    'model_intent_parent_exact_join':False,
    'entry_full_executor_1m_partial_ready_verified':False,
    'stage13_fixed_net_roi_pp':z['fixed']['net_roi_points'],
    'stage13_hybrid_net_roi_pp':z['hybrid']['net_roi_points'],
    'observed_market_context_recovered_historical_exact':False,
    'historical_order_authority':False,
    'features':z['candidate_1m_features'],
    'overlaps_actual_long':z['overlaps_real_broker_long'],
  })
 out.append(res)
bycohort={}
for lab in ('LONG_TARGET','LONG_AVOID','UNLABELLED','CONFLICT_NO_TRADE'):
 sub=[x for x in out if x['reference_label']==lab]
 a=[x for x in sub if x['original_stage13_research_decision']=='RESEARCH_READY_NO_REAL_INTENT']
 bycohort[lab]={'total_model_events':len(sub),'research_ready':len(a),
  'fresh_model_observed':sum(x.get('independent_later_model_above_rolling_count',0)>0 for x in a),
  'legacy_intent_in_same_window':sum(x.get('legacy_trade_intent_rows_in_window',0)>0 for x in a),
  'both_temporal_not_exact':sum(x['freshness_result']=='MODEL_AND_TRADE_INTENT_TEMPORAL_ONLY_NOT_EXACT_PARENT' for x in a),
  'no_observed_fresh_model_or_intent':sum(x['freshness_result']=='NO_OBSERVED_FRESH_MODEL_OR_INTENT' for x in a),
  'exact_authorized_open':0}
# 11 Stage13 LONG_AVOID hypothetical selected opens, which decisions correspond?
synthetic=set(stage['exit_comparison']['fixed']['pure_synthetic_single_position']['model_times'])
avoid=[x for x in out if x['origin_model_tr'] in synthetic and x['reference_label']=='LONG_AVOID']
assert len(avoid)==11
avoid_diagnostics={'11_hypothetical_open_count':11,
 'no_later_model_observed':sum(x.get('independent_later_model_above_rolling_count',0)==0 for x in avoid),
 'no_legacy_intent_in_window':sum(x.get('legacy_trade_intent_rows_in_window',0)==0 for x in avoid),
 'temporal_model_and_intent_not_exact':sum(x['freshness_result']=='MODEL_AND_TRADE_INTENT_TEMPORAL_ONLY_NOT_EXACT_PARENT' for x in avoid),
 'non_positive_net_fixed':sum(x.get('stage13_fixed_net_roi_pp',0)<=0 for x in avoid),
 'overlap_actual_broker':sum(bool(x.get('overlaps_actual_long')) for x in avoid)}
summary={
 'schema':'LONG1_STAGE14_FRESH_MODEL_INTENT_TEMPORAL_AUDIT_RESEARCH_V1',
 'model_events':103,'stage13_ready':sum(z['decision']=='RESEARCH_READY_NO_REAL_INTENT' for z in events),
 'source_legacy_trade_intent_rows_readonly':len(t_intents),
 'source_retained_model_long_events':len(model),
 'same_window_trade_intent_not_exact_attributed':True,
 'no_fabricated_model_intent_lineage':True,
 'requires_real_new_intent_and_live_entry_context':True,
 'source_archive_context_is_proxy':True,
 'existing_single_position_and_conflict_guards_preserved':True,
 'no_current_live_config_change':True,
 'real_orders_sent':0,'production_redis_writes':0,
 'by_reference':bycohort,
 'stage13_11_avoid_open_diagnostics':avoid_diagnostics,
 'events':out}
dest=B/'LONG1_STAGE14_FRESH_INTENT_AND_11_AVOID_AUDIT_20261119.json'
dest.write_text(json.dumps(summary,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'PASS':True,'source_intents':len(t_intents),
 'cohorts':bycohort,'avoid_11':avoid_diagnostics,
 'real_orders_authorized':0},sort_keys=True))
