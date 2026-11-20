"""Read-only: EXACT 84 original strict LONG_AVOID candidates, ordered aggTrades.

Retrospective LONG_AVOID labels select comparison COHORT only; not a live
entry policy. Signal is original fully closed 1m => next 1m open assumption.
Compare same entry universe under fifth-minute flat exit and tick-ordered
six-stage 0.22/0.35 ARM, partial sells, 5m exit. Also optional 60m
sensitivity on SAME entries, NOT a valid 60m single-position portfolio.
Price MFE timestamps are observations AFTER entry, NEVER features.
AggTrades are prints, not guaranteed executable fills.
"""
from __future__ import annotations
from pathlib import Path
from zipfile import ZipFile
from io import TextIOWrapper
from datetime import datetime
from zoneinfo import ZoneInfo
from bisect import bisect_left
from collections import Counter
import csv,gzip,json
R=Path(__file__).resolve().parents[2];OUT=R/'research/results';TR=ZoneInfo('Europe/Istanbul')
W=json.loads((OUT/'LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json').read_text())
rows=[r for r in W['development']['book_strict']['trades'] if r['cohort']=='LONG_AVOID']
assert len(rows)==84 and sum(r['end_5m_net_roi_pp']>0 for r in rows)==6
assert sum(r['end_5m_net_roi_pp']<0 for r in rows)==78
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 bars=[{'t':int(x['open_time_ms']),'o':float(x['open'])} for x in csv.DictReader(f)]
assert len(bars)==8640
ticks=[];day_counts={}
D=R/'research/local_market_data/near_usdm_20261110_15'
for day in range(11,16):
 with ZipFile(D/f'NEARUSDT-aggTrades-2026-11-{day:02d}.zip') as z:
  with z.open(z.namelist()[0]) as f:
   day_rows=[(int(t['transact_time']),int(t['agg_trade_id']),float(t['price'])) for t in csv.DictReader(TextIOWrapper(f,encoding='utf-8'))]
 assert day_rows
 day_counts[f'2026-11-{day:02d}']=len(day_rows);ticks.extend(day_rows)
assert sum(day_counts.values())==len(ticks)==819943
assert all(ticks[j][:2]<=ticks[j+1][:2] for j in range(len(ticks)-1))
times=[z[0] for z in ticks]
tiers=((.22,.10),(.35,.10),(.50,.12),(.70,.14),(1.00,.18),(1.40,.20))
sell_fractions=(.10,.15,.15,.20,.20,.20)
assert abs(sum(sell_fractions)-1)<1e-12
FEE=.24
def time_tr(ms):
 return datetime.fromtimestamp(ms/1000,TR).isoformat()
def snap(i,minutes):
 bar_i=rows[i]['i']+1
 start=bars[bar_i]['t'];stop=start+minutes*60000
 l=bisect_left(times,start);r=bisect_left(times,stop)
 assert l<r,(i,start,stop)
 entry=bars[bar_i]['o']
 tdata=ticks[l:r]
 gross=[300*(t[2]/entry-1) for t in tdata]
 max_roi=max(gross);min_roi=min(gross)
 peak_idx=max(range(len(gross)),key=lambda k:gross[k])
 min_idx=min(range(len(gross)),key=lambda k:gross[k])
 after_peak_min=min(gross[peak_idx:])
 after_peak_min_idx=peak_idx+min(range(len(gross)-peak_idx),key=lambda j:gross[peak_idx+j])
 # Causally 3x gross ROI of actual prices; not entry capability.
 first_touch={}
 for threshold in (.22,.35,.50,.70,.80,1.00,1.40):
  j=next((j for j,x in enumerate(gross) if x>=threshold-1e-10),None)
  first_touch[f'{threshold:.2f}']=(time_tr(tdata[j][0]) if j is not None else None)
 return dict(start_ms=start,last_ms=tdata[-1][0],first_tick_delay_ms=tdata[0][0]-start,
    entry_price_assumed=entry,
    trade_count=len(tdata),
    peak_roi_pp=round(max_roi,6),peak_at_tr=time_tr(tdata[peak_idx][0]),
    trough_roi_pp=round(min_roi,6),trough_at_tr=time_tr(tdata[min_idx][0]),
    worst_after_peak_roi_pp=round(after_peak_min,6),
    worst_after_peak_at_tr=time_tr(tdata[after_peak_min_idx][0]),
    peak_to_worst_after_peak_drawdown_roi_pp=round(max_roi-after_peak_min,6),
    time_to_peak_seconds=round((tdata[peak_idx][0]-start)/1000,3),
    after_peak_to_worst_seconds=round((tdata[after_peak_min_idx][0]-tdata[peak_idx][0])/1000,3),
    first_arm_touch_times_tr=first_touch,
    final_tick_roi_pp=round(gross[-1],6),
    ticks=tdata)
