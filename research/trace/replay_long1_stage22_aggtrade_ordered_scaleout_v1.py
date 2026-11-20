"""LONG1 research-only ordered Binance aggTrade execution-price proxy.

Stage13 entries and selection fixed. Before the first tick at or after each
hypothetical next-1m-open timestamp, none of the future prices are known.
Each aggregate trade is a sequential market print, NOT an executable book
quote/guaranteed fill. Same-ms events sorted by stable agg_trade_id.
Stop checked BEFORE arm and scale-out on each event, conservative stop priority.
Tier activation and partial sales at the observed trade price are optimistic
zero-latency fills. Trailing may close residual after same-ms tier activation
(if price turns), and realised net ROI is fee-charged proportionally.
No external requests or production writes.
"""
from __future__ import annotations
from pathlib import Path
from zipfile import ZipFile
from io import TextIOWrapper
from collections import Counter
from bisect import bisect_left,bisect_right
import csv,gzip,json,datetime
R=Path(__file__).resolve().parents[2];OUT=R/'research/results'
S=json.loads((OUT/'LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
P=json.loads((OUT/'LONG1_2000USDT_4_8BOT_022_035_SIX_STAGE_PARTIAL_REPLAY_20261120.json').read_text())
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 bars=[dict(t=int(z['open_time_ms']),o=float(z['open']),c=float(z['close'])) for z in csv.DictReader(f)]
assert len(bars)==8640
ready=[z for z in S['events'] if z['decision']=='RESEARCH_READY_NO_REAL_INTENT']
assert len(ready)==32
# 1m archive starts 10 Nov UTC; 11-15 Nov aggTrades archived.
ticks=[]
count_by_day={}
source_dir=R/'research/local_market_data/near_usdm_20261110_15'
for day in range(11,16):
 file=source_dir/f'NEARUSDT-aggTrades-2026-11-{day:02d}.zip'
 with ZipFile(file) as z:
  assert len(z.namelist())==1
  with z.open(z.namelist()[0]) as f:
   reader=csv.DictReader(TextIOWrapper(f,encoding='utf-8'))
   assert set(('agg_trade_id','price','transact_time')).issubset(reader.fieldnames)
   day_ticks=[(int(x['transact_time']),int(x['agg_trade_id']),float(x['price'])) for x in reader]
 assert day_ticks and all(day_ticks[k][:2]<=day_ticks[k+1][:2] for k in range(len(day_ticks)-1))
 count_by_day[f'2026-11-{day:02d}']=len(day_ticks)
 ticks.extend(day_ticks)
assert all(ticks[k][:2]<=ticks[k+1][:2] for k in range(len(ticks)-1))
T=[v[0] for v in ticks]
TIER=[(.22,.10),(.35,.10),(.50,.12),(.70,.14),(1.,.18),(1.40,.20)]
OLD=[(.22,.10),(.40,.10),(.60,.12),(.80,.15),(1.10,.18),(1.50,.20)]
PORTIONS=[.10,.15,.15,.20,.20,.20]
assert abs(sum(PORTIONS)-1)<1e-10
FEE=.24
def trace(entry_idx,tiers,partial,extra_cost_pp=0):
 entry_ms=bars[entry_idx]['t'];start=bisect_left(T,entry_ms);end=bisect_left(T,entry_ms+60*60000)
 assert end>start,(entry_ms,'no aggTrade')
 entry=bars[entry_idx]['o']
 first_delay_ms=T[start]-entry_ms
 stop=entry*(1-.0299)
 peak=0.;floor=None;rest=1.;realized=0.;stage=-1
 fills=[];seen=set();final='TIMEOUT'
 def take(frac,pr,reason,tm):
  nonlocal rest,realized
  frac=min(rest,frac)
  if frac<1e-9:return
  roi=300*(pr/entry-1)-FEE-extra_cost_pp
  realized+=frac*roi;rest=max(0,rest-frac)
  fills.append({'reason':reason,'timestamp_ms':tm,
   'closed_original_fraction':round(frac,8),'trade_price_proxy':pr,
   'net_roi_on_closed_fraction_pp':round(roi,6)})
 for tm,aggid,pr in ticks[start:end]:
  roi=300*(pr/entry-1)
  if pr<=stop:
   take(rest,pr,'STOP_TICK',tm);final='STOP_TICK';break
  if floor is not None and roi<=floor:
   take(rest,pr,'TRAIL_TICK',tm);final='TRAIL_TICK';break
  peak=max(peak,roi)
  k=max((i for i,(arm,g) in enumerate(tiers) if peak>=arm),default=-1)
  if k>stage:
   stage=k
   if k>=0:
    floor=max(peak-tiers[k][1],floor if floor is not None else float('-inf'))
    if partial:
     for n in range(k+1):
      if n not in seen:
       seen.add(n)
       take(PORTIONS[n],pr,f'STAGE_{n+1}',tm)
     if rest<=1e-9:final='ALL_STAGES_FILLED';break
  if k>=0:
   floor=max(floor,peak-tiers[k][1])
 else:
  # Last observed tick prior to 60m expiry, as a market-print proxy.
  take(rest,ticks[end-1][2],'TIMEOUT_LAST_TICK',ticks[end-1][0])
 assert rest<1e-8 and abs(sum(v['closed_original_fraction'] for v in fills)-1)<1e-7
 return {'entry_idx':entry_idx,'entry_price_next_1m_open':entry,
   'first_tick_delay_ms':first_delay_ms,
   'last_tick_proxy_time_ms':fills[-1]['timestamp_ms'],
   'exit_idx':min(len(bars)-1,max(entry_idx,int((fills[-1]['timestamp_ms']-bars[0]['t'])//60000))),
   'exit_reason':final,'highest_armed_stage':stage+1,
   'net_roi_pp':round(realized,6),
   'number_partial_sales':sum(v['reason'].startswith('STAGE_') for v in fills),
   'fills':fills}
def book(tiers,partial,extra,occupancy=False):
 busy_time_ms=-1;items=[]
 for r in ready:
  entry_ms=bars[r['entry_idx']]['t']
  if entry_ms<=busy_time_ms or (occupancy and r['overlaps_real_broker_long']):continue
  result=trace(r['entry_idx'],tiers,partial,extra)
  items.append({'model_time_tr':r['model_time_tr'],'reference_label':r['label'],
   **result})
  busy_time_ms=result['last_tick_proxy_time_ms']
 return {'opens':len(items),'net_roi_pp_total':round(sum(v['net_roi_pp'] for v in items),6),
  'wins':sum(v['net_roi_pp']>0 for v in items),'losses':sum(v['net_roi_pp']<0 for v in items),
  'exits':dict(Counter(v['exit_reason'] for v in items)),
  'partial_fills':sum(v['number_partial_sales'] for v in items),
  'first_tick_delay_ms_max':max(v['first_tick_delay_ms'] for v in items),
  'mean_net_roi_pp':round(sum(v['net_roi_pp'] for v in items)/len(items),6),
  'trades':items}
profiles={}
for name,tiers,partial in (
 ('requested_022_035_six_stage_partial',TIER,True),
 ('requested_022_035_six_stage_runner',TIER,False),
 ('old_022_040_six_stage_partial',OLD,True)):
 data={}
 for extra in (0,.05,.10,.20):
  q=book(tiers,partial,extra)
  broker=book(tiers,partial,extra,True)
  data[str(extra)]={'no_broker_veto':q,'historical_broker_occupancy_veto':broker,
    'four_bot_fixed_500_usdt_one_long1_pnl':round(5*q['net_roi_pp_total'],5),
    'eight_bot_fixed_250_usdt_one_long1_pnl':round(2.5*q['net_roi_pp_total'],5)}
 profiles[name]=data
out={'schema':'long1_stage22_ordered_aggtrade_six_stage_4_8_bot_v1',
 'asof_model_ready_candidates_from_stage13':32,
 'data_period':'2026-11-11_to_2026-11-15_TRT',
 'official_aggtrade_archive_rows_by_utc_day':count_by_day,
 'aggtrade_intra_minute_ordering_observed':True,
 'entry_next_one_minute_open_hypothetical_not_trade_fill':True,
 'tier_activate_first_trade_at_threshold_or_higher':True,
 'tier_sells_first_trade_at_or_above_threshold':True,
 'tier_same_timestamp_ordered_by_agg_trade_id':True,
 'trailing_stop_trade_price_proxy_not_real_order_fill':True,
 'same_trade_stop_checked_before_arm':True,
 'fee_roundtrip_roi_pp_base':FEE,
 'extra_roundtrip_execution_cost_roi_pp_tested':[0,.05,.10,.20],
 'source_of_extra_cost_hypothetical_not_real_spread':True,
 'tick_prices_not_orderbook_or_guaranteed_fills':True,
 'one_coin_one_position_occupancy':True,
 'full_position_stop_price_pct':2.99,
 'no_native_stop_or_true_new_model_intent':True,
 'min_notional_step_size_and_partial_ACK_not_verified':True,
 'no_nov16_aggtrade_file_available_for_tick_holdout':True,
 'four_bot_each_margin_usdt':500,'eight_bot_each_margin_usdt':250,
 'profit_units_only_one_long1_not_4_or_8_bot_portfolio':True,
 'no_production_changes':True,'live_binance_orders':0,'production_redis_writes':0,
 'profiles':profiles}
p=OUT/'LONG1_STAGE22_REAL_AGGTRADE_022_035_TIERED_SCALEOUT_20261120.json'
p.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','aggregate_trades_loaded':sum(count_by_day.values()),
 'utc_days':count_by_day,
 'result_summary':{k:{extra:{
 'opened':v['no_broker_veto']['opens'],
 'roi_pp':v['no_broker_veto']['net_roi_pp_total'],
 'stops':v['no_broker_veto']['exits'],
 'partial_sales':v['no_broker_veto']['partial_fills'],
 'broker_veto_roi':v['historical_broker_occupancy_veto']['net_roi_pp_total']
 } for extra,v in values.items()} for k,values in profiles.items()},
 'real_orders':0},sort_keys=True))
