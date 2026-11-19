"""Real PENDING window classifier on archival micro samples, no live calls.

One origin confirmation pending from 00:18:13; next 1m candle expires.
Recheck needs a new independent intent+3m/5m Context Guard approval.
"""
from pathlib import Path
from collections import Counter
import json,os
from datetime import datetime
from unittest.mock import patch
from core.trade_executor import TradeExecutor

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'research/results/LONG1_ACTUAL_ENTRY_GATE_MICRO_20261115_0018.json'
d=json.loads(P.read_text())
prod=d['profiles']['production']['evaluations']
shadow=d['profiles']['candidate_shadow']['evaluations']
assert len(prod)==len(shadow)==12
first=next(x for x in prod if x['time_tr'].startswith('2026-11-15T00:18:13'))
new=next(x for x in prod if x['time_tr'].startswith('2026-11-15T00:19:03'))
assert first['entry_action']=='pending' and new['entry_action']=='open'
assert new['sniper_window_current_005_060']
self=TradeExecutor.__new__(TradeExecutor)
origin_id=int(datetime.fromisoformat(first['time_tr']).timestamp()//60)
results={}
with patch.dict(os.environ,{'SNIPER_ENTRY_MIN_CANDLE_PROGRESS':'0.05'}):
 for x in prod:
  ts=datetime.fromisoformat(x['time_tr'])
  current_id=int(ts.timestamp()//60)
  state,age=self._classify_long_pending_window(
    created_candle_id=origin_id,
    current_candle_id=current_id,
    progress=x['progress'],
    max_pending_progress=.60,
    pending_kind='confirmation')
  results[x['time_tr']]={'state':state,'age_candles':age}
assert results[first['time_tr']]['state']=='ready'
assert results[new['time_tr']]['state']=='expired'
assert all(x['entry_action']=='pending' for x in prod if
 x['time_tr'][:16]=='2026-11-15T00:18' and
 x['time_tr']>first['time_tr'] and x['time_tr']<'2026-11-15T00:18:33')
assert next(y for y in shadow if y['time_tr'].startswith('2026-11-15T00:19:13'))['entry_action']=='open'
assert next(y for y in prod if y['time_tr'].startswith('2026-11-15T00:19:13'))['entry_action']=='pending'
d['pending_window_actual_classifier']={
 'origin_confirmation_pending_time_tr':first['time_tr'],
 'origin_new_candle_time_tr':new['time_tr'],
 'old_pending_state_at_new_candle':'expired',
 'fresh_independent_model_intent_required_for_any_open':True,
 'fresh_3m5m_revalidation_not_proven':True,
 'new_ready_candle_is_not_automatic_order':True,
 'window_state_by_micro_time':results,
}
d['candidate_additional_ready_from_retrace_060_time_tr']='2026-11-15T00:19:13.820+03:00'
d['parameter_change_proved_profitable']=False
d['full_trade_ready_proven']=False
P.write_text(json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','source_snapshots':len(prod),
 'production_ready_entry_snapshots':d['profiles']['production']['action_counts']['open'],
 'shadow_ready_entry_snapshots':d['profiles']['candidate_shadow']['action_counts']['open'],
 'old_pending_expired_new_candle':True,
 'independent_new_intent_proven':False,
 'live_orders':0,'production_redis_writes':0},sort_keys=True))