def simulate(s,minutes,partial,extra=.0):
 tdata=s['ticks'];entry=s['entry_price_assumed'];stop=entry*(1-.0299)
 rest=1.;gain=0.;top=0.;floor=None;stage=-1;seen=set();fills=[]
 end_time=s['start_ms']+minutes*60000
 def take(fraction,price,at,reason):
  nonlocal rest,gain
  fraction=min(fraction,rest)
  if fraction<1e-9:return
  gross=300*(price/entry-1)
  net=gross-FEE-extra
  gain+=fraction*net;rest=max(0.,rest-fraction)
  fills.append({'reason':reason,'time_tr':time_tr(at),'price':price,
       'original_position_fraction':round(fraction,8),
       'gross_roi_pp_on_closed_piece':round(gross,6),
       'net_roi_pp_on_closed_piece':round(net,6)})
 why='TIMEOUT'
 for at,_id,p in tdata:
  roi=300*(p/entry-1)
  if p<=stop:
   take(rest,p,at,'STOP_TICK');why='STOP_TICK';break
  if floor is not None and roi<=floor:
   take(rest,p,at,'TRAIL_TICK');why='TRAIL_TICK';break
  top=max(roi,top)
  k=max((j for j,(arm,gb) in enumerate(tiers) if top>=arm),default=-1)
  if k>stage:
   stage=k
   if k>=0:
    floor=max(top-tiers[k][1],floor if floor is not None else float('-inf'))
    if partial:
     for j in range(k+1):
      if j not in seen:
       seen.add(j)
       take(sell_fractions[j],p,at,f'TIER_{j+1}')
     if rest<=1e-9:why='ALL_SLICES';break
  if k>=0:floor=max(floor,top-tiers[k][1])
 else:
  at,_id,p=tdata[-1]
  take(rest,p,at,'TIMEOUT_LAST_TICK')
 assert abs(sum(f['original_position_fraction'] for f in fills)-1)<1e-8
 return {'net_roi_pp':round(gain,6),'exit_reason':why,
   'exit_time_tr':fills[-1]['time_tr'],
   'stages_reached':stage+1,
   'partial_sales':sum(x['reason'].startswith('TIER_') for x in fills),
   'fills':fills}
def bucket(peak):
 if peak<0:return 'MFE_NEGATIVE'
 if peak<.22:return 'MFE_0_to_0p22'
 if peak<.35:return 'MFE_0p22_to_0p35'
 if peak<.50:return 'MFE_0p35_to_0p50'
 if peak<.80:return 'MFE_0p50_to_0p80'
 if peak<1.0:return 'MFE_0p80_to_1p00'
 if peak<1.40:return 'MFE_1p00_to_1p40'
 return 'MFE_1p40plus'
records=[]
for n,orig in enumerate(rows):
 five=snap(n,5)
 sixty=snap(n,60)
 s5=simulate(five,5,True)
 s5_runner=simulate(five,5,False)
 s60=simulate(sixty,60,True)
 five_01=simulate(five,5,True,.1)
 records.append({'index':n+1,'origin_close_tr':time_tr(orig['time_ms']),
  'entry_next_open_tr':time_tr(five['start_ms']),
  'entry_price_assumed':five['entry_price_assumed'],
  'legacy_fifth_close_net_roi_pp':orig['end_5m_net_roi_pp'],
  'legacy_original_profitable':orig['end_5m_net_roi_pp']>0,
  'original_strict_features':orig['features'],
  'first_tick_delay_ms':five['first_tick_delay_ms'],
  'five_minute_price_path':{k:v for k,v in five.items() if k!='ticks'},
  'sixty_minute_price_path':{k:v for k,v in sixty.items() if k!='ticks'},
  'five_minute_partial':s5,'five_minute_runner':s5_runner,
  'five_minute_partial_extra_0p10':five_01,
  'sixty_minute_partial_OVERLAPPING_SENSITIVITY_ONLY':s60,
  'five_minute_mfe_bin':bucket(five['peak_roi_pp'])})
