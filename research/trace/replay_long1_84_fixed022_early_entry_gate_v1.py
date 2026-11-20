"""Research-only 84 unchanged LONG_AVOID entries vs hard 0.22 ROI TP.

Read pre-stored official Binance aggTrades timestamp+id sequence. For
each entry 5m window uses hypothetical NEXT-1m-open buy, first tick
crossing hard TP, -2.99% price stop, and timeout LAST TICK (a proxy).
Stop-first each tick; real price order and bid/ask fills unavailable.
Ex-ante baseline gate comparisons use only completed 1m as-of features.
False rejection in other cohort and Nov16 separately measured using
existing fixed first-hour candidate features; no time whitelist.
"""
from pathlib import Path
from zipfile import ZipFile
from io import TextIOWrapper
from bisect import bisect_left
from collections import Counter
import gzip,csv,json
R=Path(__file__).resolve().parents[2];OUT=R/'research/results'
SOURCE=json.loads((OUT/'LONG1_84_AVOID_AGGTRADE_6STAGE_REVERSAL_ANALYSIS_20261120.json').read_text())
REF=json.loads((OUT/'LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json').read_text())
TRADES=SOURCE['trades']
assert len(TRADES)==84
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 bars=[dict(t=int(x['open_time_ms']),o=float(x['open'])) for x in csv.DictReader(f)]
ticks=[]
for day in range(11,16):
 with ZipFile(R/f'research/local_market_data/near_usdm_20261110_15/NEARUSDT-aggTrades-2026-11-{day:02d}.zip') as z:
  with z.open(z.namelist()[0]) as f:
   ticks.extend((int(v['transact_time']),int(v['agg_trade_id']),float(v['price'])) for v in csv.DictReader(TextIOWrapper(f)))
