"""As-of retrospective clues for missing LONG_TARGET signals, not exact MODEL lineage.

Legacy MODEL close_id was not carried into published SIGNAL/CANDIDATE.
For that reason we require same score within archival 6-digit rounding (<=1e-6) and 0..180s elapsed
after model event to locate related TOP5, but classify these as
HEURISTIC_TIMING_SCORE, never as exact. If model event occurred while a
broker-verified LONG was open, this fact itself is exact by timestamps.
Top5->TradeIntent source_top5_id links, where present, are exact.
"""
from __future__ import annotations
import json
from datetime import datetime,timedelta
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo
import redis
ROOT=Path(__file__).resolve().parents[2]/'research/results'
path=ROOT/'LONG1_MISSED_11_AND_OPPOSITE_SHORT_4_PRICE_PATH_20261118.json'
x=json.loads(path.read_text())
actual=json.loads((ROOT/'LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())
r=redis.Redis(decode_responses=True,socket_timeout=5)
top=[]
for sid,fields in r.xrange('top5_stream_long1'):
 dt=datetime.fromtimestamp(int(sid.split('-')[0])/1000,ZoneInfo('Europe/Istanbul'))
 if dt.date().isoformat()<'2026-11-11' or dt.date().isoformat()>'2026-11-15':continue
 pkg=json.loads(fields.get('json') or '{}')
 for item in pkg.get('items') or []:
  if item.get('symbol')!='NEARUSDT':continue
  top.append((dt,sid,item))
linked_top={str(pkg.get('source_top5_id')) for _,fields in r.xrange('trade_intents_stream_long1')
 if (pkg:=json.loads(fields.get('json') or '{}')).get('source_top5_id')}
known_ranges=[(datetime.fromisoformat(z['open_tr']),datetime.fromisoformat(z['close_tr'])) for z in actual['trades']]
assert len(known_ranges)==10
config={'whale_contra_veto_threshold':.45,'master_drop_whale_contra':True,
        'config_is_current_snapshot_not_proof_historically_same':True}
summary=Counter()
for m in x['missed_model_events']:
 ts=datetime.fromisoformat(m['timestamp_tr'])
 score=float(m['score'])
 busy=any(a<=ts<b for a,b in known_ranges)
 # Never infer from user "wanted" label that entry was technically allowed.
 matches=[(t,sid,item) for t,sid,item in top
          if 0<=(t-ts).total_seconds()<180 and
           abs(float(item.get('model_score') or -1)-score)<=1e-6]
 match_whale=[]
 for t,sid,item in matches:
  wdir=str(item.get('whale_dir') or 'none').lower()
  wscore=float(item.get('whale_score') or 0)
  veto=(wdir in ('short','sell','down','bear') and wscore>=.45)
  match_whale.append(veto)
 # Deduplicate top5 repeated candidate by id; many duplicates are
 # re-published same model evaluation as 1m "intent candidates".
 bysource={}
 for t,sid,item in matches:
  c=item.get('candidate_id')
  bysource[c]=(t,sid,item)
 no_intent_for_matches=all(sid not in linked_top for t,sid,item in matches)
 xtra={
  'broker_verified_long_already_open_at_model_event':busy,
  'legacy_top5_same_score_within_180s_count':len(matches),
  'legacy_top5_candidate_ids_count':len(bysource),
  'matched_top5_no_trade_intent_exact_source_ids':no_intent_for_matches if matches else None,
  'matched_top5_whale_contra_meeting_current_045_threshold':
       all(match_whale) if matches else None,
  'matched_top5_whale_contra_some':
       any(match_whale) if matches else None,
  'linkage_evidence':'SCORE_AND_TIME_HEURISTIC_NOT_EXACT_MODEL_CLOSE_ID',
  'master_policy_cause_independently_attested':False
 }
 m['upstream_historical_diagnostic']=xtra
 if busy:summary['broker_position_already_open']+=1
 if not matches:summary['no_exact_score_nearby_top5']+=1
 elif all(match_whale):summary['all_nearby_top5_contra_veto_candidate']+=1
 elif any(match_whale):summary['some_top5_contra_veto_candidate']+=1
 else:summary['nearby_top5_not_contra_veto']+=1
 assert not busy or not m['exact_model_to_intent_trace_present']
x['missed_upstream_summary']=dict(summary)
x['asof_master_whale_policy_snapshot']=config
assert len(x['missed_model_events'])==11
path.write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'status':'PASS','summary':dict(summary),'per_model':[{
 't':i['timestamp_tr'][5:19],
 'broker_busy':i['upstream_historical_diagnostic']['broker_verified_long_already_open_at_model_event'],
 'top5_same_score_nearby':i['upstream_historical_diagnostic']['legacy_top5_same_score_within_180s_count'],
 'all_top5_contra':i['upstream_historical_diagnostic']['matched_top5_whale_contra_meeting_current_045_threshold'],
 'intent_near':i['nearby_trade_intents_not_exact_trace']
} for i in x['missed_model_events']]},sort_keys=True))
