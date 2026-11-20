"""Research: four/eight fixed bot capital envelopes with six-stage micro lock.

Explicit ambiguity: hard +0.80 ROI TP caps all later stages. A second
six-tier *runner* uses +0.80 as a SOFT milestone, NOT a resting TP order.
On actual 1m bars the earliest confirmed activation/peak is after candle
CLOSE. Exit on next open; cannot guarantee a locked ROI or intrabar fills.
Never simulates 4/8 simultaneous NEAR positions: central one-symbol lock.
"""
from pathlib import Path
from collections import Counter
import csv,gzip,json
R=Path(__file__).resolve().parents[2];OUT=R/'research/results'
s=json.loads((OUT/'LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 b=[dict(t=int(x['open_time_ms']),o=float(x['open']),h=float(x['high']),l=float(x['low']),c=float(x['close'])) for x in csv.DictReader(f)]
assert len(b)==8640
candidates=[x for x in s['events'] if x['decision']=='RESEARCH_READY_NO_REAL_INTENT']
assert len(candidates)==32
fee=.24
dynamic_tp_targets=(.80,1.00,1.20,1.50,1.80,2.30)
tiers_user=((.22,.10),(.40,.10),(.60,.12),(.80,.15),(1.10,.18),(1.50,.20))
# Comparator changes ONLY initial ARM so the locked floor exceeds fee.
tiers_feeaware=((.45,.10),(.60,.12),(.80,.15),(1.10,.18),(1.50,.20),(2.00,.20))
for tiers in (tiers_user,tiers_feeaware):
 assert len(tiers)==6 and all(tiers[i][0]<tiers[i+1][0] for i in range(5))
def trade(i,p):
 entry=b[i]['o'];stop=entry*(1-.0299)
 hard_tp=entry*(1+p['tp']/300) if p['tp'] is not None else None
 peak=0.;floor=None;armed_j=None;highest=-1
 for j in range(i,min(i+60,len(b)-1)):
  bar=b[j]
  # A dynamic TP can only be amended AFTER a previous fully
  # closed 1m candle. Assumes exchange cancel+replace succeeds
  # before next minute OPEN, an optimistic approximation.
  if p.get('dynamic_tp_targets') is not None:
   target_step=max(0,highest)
   hard_tp=entry*(1+p['dynamic_tp_targets'][target_step]/300)
  if bar['o']<=stop:return j,'STOP_GAP',round(300*(bar['o']/entry-1)-fee,5),highest
  if hard_tp is not None and bar['o']>=hard_tp:
   return j,'TP_GAP',round(300*(bar['o']/entry-1)-fee,5),highest
  if bar['l']<=stop:return j,'SL_FIRST',-9.21,highest
  if hard_tp is not None and bar['h']>=hard_tp:
   return j,'TP_FIRST',round(p['tp']-fee,5),highest
  # Bar CLOSE only: cannot use its HIGH as intrabar trailing evidence.
  roi=300*(bar['c']/entry-1)
  peak=max(peak,roi)
  k=max((idx for idx,(arm,gb) in enumerate(p['tiers']) if peak>=arm),default=-1)
  if k>=0:
   highest=max(highest,k)
   floor=max(peak-p['tiers'][k][1],floor if floor is not None else float('-inf'))
   if armed_j is None:armed_j=j
   # Old ARM cannot both activate and trigger on same CLOSE.
   if j>armed_j and roi<=floor:
    return j+1,'TRAIL_NEXT_OPEN',round(300*(b[j+1]['o']/entry-1)-fee,5),highest
 j=min(i+59,len(b)-1)
 return j,'TIMEOUT',round(300*(b[j]['c']/entry-1)-fee,5),highest
profiles={
 'hard_tp_0p80_6stage_first_arm_0p22':dict(tp=.80,tiers=tiers_user),
 'dynamic_tp_0p80_start_then_raise_six_stage':dict(tp=.80,tiers=tiers_user,dynamic_tp_targets=dynamic_tp_targets),
 'dynamic_tp_0p80_start_then_raise_feeaware':dict(tp=.80,tiers=tiers_feeaware,dynamic_tp_targets=dynamic_tp_targets),
 'soft_tp_0p80_6stage_runner_first_arm_0p22':dict(tp=None,tiers=tiers_user),
 'soft_tp_0p80_6stage_runner_feeaware_arm_0p45':dict(tp=None,tiers=tiers_feeaware),
 'hard_tp_0p80_no_trail_control':dict(tp=.80,tiers=()),
}
def build(p,with_broker=False):
 busy=-1;trades=[];tiers_seen=Counter()
 for z in candidates:
  if z['entry_idx']<=busy or (with_broker and z['overlaps_real_broker_long']):continue
  e,reason,roi,tier=trade(z['entry_idx'],p);busy=e
  trade_row={'model_time_tr':z['model_time_tr'],
    'research_label':z['label'],'entry_idx':z['entry_idx'],'exit_idx':e,
    'exit_reason':reason,'net_roi_pp':roi,'highest_armed_stage':tier+1}
  trades.append(trade_row)
  tiers_seen[tier+1]+=1
 return {'trades_count':len(trades),
 'total_net_roi_pp':round(sum(t['net_roi_pp'] for t in trades),5),
 'win_count':sum(t['net_roi_pp']>0 for t in trades),
 'loss_count':sum(t['net_roi_pp']<0 for t in trades),
 'exits':dict(Counter(t['exit_reason'] for t in trades)),
 'highest_stage_distribution':dict(tiers_seen),
 'cohort':dict(Counter(t['research_label'] for t in trades)),
 'additional_cost_0p05_roi_pp_total':round(sum(t['net_roi_pp']-.05 for t in trades),5),
 'additional_cost_0p1_roi_pp_total':round(sum(t['net_roi_pp']-.10 for t in trades),5),
 'trades':trades}
comparison={}
for name,p in profiles.items():
 one=build(p)
 sensitivity=build(p,True)
 scenarios=[]
 for count in (4,8):
  margin=2000/count
  notional=margin*3
  scenarios.append({'bot_count':count,'balance_per_bot_usdt':margin,
    'allocation_pct_of_total_balance':100/count,
    'position_notional_per_bot_if_full_allocation_usdt':notional,
    'total_nominal_if_all_bots_use_full_balance_usdt':6000,
    'roundtrip_fee_usdt_per_full_position':round(notional*.0008,5),
    'first_arm_roi_pp':p['tiers'][0][0] if p['tiers'] else None,
    'first_floor_gross_roi_pp':round(p['tiers'][0][0]-p['tiers'][0][1],5) if p['tiers'] else None,
    'first_floor_net_after_fee_roi_pp':round(p['tiers'][0][0]-p['tiers'][0][1]-fee,5) if p['tiers'] else None,
    'first_floor_net_usdt_if_perfect_fill':round(margin*(p['tiers'][0][0]-p['tiers'][0][1]-fee)/100,5) if p['tiers'] else None,
    'hard_tp_net_usdt_if_filled':round(margin*(p['tp']-fee)/100,5) if p['tp'] else None,
    'stop_net_usdt_if_filled':round(-margin*.0921,5),
    'stop_pct_of_total_account':round(margin*.0921/2000*100,5),
    'synthetic_roi_sum_as_usdt_constant_margin_one_coin':round(margin*one['total_net_roi_pp']/100,5),
    'broker_occupancy_sensitivity_usdt':round(margin*sensitivity['total_net_roi_pp']/100,5)})
 comparison[name]={'parameters':p,'one_coin_single_position_book':one,
   'broker_occupancy_veto_sensitivity':sensitivity,
   'four_eight_allocation_scenarios':scenarios}
assert comparison['hard_tp_0p80_no_trail_control']['one_coin_single_position_book']['total_net_roi_pp']==.29285
assert comparison['hard_tp_0p80_no_trail_control']['one_coin_single_position_book']['trades_count']==19
out={'schema':'long1_four_eight_bot_2000_six_stage_shadow_replay_v1',
 'research_only':True,'model_events':103,'research_ready':32,
 'historical_window':'2026-11-11_to_2026-11-15_TRT',
 'symbol':'NEARUSDT','account_balance_usdt':2000,'leverage':3,
 'allocation_is_fixed_capital_envelope_not_live_full_margin_mandate':True,
 'full_2000_allocated_leaves_no_unreserved_cash_buffer':True,
 'aggregate_8_bots_replay_not_valid_from_one_long1_data_series':True,
 'same_coin_global_one_position_risk_master_invariant':True,
 'roundtrip_fee_3x_roi_pp_assumption':.24,
 'stop_price_percent':2.99,
 'hard_tp_0p80_caps_6_step_upside':True,
 'dynamic_tp_raises_only_after_prior_full_1m_close':True,
 'dynamic_tp_cancel_replace_instantaneous_optimistic':True,
 'dynamic_tp_targets_from_initial_0p80':dynamic_tp_targets,
 'soft_tp_0p80_is_not_guaranteed_exit_at_0p80':True,
 'intrabar_entry_trailing_true_tick_not_available':True,
 'trailing_uses_completed_1m_and_next_open':True,
 'live_new_model_intent_not_reproduced':True,
 'native_fills_slippage_funding_not_included':True,
 'historical_user_label_not_used_as_decision':True,
 'real_orders_sent':0,'redis_writes':0,
 'six_stage_user_first_arm':tiers_user,
 'six_stage_feeaware_comparator':tiers_feeaware,
 'profiles':comparison}
p=OUT/'LONG1_2000USDT_4BOT_8BOT_6STAGE_SIM_20261120.json'
p.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({'status':'PASS','profiles':{name:{
 'opens':v['one_coin_single_position_book']['trades_count'],
 'total_roi_pp':v['one_coin_single_position_book']['total_net_roi_pp'],
 'exits':v['one_coin_single_position_book']['exits'],
 'stages':v['one_coin_single_position_book']['highest_stage_distribution'],
 'broker_veto_roi_pp':v['broker_occupancy_veto_sensitivity']['total_net_roi_pp'],
 '4bot_usdt':v['four_eight_allocation_scenarios'][0]['synthetic_roi_sum_as_usdt_constant_margin_one_coin'],
 '8bot_usdt':v['four_eight_allocation_scenarios'][1]['synthetic_roi_sum_as_usdt_constant_margin_one_coin']
 } for name,v in comparison.items()}},sort_keys=True))
