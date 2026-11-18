"""READ-ONLY stage-context audit + hypothetical NEARUSDT SHORT price paths.

Uses public Binance futures 1m klines only and previously broker-verified
LONG order fill entries; does NOT emulate SHORT1 on INJUSDT, execution,
exchange margin rules, protective orders, liquidation, or actual spreads.
Uses a fixed same-price SHORT reference, deterministic bar-order conservative
stop-first for within-bar ambiguities, NO market data from the future to
authorize entries. A user-window label is an evaluation annotation ONLY.
"""
from __future__ import annotations
import json,requests,math
from datetime import datetime,timedelta
from collections import Counter
from pathlib import Path
from decimal import Decimal

ROOT=Path(__file__).resolve().parents[2]/'research/results'
BASE=json.loads((ROOT/'LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())
MODEL=json.loads((ROOT/'LONG1_MARKET_CONTEXT_V2_103_ASOF_20261111_15.json').read_text())['full_results']
FIRST=json.loads((ROOT/'LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json').read_text())['events']
assert len(MODEL)==len(FIRST)==103
shorts=[v for v in BASE['trades'] if v['reference_label']=='LONG_AVOID']
assert len(shorts)==4
targets=[v for v in MODEL if v['reference_label']=='LONG_TARGET']
assert len(targets)==11
first_by_ts={v['model_ts_tr']:v for v in FIRST}
assert len(first_by_ts)==103
intent_rows=BASE['all_112_intent_decisions_anonymized']
wanted_intents=[v for v in intent_rows if v['user_reference']=='LONG_TARGET']
assert len(wanted_intents)==9
from zoneinfo import ZoneInfo
TR=ZoneInfo('Europe/Istanbul')

def klines(start,end):
    """Fully closed 1m bars; loop bounded to <10 calls total."""
    ms=int(start.timestamp()*1000)
    endms=int(end.timestamp()*1000)
    rows=[];calls=0
    while ms<endms:
        r=requests.get('https://fapi.binance.com/fapi/v1/klines',
          params={'symbol':'NEARUSDT','interval':'1m','startTime':ms,
                  'endTime':endms-1,'limit':1000},timeout=12,allow_redirects=False)
        r.raise_for_status()
        page=r.json()
        if not isinstance(page,list):raise ValueError('invalid klines')
        if not page:break
        rows.extend(page)
        nxt=int(page[-1][0])+60000
        assert nxt>ms
        ms=nxt
        calls+=1
        assert calls<=9
    bars={int(z[0]):{'t':int(z[0]),'o':float(z[1]),'h':float(z[2]),
                       'l':float(z[3]),'c':float(z[4])} for z in rows}
    return bars,calls

# Four entries span max Nov 12–14; shared market download, no repeated calls.
first_open=min(datetime.fromisoformat(x['open_tr']) for x in shorts)
last_open=max(datetime.fromisoformat(x['open_tr']) for x in shorts)
first_candle=first_open.replace(second=0,microsecond=0)
last_candle=last_open.replace(second=0,microsecond=0)+timedelta(minutes=241)
bars,calls=klines(first_candle,last_candle)
def segment_for(entry,end):
    start=entry.replace(second=0,microsecond=0)+timedelta(minutes=1)
    end_floor=end.replace(second=0,microsecond=0)
    out=[]
    while start<end_floor:
        k=int(start.timestamp()*1000)
        if k not in bars:return None
        out.append(bars[k])
        start+=timedelta(minutes=1)
    return out
def tr(ms):return datetime.fromtimestamp(ms/1000,TR).isoformat(timespec='seconds')

ROIS=(.6,.95,1.2,1.65,2.0,2.5)
GIVEBACK={.6:.1,.95:.15,1.2:.15,1.65:.2,2.0:.2,2.5:.2}
# strict conservative "first hit" stop-first, triggers on favorable low
# then tests adverse high on next minute ONLY; same-minute sequencing unknown.
def trailing_proxy(path,entry,lever):
    results=[]
    for arm in ROIS:
        gb=GIVEBACK[arm]
        peak=0.0;armed=False;trigger=None;ambiguous=0
        for bar in path:
            low=(entry-bar['l'])/entry*lever*100
            high=(entry-bar['h'])/entry*lever*100
            # previous peak guard, then same-bar favorable advance
            if armed and peak-high>=gb:
                trigger={'time_tr':tr(bar['t']),'price_proxy':bar['h'],
                         'gross_roi_pct_price_proxy':round(high,3),
                         'prior_peak_roi_pct':round(peak,3),
                         'mechanism':'bar_high_conservative_proxy_not_live_fill'}
                break
            if low>=arm and not armed:armed=True
            peak=max(peak,low)
            if armed and peak-high>=gb:ambiguous+=1
        results.append({'arm_roi_pct':arm,'giveback_roi_points':gb,
          'activated':armed,'trigger_proxy':trigger,
          'ambiguous_same_bar_occurrences':ambiguous,
          'execution_estimate_not_valid':True})
    return results

results=[]
for original in shorts:
    open_time=datetime.fromisoformat(original['open_tr'])
    close_time=datetime.fromisoformat(original['close_tr'])
    entry=float(original['entry_price'])
    lev=float(original['leverage'])
    periods=[('original_long_hold',close_time),('60m',open_time+timedelta(minutes=60)),
              ('120m',open_time+timedelta(minutes=120)),('240m',open_time+timedelta(minutes=240))]
    seen=set();views={}
    for label,end in periods:
        path=segment_for(open_time,end)
        if path is None:views[label]={'status':'CENSORED_MISSING_DATA'};continue
        if not path:views[label]={'status':'NO_FULL_BAR'};continue
        peak=max(path,key=lambda q:(entry-q['l'])/entry)
        trough=min(path,key=lambda q:(entry-q['h'])/entry)
        max_short=(entry-peak['l'])/entry*lev*100
        worst_short=(entry-trough['h'])/entry*lev*100
        idx=path.index(peak)
        after=path[idx+1:]
        peak_roi=max_short
        # When short "turned back": min low price at peak, subsequent
        # high > low -> giveback; not necessarily tradable at that price.
        after_high=max(after,key=lambda q:q['h']) if after else None
        after_max_drawback=((after_high['h']-peak['l'])/entry*lev*100) if after_high else None
        first_levels={str(arm):tr(next(q['t'] for q in path
                 if (entry-q['l'])/entry*lev*100>=arm))
          for arm in ROIS if max_short>=arm}
        views[label]={
           'status':'COMPLETE_FULL_MINUTE_BARS_ONLY',
           'n_closed_bars':len(path),
           'short_mfe_roi_pct':round(max_short,3),
           'short_mae_roi_pct':round(worst_short,3),
           'short_mfe_low_price':round(peak['l'],6),
           'short_mfe_time_tr':tr(peak['t']),
           'short_worst_high_price':round(trough['h'],6),
           'short_worst_time_tr':tr(trough['t']),
           'short_roi_final_full_bar_close_pct':round((entry-path[-1]['c'])/entry*lev*100,3),
           'max_reversal_after_best_roi_points':round(after_max_drawback,3) if after_max_drawback is not None else None,
           'max_reversal_after_best_time_tr':tr(after_high['t']) if after_high else None,
           'first_arm_touch_time_tr':first_levels,
           'trailing_proxy':trailing_proxy(path,entry,lev),
           'intraminute_sequence_unknown':True,
           'entry_and_exit_minute_excluded':True
        }
    # SHORT with same original LONG close is independent counterfactual,
    # ignores costs and whether a short signal was actually produced.
    actual_short_mark_roi=(entry-float(original['exit_price']))/entry*lev*100
    results.append({
      'original_long_open_tr':original['open_tr'],
      'original_long_close_tr':original['close_tr'],
      'user_reference':'LONG_AVOID',
      'same_price_hypothetical_short_entry':entry,
      'actual_long_realized_gross_roi_pct':original['gross_roi_pct'],
      'hypothetical_short_roi_at_long_close_pct':round(actual_short_mark_roi,3),
      'short_hypothesis_only':True,
      'opposite_bot_short1_symbol_not_nearusdt':True,
      'windows':views,
      'original_long_id_not_shared':True
    })

missed=[]
for m in targets:
    t=m['ts_tr']
    f=first_by_ts[t]
    near=[row for row in wanted_intents
          if abs((datetime.fromisoformat(row['intent_time_tr'])-datetime.fromisoformat(t)).total_seconds())<=180]
    # Near-clock is explicitly NOT exact source model->intent join.
    missed.append({
       'timestamp_tr':t,'model_close_id_legacy':m['close_id'],
       'score':f['model_score'],'rolling_threshold':f['actual_rolling_threshold'],
       'score_above_rolling':f['model_score']>=f['actual_rolling_threshold'],
       'context_v2':m['decision'],'context_v2_reason':m['reason'],
       'flow_asof_available':m['flow_available'],
       'fwd_model_ref_close':f['reference_close'],
       'hypothetical_60m_first_hit':f['horizons']['60']['status'],
       'hypothetical_60m_first_tp_time_tr':f['horizons']['60'].get('tp_touched_tr'),
       'hypothetical_60m_first_sl_time_tr':f['horizons']['60'].get('sl_touched_tr'),
       'first_hit_not_actual_entry':True,
       'nearby_trade_intents_not_exact_trace':len(near),
       'nearby_intent_reason_histogram_not_attributed':
          dict(Counter(x['evidence_reason'] for x in near)),
       'exact_model_to_intent_trace_present':False
    })
assert len(missed)==11
assert all(x['hypothetical_60m_first_hit']=='TP_FIRST' for x in missed)
assert sum(x['score_above_rolling'] for x in missed)<=11
output={
 'schema':'long1_user_window_11_missed_and_4_opposite_shorts_research_v1',
 'window_tr':['2026-11-11','2026-11-15'],
 'user_reference_source':'BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json',
 'missing_opportunity_model_events':11,
 'target_trade_intents_total':9,
 'target_broker_opens':0,
 'opposite_short_scenarios':len(results),
 'model_to_intent_legacy_parent_identity_missing':True,
 'opposite_short1_INJUSDT_not_simulated':True,
 'opposite_position_same_NEARUSDT_price_only':True,
 'short_live_exchange_does_not_exist':True,
 'short_liquidation_and_realistic_execution_not_simulated':True,
 'price_ohlc_full_minute_only':True,
 'entry_bar_excluded':True,
 'retro_research_only':True,
 'orders_sent':0,'production_redis_writes':0,
 'public_price_api_calls':calls,
 'missed_model_events':missed,
 'opposite_short_from_four_long_avoid_entries':results
}
out=ROOT/'LONG1_MISSED_11_AND_OPPOSITE_SHORT_4_PRICE_PATH_20261118.json'
out.write_text(json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','missed_model':len(missed),'opposite_short':len(results),
 'price_get_calls':calls,'scenarios':[
   {'opened':x['original_long_open_tr'],
    'at_long_close':x['hypothetical_short_roi_at_long_close_pct'],
    '60m_mfe':x['windows']['60m'].get('short_mfe_roi_pct'),
    '120m_mfe':x['windows']['120m'].get('short_mfe_roi_pct'),
    '240m_mfe':x['windows']['240m'].get('short_mfe_roi_pct'),
    'original_hold_mfe':x['windows']['original_long_hold'].get('short_mfe_roi_pct')}
 for x in results],
 'no_orders':True},sort_keys=True))
