"""Counterfactual micro-TP and early tiered lock research on Stage13 candidates.

Candidate entry timestamps fixed from Stage13, NO future-based selection.
STOP_FIRST pessimistic OHLC, next-open trailing only after closed 1m bars.
Fixed TP limit is optimistic touch fill; spreads/gaps/queue/slippage ignored.
NOT a native exchange order simulation, not a historical exact intent replay.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
import csv,gzip,json
R=Path(__file__).resolve().parents[2]
base=R/'research/results'
s=json.loads((base/'LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 bars=[dict(t=int(r['open_time_ms']),o=float(r['open']),h=float(r['high']),l=float(r['low']),c=float(r['close'])) for r in csv.DictReader(f)]
assert len(bars)==8640
candidates=[z for z in s['events'] if z['decision']=='RESEARCH_READY_NO_REAL_INTENT']
assert len(candidates)==32
profiles={
 'fixed_0p40':dict(tp=.40,tiers=()),
 'fixed_0p60':dict(tp=.60,tiers=()),
 'fixed_0p80':dict(tp=.80,tiers=()),
 'fixed_1p00':dict(tp=1.00,tiers=()),
 'fixed_1p25':dict(tp=1.25,tiers=()),
 'micro_0p40_arm_0p10_gb_tp_0p80':dict(tp=.80,tiers=((.40,.10),(.60,.12))),
 'micro_0p50_arm_0p12_gb_tp_1p00':dict(tp=1.00,tiers=((.50,.12),(.75,.15))),
 'six_tier_legacy_tp_1p25':dict(tp=1.25,tiers=((.60,.10),(.95,.15),(1.20,.15),(1.65,.20),(2.00,.20),(2.50,.20)))}
fee=.24
def run_trade(i,p):
 entry=bars[i]['o'];stop=entry*(1-.0299);tp=entry*(1+p['tp']/300)
 peak=0.;floor=None;armed=None
 for j in range(i,min(i+60,len(bars)-1)):
  b=bars[j]
  if b['o']<=stop:return j,'STOP_GAP',round(300*(b['o']/entry-1)-fee,5)
  if b['o']>=tp:return j,'TP_GAP',round(300*(b['o']/entry-1)-fee,5)
  if b['l']<=stop:return j,'SL_FIRST',-9.21
  if b['h']>=tp:return j,'TP_FIRST',round(p['tp']-fee,5)
  # Only fully CLOSED candle can be used for trailing. Intrabar
  # high excursions never treated as known until bar is complete.
  roi=300*(b['c']/entry-1)
  peak=max(peak,roi)
  k=max((k for k,(arm,gb) in enumerate(p['tiers']) if peak>=arm),default=-1)
  if k>=0:
   gb=p['tiers'][k][1]
   floor=max(peak-gb,floor if floor is not None else float('-inf'))
   if armed is None:armed=j
   if j>armed and roi<=floor:
    return j+1,'TRAIL_NEXT_OPEN',round(300*(bars[j+1]['o']/entry-1)-fee,5)
 j=min(i+59,len(bars)-1)
 return j,'TIMEOUT',round(300*(bars[j]['c']/entry-1)-fee,5)
def book(p,skip_real=False):
 chosen=[];busy=-1
 for z in candidates:
  if z['entry_idx']<=busy or (skip_real and z['overlaps_real_broker_long']):continue
  j,reason,roi=run_trade(z['entry_idx'],p)
  chosen.append(dict(model_time_tr=z['model_time_tr'],entry_idx=z['entry_idx'],exit_idx=j,
   label=z['label'],exit_reason=reason,net_roi_pp=roi))
  busy=j
 return {'count':len(chosen),'outcome':dict(Counter(x['exit_reason'] for x in chosen)),
  'positive_net_roi_count':sum(x['net_roi_pp']>0 for x in chosen),
  'negative_net_roi_count':sum(x['net_roi_pp']<0 for x in chosen),
  'total_net_roi_pp':round(sum(x['net_roi_pp'] for x in chosen),5),
  'gross_roi_nominal_usdt_total_margin200':round(2*sum(x['net_roi_pp'] for x in chosen),4),
  'total_net_roi_pp_extra_cost_0p05_per_trade':round(sum(x['net_roi_pp']-.05 for x in chosen),5),
  'total_net_roi_pp_extra_cost_0p10_per_trade':round(sum(x['net_roi_pp']-.10 for x in chosen),5),
  'cohorts':dict(Counter(x['label'] for x in chosen)),
  'individual_trades':chosen}
res={}
for name,p in profiles.items():
 res[name]={'parameters':p,'synthetic_single_position':book(p),
            'existing_broker_occupancy_veto_sensitivity':book(p,True)}
assert res['fixed_1p25']['synthetic_single_position']['count']==18
assert abs(res['fixed_1p25']['synthetic_single_position']['total_net_roi_pp']-2.5265)<.0001
assert abs(res['six_tier_legacy_tp_1p25']['synthetic_single_position']['total_net_roi_pp']-.737)<.0001
result={'schema':'long1_micro_tp_fixed_candidate_asof_103_v1','development_time':'2026-11-11_to_2026-11-15',
 'entry_candidates':32,'entry_exit_date_same_data_not_independent_holdout':True,
 'stage13_model_intent_not_verified':True,'price_stop_pct':2.99,'leverage':3,
 'fee_roundtrip_roi_pp_assumed':.24,'single_position_only':True,
 'fixed_tp_touch_fill_optimistic':True,'stop_first_if_both_seen':True,
 'trailing_only_confirmed_1m_close_next_open':True,
 'not_live_native_stop':True,'spreads_slippage_funding_ignored':True,
 'historical_labels_not_entry_features':True,
 'live_orders':0,'production_redis_writes':0,
 'profiles':res}
path=base/'LONG1_MICRO_TP_103_ASOF_PROFILE_COMPARISON_20261120.json'
path.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','profiles':{k:{
 'n':v['synthetic_single_position']['count'],'roi':v['synthetic_single_position']['total_net_roi_pp'],
 'n_real_veto':v['existing_broker_occupancy_veto_sensitivity']['count'],
 'roi_real_veto':v['existing_broker_occupancy_veto_sensitivity']['total_net_roi_pp'],
 'net_after_extra_0p1':v['synthetic_single_position']['total_net_roi_pp_extra_cost_0p10_per_trade'],
 'exits':v['synthetic_single_position']['outcome']} for k,v in res.items()}},sort_keys=True))
