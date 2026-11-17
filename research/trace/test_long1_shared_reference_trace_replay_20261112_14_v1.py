"""Stage6 time-window reference / legacy model funnel historical regression.

Read existing archive files only, no Redis, exchange, production traffic.
User-defined windows are retrospective research labels, NEVER deploy as
live time-of-day gates, training target, or causal trade/fill outcomes.
"""
from __future__ import annotations
import json
from collections import Counter,defaultdict
from datetime import datetime,date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
SHARED=ROOT/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json'
FUNNEL=ROOT/'research/results/LONG1_FUNNEL_TRACE_READONLY_V1_20261111_15.json'
REV=ROOT/'research/results/LONG1_FOUR_FAST_REVERSALS_20261112_14_20261115.md'
OUTCOMES=ROOT/'research/results/LONG1_ACTUAL_OUTCOMES_REFERENCE_20261111_15.json'
TZ=ZoneInfo('Europe/Istanbul')
WINDOWS=json.loads(SHARED.read_text())
HISTORY=json.loads(FUNNEL.read_text())
assert WINDOWS["research_only"] is True and WINDOWS["production_order_authority"] is False
assert WINDOWS["long_wanted_count"]==44 and WINDOWS["long_avoid_count"]==26
assert HISTORY['read_only'] is True

intervals=[]
for x in WINDOWS['user_intervals']:
    start=datetime.fromisoformat(x['start_tr'])
    end=datetime.fromisoformat(x['end_tr'])
    assert start.tzinfo is not None and end.tzinfo is not None
    assert end>start
    assert x['user_label'] in ('LONG_WANTED','LONG_AVOID')
    intervals.append((start,end,x['user_label']))

def reference(ts_ms:int)->str:
    instant=datetime.fromtimestamp(ts_ms/1000,TZ)
    hits={label for start,end,label in intervals if start<=instant<end}
    if len(hits)>1:return 'CONFLICT_NO_TRADE'
    if 'LONG_AVOID' in hits:return 'LONG_AVOID'
    if 'LONG_WANTED' in hits:return 'LONG_TARGET'
    return 'UNLABELLED'

def summarize(rows):
    by_day=defaultdict(Counter)
    by_market=defaultdict(Counter)
    for row in rows:
        dt=datetime.fromtimestamp(row['ts_ms']/1000,TZ)
        lbl=reference(row['ts_ms'])
        assert lbl==row['reference_label'],(dt.isoformat(),lbl,row['reference_label'])
        by_day[dt.date().isoformat()][lbl]+=1
        by_market[lbl][row['market_decision']]+=1
    return by_day,by_market

start=date(2026,11,12)
end=date(2026,11,14)
selected=[x for x in HISTORY['model_event_trace']
          if start<=datetime.fromtimestamp(x['ts_ms']/1000,TZ).date()<=end]
assert len(selected)==89,len(selected)
daily,market=summarize(selected)
overall=Counter(reference(x['ts_ms']) for x in selected)
assert overall=={'LONG_AVOID':67,'LONG_TARGET':7,'UNLABELLED':14,'CONFLICT_NO_TRADE':1},overall

# Important no-lookahead: archived funnel's links are HEURISTIC_SCORE_TIME,
# not new Stage6 exact ID chains. Old rows DO NOT contain the new IDs.
assert all(r['attribution'] in ('MODEL_ONLY','HEURISTIC_SCORE_TIME') for r in selected)
assert not any(r.get('model_evaluation_id') or r.get('parent_signal_event_id') for r in selected)

def find_historical(day_time,score):
    t=datetime.fromisoformat(day_time).replace(tzinfo=TZ)
    matches=[r for r in selected if
       abs(r['ts_ms']/1000-t.timestamp())<60 and
       abs(r['score']-score)<1e-6]
    assert len(matches)==1,(day_time,len(matches))
    return matches[0]