def summary(recs):
 a=Counter()
 a['positions']=len(recs)
 a['legacy_positive']=sum(z['legacy_original_profitable'] for z in recs)
 a['legacy_negative']=sum(not z['legacy_original_profitable'] for z in recs)
 for k in ('five_minute_partial','five_minute_runner',
           'five_minute_partial_extra_0p10','sixty_minute_partial_OVERLAPPING_SENSITIVITY_ONLY'):
  a[k+'_wins']=sum(z[k]['net_roi_pp']>0 for z in recs)
  a[k+'_losses']=sum(z[k]['net_roi_pp']<0 for z in recs)
  a[k+'_total_net_roi_pp']=round(sum(z[k]['net_roi_pp'] for z in recs),6)
  a[k+'_partial_sale_events']=sum(z[k]['partial_sales'] for z in recs)
  a[k+'_exits']=dict(Counter(z[k]['exit_reason'] for z in recs))
 a['legacy_total_net_roi_pp']=round(sum(z['legacy_fifth_close_net_roi_pp'] for z in recs),6)
 for threshold in (.22,.35,.50,.70,.80,1.,1.40):
  a[f'peak_5m_ge_{threshold:.2f}']=sum(z['five_minute_price_path']['peak_roi_pp']>=threshold-1e-6 for z in recs)
 a['mfe_5m_buckets']=dict(Counter(z['five_minute_mfe_bin'] for z in recs))
 a['5m_peak_then_trades_back_below_entry']=sum(
  z['five_minute_price_path']['peak_roi_pp']>0
  and z['five_minute_price_path']['worst_after_peak_roi_pp']<0 for z in recs)
 return dict(a)
losses=[z for z in records if not z['legacy_original_profitable']]
wins=[z for z in records if z['legacy_original_profitable']]
assert len(losses)==78 and len(wins)==6
out={'schema':'long1_84_avoid_strict_aggtrade_reversal_scaleout_v1',
 'period':'2026-11-11_to_2026-11-15_TRT',
 'source':'research/results/LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json',
 'exact_source_strict_avoid_candidates':84,
 'source_legacy_loss_count':78,'source_legacy_win_count':6,
 'aggtrade_rows_observed':len(ticks),'input_archive_rows_by_utc_day':day_counts,
 'six_arm_roi_thresholds':[z[0] for z in tiers],
 'six_giveback_roi_points':[z[1] for z in tiers],
 'six_sale_fractions_original_position':sell_fractions,
 'fee_3x_roi_pp_per_fraction':FEE,'extra_cost_test_pp':.1,
 'entry_price_is_hypothetical_next_1m_open':True,
 'ordered_market_prints_not_guaranteed_exchange_fills':True,
 'all_eighty_four_same_entries_across_profiles':True,
 'fifth_minute_and_60minute_not_comparable_as_1position_books':True,
 '60minute_sensitivity_overlapping_entries_not_joint_portfolio':True,
 'legacy_5m_close_not_dynamic_tp':True,
 'original_user_avoid_is_reporting_cohort_not_live_trade_gate':True,
 'historical_user_labels_never_create_signals':True,
 'no_real_new_model_intent_or_exact_market_context_proof':True,
 'no_riskmaster_or_actual_broker_position_reconstruction':True,
 'no_native_exchange_stop_spread_order_book_or_execution_latency':True,
 'live_orders':0,'production_redis_writes':0,
 'all':summary(records),'legacy_78_losing':summary(losses),
 'legacy_6_winning':summary(wins),
 'trades':records}
p=OUT/'LONG1_84_AVOID_AGGTRADE_6STAGE_REVERSAL_ANALYSIS_20261120.json'
p.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'status':'PASS','all':out['all'],'legacy_78_losing':out['legacy_78_losing'],
 'archive_rows':len(ticks),'orders':0},sort_keys=True))