assert len(ticks)==819943 and all(ticks[i][:2]<=ticks[i+1][:2] for i in range(len(ticks)-1))
TIMES=[z[0] for z in ticks]
BASE_FEE=.24
def tp_sim(t,hardtp=.22,extra=.0):
 entry_idx=int((int(__import__('datetime').datetime.fromisoformat(t['entry_next_open_tr']).timestamp()*1000)-bars[0]['t'])//60000)
 assert bars[entry_idx]['o']==t['entry_price_assumed']
 entry=bars[entry_idx]['o'];start=bars[entry_idx]['t']
 a=bisect_left(TIMES,start);b=bisect_left(TIMES,start+5*60000)
 assert b>a
 stop=entry*(1-.0299)
 for tm,tid,p in ticks[a:b]:
  roi=300*(p/entry-1)
  if p<=stop:return {'reason':'STOP_TICK','gross_roi_pp':round(roi,6),'net_roi_pp':round(roi-BASE_FEE-extra,6),'exit_ms':tm}
  if roi>=hardtp:
   # idealized fixed price resting TP limit at threshold,
   # not the first market print above it, to avoid
   # granting gaps favorable slippage.
   return {'reason':'HARD_TP_TOUCH_IDEAL_FILL','gross_roi_pp':hardtp,
    'net_roi_pp':round(hardtp-BASE_FEE-extra,6),'exit_ms':tm}
 tm,tid,p=ticks[b-1];roi=300*(p/entry-1)
 return {'reason':'TIMEOUT_LAST_TICK','gross_roi_pp':round(roi,6),
  'net_roi_pp':round(roi-BASE_FEE-extra,6),'exit_ms':tm}
def total(items):
 c=Counter()
 for z in items:
  c['n']+=1;c[z['reason']]+=1
  c['profitable']+=z['net_roi_pp']>0;c['loss']+=z['net_roi_pp']<0
  c['zero']+=z['net_roi_pp']==0
 c['net_roi_pp_sum']=round(sum(z['net_roi_pp'] for z in items),6)
 return dict(c)
cases={}
for tp in (.22,.35,.40,.50,.80,1.):
 a=[tp_sim(t,tp) for t in TRADES]
 b=[tp_sim(t,tp,.10) for t in TRADES]
 cases[f'{tp:.2f}']={
  'base':total(a),'extra_0p10_roi_pp':total(b),
  'fixed_500margin_pnl_usdt':round(5*sum(z['net_roi_pp'] for z in a),5),
  'fixed_250margin_pnl_usdt':round(2.5*sum(z['net_roi_pp'] for z in a),5),
  'trades':a}
# Gate experiments are NOT tuned/selected using future result labels.
# Demand a 5m upward conviction stronger than baseline from prior closes:
# r5>=0.20 and flow3>=0.25, or time-independent higher context
# r3<=0.20 "not overextended"; no gate may use the three known times.
GATES={
 'base_no_extra':lambda f:True,
 'five_minute_strength_ge_0p20pct':lambda f:f['r5']>=.20,
 'three_minute_flow_ge_0p25':lambda f:f['flow3']>=.25,
 'five_minute_strength_and_flow':lambda f:f['r5']>=.20 and f['flow3']>=.25,
 'three_minute_return_le_0p30pct':lambda f:f['r3']<=.30,
 'three_minute_return_le_0p20pct':lambda f:f['r3']<=.20}
groups={
 'avoid_84':TRADES,
 'wanted_original_strict_book':[z for z in REF['development']['book_strict']['trades'] if z['cohort']=='LONG_WANTED'],
 'holdout_nov16_original_strict_book':REF['nov16_holdout']['book_strict']['trades']}
def feature_of(z):return z.get('original_strict_features',z.get('features'))
gates={}
for name,rule in GATES.items():
 cohorts={}
 for cohort,items in groups.items():
  allowed=[z for z in items if rule(feature_of(z))]
  rejected=[z for z in items if not rule(feature_of(z))]
  c={'base_count':len(items),'accepted':len(allowed),'rejected':len(rejected)}
  if cohort=='avoid_84':
   # compares only historical 5m outcome; changing entry selection
   # changes chronology, so this is cohort-level filter diagnostic
   c['previous_net_loss_rejected']=sum(z['legacy_fifth_close_net_roi_pp']<0 for z in rejected)
   c['previous_net_win_rejected']=sum(z['legacy_fifth_close_net_roi_pp']>0 for z in rejected)
   c['rejected_3_target_times']=[z['entry_next_open_tr'] for z in rejected
    if any(z['entry_next_open_tr'].startswith(prefix) for prefix in
    ('2026-11-14T18:28','2026-11-14T01:01','2026-11-14T19:27'))]
   c['accepted_fixed_tp022_roi_sum']=round(sum(cases['0.22']['trades'][j]['net_roi_pp'] for j,z in enumerate(items) if rule(feature_of(z))),6)
  else:
   c['accepted_5m_net_sum']=round(sum(z['end_5m_net_roi_pp'] for z in allowed),6)
  cohorts[cohort]=c
 gates[name]=cohorts
target=[t for t in TRADES if any(t['entry_next_open_tr'].startswith(prefix) for prefix in
 ('2026-11-14T18:28','2026-11-14T01:01','2026-11-14T19:27'))]
assert len(target)==3
target_details=[]
for t in target:
 k=TRADES.index(t)
 target_details.append({'entry_time_tr':t['entry_next_open_tr'],
  'pre_entry_asof_closed_1m_features':t['original_strict_features'],
  'old_net_5m_roi_pp':t['legacy_fifth_close_net_roi_pp'],
  'maximum_gross_roi_5m_pp':t['five_minute_price_path']['peak_roi_pp'],
  'floor_after_peak_5m_pp':t['five_minute_price_path']['worst_after_peak_roi_pp'],
  'hard_tp022_result':cases['0.22']['trades'][k],
  'guards_that_exclude':[name for name,cohort in gates.items() if
    t['entry_next_open_tr'] in cohort['avoid_84'].get('rejected_3_target_times',[])]})
out={'schema':'long1_exact84_avoid_hardtp022_gates_asof_v1',
 'source_original_strict_84_unchanged':True,'positions':84,
 'source_legacy_78_losses':78,'source_legacy_6_wins':6,
 'source_timestamps_used_for_diagnostics_only':True,
 'filters_use_only_asof_completed_1m_bars':True,
 'not_original_live_model_intents':True,
 'not_live_3m5m_market_context':True,
 'one_original_book_chronology_not_rerun_after_gate':True,
 'six_tier_partial_fixed_5m_baseline_net_roi_pp':SOURCE['all']['five_minute_partial_total_net_roi_pp'],
 'source_original_fixed_5m_close_net_roi_pp':SOURCE['all']['legacy_total_net_roi_pp'],
 'same_aggtrade_archive_count':len(ticks),
 'fee_3x_roi_pp_assumption':BASE_FEE,
 'hard_tp_0p22_net_pp_after_fee':round(.22-.24,5),
 'hard_tp_0p22_not_net_profitable_at_assumed_fee':True,
 'tp_limit_touch_assumed_instant_execution_optimistic':True,
 'stop_first_on_aggtrade_print':True,
 'true_orderbook_bid_ask_slippage_funding_minqty_missing':True,
 'five_minute_time_stop_on_last_aggtrade':True,
 'whole_book_expected_4_or_8_bot_pnl_not_calculated':True,
 'replay_futures_signal_identity_not_verified':True,
 'real_orders':0,'prod_redis_writes':0,
 'fixed_tp_profiles':cases,
 'preentry_gate_screen':gates,'three_loss_examples':target_details}
p=OUT/'LONG1_AVOID84_FIXED_TP022_AND_PREENTRY_GATES_20261120.json'
p.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'status':'PASS',
 'fixed_tps':{k:{b:v for b,v in z.items() if b!='trades'} for k,z in cases.items()},
 'gate_screen':gates,'three_losses':target_details,'real_orders':0},sort_keys=True))
