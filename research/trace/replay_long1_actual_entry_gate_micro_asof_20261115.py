"""Actual LONG1 Entry Confirmation evaluated on retained as-of 1m micro snapshots.

Does not reproduce full production context, broker, whale, sniper order
clock, or revalidation authority. Source snapshots may be ~10 s apart,
so there may be unrecorded intermediate READY states. No look-ahead:
only snapshots with source timestamp >= MODEL signal; strictly ≤120s.
"""
from __future__ import annotations
import json,os
from collections import Counter
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
import redis
from core.trade_executor import TradeExecutor

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'research/results/LONG1_ACTUAL_ENTRY_GATE_MICRO_20261115_0018.json'
model=json.loads((ROOT/'research/results/LONG1_MISSED_11_AND_OPPOSITE_SHORT_4_PRICE_PATH_20261118.json').read_text())['missed_model_events']
t=next(x for x in model if x['timestamp_tr']=='2026-11-15T00:18:00+03:00')
r=redis.Redis(decode_responses=True,socket_timeout=5)
start=int(datetime.fromisoformat(t['timestamp_tr']).timestamp()*1000)
end=start+120000
saved=[]
for sid,fields in r.xrange('shadow:telemetry:microstructure',min=str(start)+'-0',max=str(end)+'-999999'):
 try:obj=json.loads(fields.get('json') or '{}')
 except(ValueError,TypeError):continue
 ts=int(obj.get('observed_at_ms') or sid.split('-')[0])
 if not(start<=ts<=end and obj.get('symbol')=='NEARUSDT'):continue
 saved.append((ts,obj))
assert saved and len(saved)>=5
assert all(saved[j+1][0]>=saved[j][0] for j in range(len(saved)-1))
assert all('live1m_open' in obj and 'live1m_high' in obj and
   'live1m_low' in obj and 'live1m_close' in obj for _,obj in saved)

engine=TradeExecutor.__new__(TradeExecutor)
profiles={
 'production':{'ENTRY_CONFIRM_MIN_BODY_RATIO':'0.15',
               'ENTRY_CONFIRM_MAX_RETRACE_RATIO':'0.50',
               'ENTRY_CONFIRM_REJECT_RETRACE_RATIO':'0.75',
               'ENTRY_CONFIRM_MIN_QUALITY':'0.52'},
 'candidate_shadow':{'ENTRY_CONFIRM_MIN_BODY_RATIO':'0.15',
               'ENTRY_CONFIRM_MAX_RETRACE_RATIO':'0.60',
               'ENTRY_CONFIRM_REJECT_RETRACE_RATIO':'0.75',
               'ENTRY_CONFIRM_MIN_QUALITY':'0.48'},
}
result={}
for name,env in profiles.items():
 evaluations=[]
 with patch.dict(os.environ,dict(env,ENTRY_CONFIRM_ENABLE='1',ENTRY_CONFIRM_SHADOW='0')):
  for ts,source in saved:
   progress=float(source['live1m_progress'])
   ctx={
     'px_now':float(source['live1m_close']),
     'candle_open':float(source['live1m_open']),
     'candle_high':float(source['live1m_high']),
     'candle_low':float(source['live1m_low']),
     'entry_candle_interval':'1m',
     'entry_context_source':'historical_redis_micro_asof'
   }
   entry=engine._evaluate_long_entry_confirmation(
     side='long',signal_score=float(t['score']),
     open_min_score=float(t['rolling_threshold']),market_context=ctx)
   assert entry['action'] in ('open','pending','block')
   assert entry['details']['entry_context_source']=='historical_redis_micro_asof'
   evaluations.append({
      'time_tr':datetime.fromtimestamp(ts/1000,ZoneInfo('Europe/Istanbul')).isoformat(timespec='milliseconds'),
      'progress':round(progress,4),
      'entry_action':entry['action'],'reason':entry['reason'],
      'quality':entry['details']['entry_quality'],
      'body_ratio':entry['details']['body_ratio'],
      'retrace_ratio':entry['details']['retrace_ratio'],
      'direction_support':entry['details']['direction_support'],
      'sniper_window_current_005_060':
          .05<=progress<=.60,
      'sniper_window_shadow_005_075':
          .05<=progress<=.75,
   })
 result[name]={
   'total_source_snapshots':len(evaluations),
   'action_counts':dict(Counter(e['entry_action'] for e in evaluations)),
   'current_sniper_and_entry_open_snapshots':sum(e['entry_action']=='open' and e['sniper_window_current_005_060'] for e in evaluations),
   'shadow_sniper_and_entry_open_snapshots':sum(e['entry_action']=='open' and e['sniper_window_shadow_005_075'] for e in evaluations),
   'evaluations':evaluations,
 }
assert result['production']['total_source_snapshots']==result['candidate_shadow']['total_source_snapshots']
a={
 'schema':'long1_actual_entry_confirmation_historical_micro_asof_v1',
 'source_redis':'shadow:telemetry:microstructure',
 'first_redis_data_date_tr':'2026-11-14T14:25+03:00',
 'model_event_tr':t['timestamp_tr'],
 'model_score':t['score'],
 'model_rolling_gate_passed':True,
 'model_to_micro_uuid_exact_join':False,
 'asof_time_bound_not_exact_model_trace':True,
 'source_micro_snapshot_count':len(saved),
 'sampling_sparse_approx_every_10sec':True,
 'actual_entry_confirmation_method_used':True,
 'actual_sniper_method_replayed':False,
 'sniper_window_boundary_from_config_only':True,
 'real_model_intent_has_to_revalidate':True,
 'missing_3m_5m_context_prevents_real_entry_authority':True,
 'reference_user_label_not_a_runtime_input':True,
 'production_env_changed':False,
 'live_order_authority':False,'production_redis_writes':0,
 'profiles':result
}
P.write_text(json.dumps(a,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'status':'PASS','model':t['timestamp_tr'],'snapshots':len(saved),
 'production':{k:v for k,v in result['production'].items() if k!='evaluations'},
 'shadow':{k:v for k,v in result['candidate_shadow'].items() if k!='evaluations'},
 'no_orders':True},sort_keys=True))
