"""Execute actual MasterExecutor whale gate on archived selected candidates.
No service init, network order, Redis write or .env modification.
Model -> Top5 ancestry here is HEURISTIC score/time, NOT exact trace.
"""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import redis
from orchestration.executor.master_executor import MasterExecutor

ROOT=Path(__file__).resolve().parents[2]
X=ROOT/'research/results/LONG1_TARGET_CONFLICT_SHADOW_PROFILE_SWEEP_20261119.json'
data=json.loads(X.read_text())
candidates=json.loads((ROOT/'research/results/LONG1_MISSED_11_AND_OPPOSITE_SHORT_4_PRICE_PATH_20261118.json').read_text())['missed_model_events']
r=redis.Redis(host='127.0.0.1',port=6379,decode_responses=True,
              socket_connect_timeout=2,socket_timeout=5)
selected=[]
for sid,record in r.xrange('top5_stream_long1'):
 t=datetime.fromtimestamp(int(sid.split('-')[0])/1000,ZoneInfo('Europe/Istanbul'))
 if not datetime(2026,11,11,tzinfo=t.tzinfo)<=t<datetime(2026,11,16,tzinfo=t.tzinfo):continue
 batch=json.loads(record.get('json') or '{}')
 for it in batch.get('items') or []:
  if it.get('symbol')=='NEARUSDT' and it.get('side')=='long':
   selected.append((sid,t,it))
assert selected
profile_results=[]
for e in candidates:
 when=datetime.fromisoformat(e['timestamp_tr'])
 close_score=float(e['score'])
 near=[(sid,t,it) for sid,t,it in selected
       if 0<=(t-when).total_seconds()<180
       and abs(float(it.get('model_score') or -1)-close_score)<=1e-6]
 count_current=count_055=count_065=0
 statuses=[]
 for sid,t,item in near:
  raw=item.get('raw') or {}
  assert isinstance(raw,dict)
  flags={}
  for threshold in (.45,.55,.65):
   m=object.__new__(MasterExecutor)
   m.long_whale_band_shadow_enable=False
   m.w_min=.05
   m.whale_use_final_decision=True
   m.whale_hard_block_actions={'block_open','hard_block'}
   m.drop_if_whale_contra=True
   m.whale_boost_thr=threshold
   res=bool(m._reject_by_whale_policy('NEARUSDT','3m','long',raw,float(item['model_score'])))
   flags[str(threshold)]=res
  count_current+=flags['0.45']
  count_055+=flags['0.55']
  count_065+=flags['0.65']
  statuses.append(flags)
 rec={
    'model_ts_tr':e['timestamp_tr'],
    'nearby_TOP5_heuristic_count':len(near),
    'vetoed_current_045':count_current,
    'vetoed_shadow_055':count_055,
    'vetoed_aggressive_065_research_only':count_065,
    'master_whale_gate_function_real':True,
    'model_to_top5_exact_trace_available':False,
 }
 profile_results.append(rec)
assert len(profile_results)==11
totals={str(v):sum(z[f'vetoed_{"current_045" if v==.45 else "shadow_055" if v==.55 else "aggressive_065_research_only"}']
                   for z in profile_results) for v in (.45,.55,.65)}
out={
 'schema':'long1_whale_gate_actual_function_readonly_on_archived_top5_v1',
 'identity_limit':'OLD_MODEL_TOP5_SCORE_AND_CLOCK_HEURISTIC',
 'model_events':11,'TOP5_rows_tested':sum(x['nearby_TOP5_heuristic_count'] for x in profile_results),
 'veto_counts_by_threshold':totals,
 'decision_code_not_modified':True,
 'veto_threshold_change_not_proven_safe':True,
 'entry_confirmation_not_replayed':True,
 'live_orders':0,'prod_redis_writes':0,
 'events':profile_results,
}
dest=ROOT/'research/results/LONG1_WHALE_THRESHOLD_045_055_065_STAGE_SHADOW_20261119.json'
dest.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'status':'PASS','tested':out['TOP5_rows_tested'],
 'vetoes':totals,'events':profile_results,'live_changes':False},sort_keys=True))
