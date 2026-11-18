"""Offline invariants: past user-label overlaps never grant future orders."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from collections import Counter
R=Path(__file__).resolve().parents[2]/'research/results'
x=json.loads((R/'LONG1_MISSED_11_AND_OPPOSITE_SHORT_4_PRICE_PATH_20261118.json').read_text())
base=json.loads((R/'LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())
assert x['missing_opportunity_model_events']==11
assert x['target_trade_intents_total']==9 and x['target_broker_opens']==0
assert len(x['missed_model_events'])==11
assert all(z['score_above_rolling'] for z in x['missed_model_events'])
assert all(z['hypothetical_60m_first_hit']=='TP_FIRST' for z in x['missed_model_events'])
assert all(z['exact_model_to_intent_trace_present'] is False for z in x['missed_model_events'])
assert sum(z['upstream_historical_diagnostic']['broker_verified_long_already_open_at_model_event']
           for z in x['missed_model_events'])==2
assert sum(z['upstream_historical_diagnostic'].get('matched_top5_whale_contra_meeting_current_045_threshold') is True
           for z in x['missed_model_events'])==4
assert len(x['opposite_short_from_four_long_avoid_entries'])==4
mfe=[3.433,8.241,9.042,5.165]
for i,z in enumerate(x['opposite_short_from_four_long_avoid_entries']):
    w=z['windows']
    assert w['60m']['status']=='COMPLETE_FULL_MINUTE_BARS_ONLY'
    assert w['120m']['status']=='COMPLETE_FULL_MINUTE_BARS_ONLY'
    assert w['240m']['status']=='COMPLETE_FULL_MINUTE_BARS_ONLY'
    assert abs(w['60m']['short_mfe_roi_pct']-mfe[i])<.002
    assert w['120m']['short_mfe_roi_pct']>=w['60m']['short_mfe_roi_pct']
    assert w['240m']['short_mfe_roi_pct']>=w['120m']['short_mfe_roi_pct']
    assert w['60m']['entry_and_exit_minute_excluded']
    assert w['60m']['intraminute_sequence_unknown']
    assert w['60m']['short_mfe_roi_pct']>=.6
    assert isinstance(w['60m']['short_mfe_time_tr'],str)
    assert datetime.fromisoformat(w['60m']['short_mfe_time_tr'])>datetime.fromisoformat(z['original_long_open_tr'])
    assert z['short_hypothesis_only']
    assert z['opposite_bot_short1_symbol_not_nearusdt']
    assert not z.get('actual_short_order_id')
assert x['short_live_exchange_does_not_exist']
assert x['short_liquidation_and_realistic_execution_not_simulated']
assert x['retro_research_only'] and x['orders_sent']==0 and x['production_redis_writes']==0
assert base['conflict_segments']==7 and all(z['real_open_count']==0 for z in base['conflict_coverage'])
print(json.dumps({'status':'PASS','missed_model':11,'wanted_intents':9,
 'wanted_real_opens':0,'short_scenarios':4,
 'short_first_60m_max_roi':mfe,'short_real_executions':0,
 'conflicts_no_real_long_opens':7,'no_live_orders':True},sort_keys=True))