examples=[
 ("2026-11-12T01:36:16",.497407),
 ("2026-11-14T17:06:14",.499819),
 ("2026-11-14T19:06:12",.500040),
 ("2026-11-14T23:57:09",.510074),
]
four=[]
for label,score in examples:
    row=find_historical(label,score)
    assert reference(row['ts_ms'])=='LONG_AVOID'
    # Only model timestamp -> user window has EXACT interval containment.
    # Model->entry and entry->order lineage remain NOT VERIFIED.
    four.append({
      "timestamp_tr":label,
      "model_score":score,
      "user_reference":"LONG_AVOID",
      "market_context_advisory":row['market_decision'],
      "legacy_entry_attribution":row['attribution'],
      "legacy_entry_actions_heuristic":row['approximate_entry_actions'],
      "direct_order_fill_verified":False,
      "new_stage6_trace_available_for_legacy":False
    })
assert four[2]['legacy_entry_actions_heuristic'].get('pending')==2

# Historical position outcome telemetry uses user-window labels at a
# different event time (position OPEN, not MODEL score). These records
# are NOT independently revalidated Binance fills; never infer 1:1 join
# to any of the 89 model-score bars.
outcomes=json.loads(OUTCOMES.read_text())
assert outcomes['read_only'] is True
historical_positions=[]
for item in outcomes['rows']:
    dt=datetime.fromisoformat(item['open_tr'])
    if not (start<=dt.date()<=end):
        continue
    predicted_label=reference(round(dt.timestamp()*1000))
    assert predicted_label==item['label'],(dt,item['label'],predicted_label)
    historical_positions.append({
      'position_open_tr':item['open_tr'],
      'reference_label':predicted_label,
      'exit_reason_telemetry':item['reason'],
      'net_roi_percent_telemetry':item['net_roi_percent'],
      'independent_exchange_fill_verified':False
    })
assert len(historical_positions)==7,len(historical_positions)
position_counts=Counter(x['reference_label'] for x in historical_positions)
assert position_counts=={'UNLABELLED':4,'LONG_AVOID':3},position_counts
avoid_outcomes=[x for x in historical_positions if x['reference_label']=='LONG_AVOID']
assert sum(x['net_roi_percent_telemetry']>0 for x in avoid_outcomes)==2
assert sum(x['net_roi_percent_telemetry']<0 for x in avoid_outcomes)==1

# Window coverage is NOT prediction quality; include non-model window
# labels to guard against extrapolating LONG_TARGET as a guaranteed trade.
assert sum(overall.values())==89
output={
 "schema":"long1_shared_window_trace_stage6_historical_20261112_14.v1",
 "source_files":[SHARED.name,FUNNEL.name,REV.name,OUTCOMES.name],
 "timezone":"Europe/Istanbul",
 "window_inclusive_dates":["2026-11-12","2026-11-14"],
 "historical_model_long_count":len(selected),
 "overall_reference_counts":dict(overall),
 "daily":{k:dict(v) for k,v in sorted(daily.items())},
 "advisory_market_decisions_by_user_reference":
          {k:dict(v) for k,v in sorted(market.items())},
 "strict_interval_labels_recomputed_and_equal":True,
 "four_fast_reversal_examples":four,
 "historical_position_outcome_telemetry_rows":len(historical_positions),
 "historical_position_outcome_reference_counts":dict(position_counts),
 "LONG_AVOID_outcomes_positive_net_roi_count":2,
 "LONG_AVOID_outcomes_negative_net_roi_count":1,
 "position_outcome_telemetry_rows":historical_positions,
 "no_model_to_position_join_inferred":True,
 "legacy_entries_linked_with_exact_trace_id":0,
 "legacy_funnel_only_heuristic_or_model_only":True,
 "user_labels_not_trading_policy":True,
 "retrospective_reference_not_causal_entry_or_fill_proof":True,
 "exchange_orders":0,"production_redis_writes":0
}
target=ROOT/'research/results/LONG1_SHARED_REFERENCE_TRACE_STAGE6_REPLAY_20261112_14.json'
target.write_text(json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({
 "status":"PASS","historical_model_long":len(selected),
 "reference_counts":dict(overall),"daily":output['daily'],
 "four_examples_recomputed_LONG_AVOID":True,
 "historical_position_outcomes":len(historical_positions),
 "LONG_AVOID_positive_outcomes":2,
 "LONG_AVOID_negative_outcomes":1,
 "legacy_exact_parent_matches":0,
 "production_redis_writes":0,"orders":0},sort_keys=True))
