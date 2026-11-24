"""Stage23: frozen 103 archived MODEL events, stage13 proxy research READY,
stage20 asof candle, stage21 flow, aggTrade timestamp-ordered TP035/SL.
Two horizons, single-position rebased selection, NO live execution authority.

Retrospective sample already used for rule design; not out of sample.
Historical broker occupied at entry is an advisory proxy only.
Ideal TP price touch and 1m open entry; bid/ask/liquidity absent.
"""
from __future__ import annotations
from bisect import bisect_left
from collections import Counter
from datetime import datetime
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile
import csv,gzip,json
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'research/results'
STAGE13=json.loads((OUT/'LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
STAGE20=json.loads((OUT/'LONG1_STAGE20_ASOF_3M5M_CANDLE_PENDING_EVIDENCE_20261124.json').read_text())
STAGE21=json.loads((OUT/'LONG1_STAGE21_FLOW_CONTEXT_PENDING_PROOF_20261124.json').read_text())
assert len(STAGE13['events'])==len(STAGE20['research_event_rows'])==len(STAGE21['details'])==103
assert all(a['model_time_tr']==b['model_time_tr']==c['model_time_tr'] for a,b,c in
 zip(STAGE13['events'],STAGE20['research_event_rows'],STAGE21['details']))
with gzip.open(ROOT/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 bars={int(x['open_time_ms']):float(x['open']) for x in csv.DictReader(f)}
assert len(bars)==8640
ticks=[]
for day in range(11,16):
 with ZipFile(ROOT/f'research/local_market_data/near_usdm_20261110_15/NEARUSDT-aggTrades-2026-11-{day:02d}.zip') as z:
  with z.open(z.namelist()[0]) as stream:
   ticks.extend((int(v['transact_time']),int(v['agg_trade_id']),float(v['price']))
     for v in csv.DictReader(TextIOWrapper(stream)))
assert len(ticks)==819943
assert all(ticks[i][:2]<=ticks[i+1][:2] for i in range(len(ticks)-1))
tms=[z[0] for z in ticks]
FEE=.24;TP=.35;STOP_PRICE_PERCENT=-2.99
def exit_replay(entry_ms,entry_price,horizon_min,extra_cost=.0):
 assert 0<=extra_cost<=.2 and horizon_min in (5,60)
 horizon=entry_ms+horizon_min*60000
 if horizon>tms[-1]:
  return {'reason':'CENSORED_SOURCE_END','net_roi_pp':None,'exit_ms':None,
   'trade_horizon_complete':False}
 a=bisect_left(tms,entry_ms);b=bisect_left(tms,horizon)
 if a>=b:return {'reason':'NO_TICKS','net_roi_pp':None,'exit_ms':None,
   'trade_horizon_complete':False}
 stop=entry_price*(1+STOP_PRICE_PERCENT/100)
 for tm,tid,px in ticks[a:b]:
  gross=300*(px/entry_price-1)
  if px<=stop:
   return {'reason':'STOP_TICK','net_roi_pp':round(gross-FEE-extra_cost,6),
    'exit_ms':tm,'trade_horizon_complete':True}
  if gross>=TP:
   return {'reason':'TP035_TOUCH_IDEAL_LIMIT_FILL',
    'net_roi_pp':round(TP-FEE-extra_cost,6),
    'exit_ms':tm,'trade_horizon_complete':True}
 tm,tid,px=ticks[b-1]
 gross=300*(px/entry_price-1)
 return {'reason':'TIMEOUT_LAST_TICK',
  'net_roi_pp':round(gross-FEE-extra_cost,6),'exit_ms':tm,
  'trade_horizon_complete':True}
candidates=[]
for idx,(a,b,c) in enumerate(zip(STAGE13['events'],STAGE20['research_event_rows'],STAGE21['details'])):
 if a['decision']!='RESEARCH_READY_NO_REAL_INTENT':continue
 entry=int(a['research_entry_ms'])
 assert entry==int(b['research_1m_entry_decision_ms'])==int(c['research_decision_asof_ms'])
 assert abs(bars[entry]-a['entry_price'])<1e-10
 proxy=b['research_proxy_revalidation']['status']=='RESEARCH_CANDLE_PROXY_READY_NOT_LIVE'
 broad=c['research_market_context_result']=='ARCHIVE_RESEARCH_SUPPORT_ONLY'
 assert c['investigated'] and not c['real_order_authority']
 cand={'model_time_tr':a['model_time_tr'],'retrospective_label_only':a['label'],
 'research_proxy_entry_ms':entry,'research_entry_price':a['entry_price'],
 'broker_occupied_at_research_entry_proxy':a['overlaps_real_broker_long'],
 'research_stage20_price_candle_fresh_up':proxy,
 'research_stage21_all_price_flow_favorable':broad,
 'research_stage21_context_reason':c['research_market_context_result'],
 'full_model_intent_sniper_entry_risk_authority_verified':False,
 'synthetic_origin_intent_is_not_real':True,
 'exits':{}}
 for m in (5,60):
  for extra in (0.,.10):
   cand['exits'][f'{m}m_extra_{extra:.2f}']=exit_replay(entry,a['entry_price'],m,extra)
 candidates.append(cand)
assert len(candidates)==32
assert sum(z['research_stage20_price_candle_fresh_up'] for z in candidates)==20
assert sum(z['research_stage21_all_price_flow_favorable'] for z in candidates)==0
def choose(profile,c):
 if profile=='STAGE13_1M_ONLY':return True
 if profile=='STAGE20_PRICE_FRESH_3M5M':return c['research_stage20_price_candle_fresh_up']
 if profile=='STAGE21_PRICE_PLUS_SIGNED_FLOW_3_5_15_60':
  return c['research_stage20_price_candle_fresh_up'] and c['research_stage21_all_price_flow_favorable']
 if profile=='PRODUCTION_PROVEN_END_TO_END':return c['full_model_intent_sniper_entry_risk_authority_verified']
 raise ValueError(profile)
def settle(profile,horizon,extra,broker=False):
 initial=[z for z in candidates if choose(profile,z) and (not broker or not z['broker_occupied_at_research_entry_proxy'])]
 booked=[];busy_until=-1
 k=f'{horizon}m_extra_{extra:.2f}'
 for z in initial:
  if z['research_proxy_entry_ms']<busy_until:continue
  ex=z['exits'][k]
  if not ex['trade_horizon_complete']:continue
  booked.append(z);busy_until=ex['exit_ms']+1
 values=[z['exits'][k]['net_roi_pp'] for z in booked]
 return {'eligible':len(initial),'booked_nonoverlap':len(booked),
  'excluded_due_to_source_censor':sum(not z['exits'][k]['trade_horizon_complete'] for z in initial),
  'wins':sum(v>0 for v in values),'losses':sum(v<0 for v in values),
  'net_roi_points_sum':round(sum(values),6),
  'mean_net_roi_per_booked_trade':round(sum(values)/len(values),6) if values else None,
  'assumed_500usdt_margin_sum_pnl_usdt':round(sum(values)*5,4),
  'assumed_250usdt_margin_sum_pnl_usdt':round(sum(values)*2.5,4),
  'exit_reasons':dict(Counter(z['exits'][k]['reason'] for z in booked)),
  'model_times':[z['model_time_tr'] for z in booked],
  'real_orders_placed':0}
scenarios={}
for p in ('STAGE13_1M_ONLY','STAGE20_PRICE_FRESH_3M5M',
          'STAGE21_PRICE_PLUS_SIGNED_FLOW_3_5_15_60','PRODUCTION_PROVEN_END_TO_END'):
 cases={}
 for m in (5,60):
  for extra in (0.,.10):
   for broker in (False,True):
    cases[f'{m}m_extra_{extra:.2f}_broker_occupancy_{broker}']=settle(p,m,extra,broker)
 scenarios[p]=cases
out={'schema':'long1_stage23_model103_aggtrade_tp035_endtoend_failclosed_sim_v1',
 'source_real_model_event_count':103,'stage13_research_ready':32,
 'stage20_price_recovery_proxy':20,'stage21_all_flows_and_price_support_proxy':0,
 'production_proven_order_authority':0,
 'fully_closed_prior_1m_only':True,'entry_assumed_next_1m_open':True,
 'exits_follow_original_binance_aggtrade_order':True,
 'actual_live_model_intent_and_pending_proof_absent':True,
 'research_cohort_used_to_design_gates_in_sample':True,
 'broker_occupancy_only_proxy_at_entry_not_full_real_risk_reconstruction':True,
 'risk_master_global_coin_lock_not_reconstructed':True,
 'fill_at_limit_touch_optimistic':True,
 'stop_is_price_minus_2p99_percent_not_roi_minus_2p99':True,
 'stop_before_tp_in_same_tick_sequence':True,
 'fixed_tp_gross_roi_pp':TP,'three_x_leverage':3,
 'assumed_roundtrip_fee_roi_pp':FEE,
 'extra_cost_sensitivity_roi_pp':.10,
 'funding_spread_latency_orderbook_liquidity_not_modeled':True,
 'per_trade_500usd_margin_independent_not_equity_compounding':True,
 'no_rebook_of_rejected_stage13_candidates':True,
 'source_tick_count':len(ticks),
 'real_orders_sent':0,'production_redis_writes':0,'service_restart':False,
 'scenarios':scenarios,'candidate_details':candidates}
dst=OUT/'LONG1_STAGE23_MODEL103_TP035_EXECUTION_PROXY_SIM_20261124.json'
dst.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'status':'PASS','source_model':103,'research_candidates':32,
 'price_context_keep':20,'all_flow_context_keep':0,
 'scenarios_summary':{p:{k:{q:v[q] for q in ('eligible','booked_nonoverlap','wins','losses','net_roi_points_sum')} for k,v in c.items() if k in ('5m_extra_0.00_broker_occupancy_False','60m_extra_0.00_broker_occupancy_False','5m_extra_0.00_broker_occupancy_True')} for p,c in scenarios.items()},
 'orders':0},sort_keys=True))
