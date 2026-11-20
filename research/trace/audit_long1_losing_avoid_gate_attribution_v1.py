"""Research-only attribution for AVOID84 fixed TP35 losses.

Avoid imputing actual executor READY from synthetic closed-1m signals.
Native Entry Confirmation uses body abs(px-open)/range and retrace
(hi-px)/(hi-open) and mid-minute state, NOT the research proxy
retrace (high-close)/range. This audit computes a closed bar
illustration, not verified live decisions. Cohort-only ancestry.
"""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from bisect import bisect_left
import json,csv,gzip
R=Path(__file__).resolve().parents[2];OUT=R/'research/results';TR=ZoneInfo('Europe/Istanbul')
book=json.loads((OUT/'LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json').read_text())['development']['book_strict']['trades']
avoid=[z for z in book if z['cohort']=='LONG_AVOID']
price=json.loads((OUT/'LONG1_AVOID84_FIXED_TP022_AND_PREENTRY_GATES_20261120.json').read_text())
tp35=price['fixed_tp_profiles']['0.35']['trades']
detail=json.loads((OUT/'LONG1_84_AVOID_AGGTRADE_6STAGE_REVERSAL_ANALYSIS_20261120.json').read_text())['trades']
stage=json.loads((OUT/'LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())['events']
assert len(avoid)==len(tp35)==len(detail)==84
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 bars=[{k:float(z[k]) for k in ('open','high','low','close')}|{'t':int(z['open_time_ms'])} for z in csv.DictReader(f)]
assert len(bars)==8640
T=[z['t'] for z in bars]
models=defaultdict(list)
for ev in stage:
 ms=int(datetime.fromisoformat(ev['model_time_tr']).timestamp()*1000)
 models[ms//60000*60000].append(ev)
assert sum(map(len,models.values()))==103
# Env whitelist is read-only, no secrets.
keys=('LONG_ROLLING_MODEL_GATE_ENABLE','LONG_ROLLING_MODEL_GATE_MIN','LONG_ROLLING_MODEL_GATE_MAX',
 'LONG_ROLLING_MODEL_GATE_QUANTILE','ENTRY_CONFIRM_ENABLE','ENTRY_CONFIRM_SHADOW',
 'ENTRY_CONFIRM_MIN_BODY_RATIO','ENTRY_CONFIRM_MAX_RETRACE_RATIO',
 'ENTRY_CONFIRM_REJECT_RETRACE_RATIO','ENTRY_CONFIRM_MIN_QUALITY',
 'SNIPER_ENTRY_MIN_CANDLE_PROGRESS','SNIPER_ENTRY_MAX_CANDLE_PROGRESS',
 'LONG_CONTRA_GUARD_ENABLE')
env={}
for line in (R/'.env').read_text().splitlines():
 if '=' in line and not line.lstrip().startswith('#'):
  k,v=line.split('=',1)
  if k in keys:env[k]=v.strip()
assert env['ENTRY_CONFIRM_SHADOW']=='0' and env['LONG_CONTRA_GUARD_ENABLE']=='1'
base={'body_min':.22,'retrace_max':.35,'flow1_min':.03,'flow3_positive':0.,
 'flow3_improvement_min':.08,'r3_positive':0.,'r3_improvement_min_pp':.10,'r5_positive':0.}
# Real code formula evaluated at COMPLETED candle only (not partial).
def closed_native_shape(z):
 candle_range=z['high']-z['low']
 if not(candle_range>0 and z['open']>0 and z['low']>0 and z['close']>0):return None
 px=z['close'];op=z['open'];hi=max(px,z['high']);lo=min(px,z['low'])
 span=hi-op
 if span<=0:return {'direction':px>=op,'has_span':False}
 body=abs(px-op)/(hi-lo)
 retrace=min(1.,max(0.,hi-px)/span)
 location=max(0.,min(1.,(px-lo)/(hi-lo)))
 bquality=min(1.,body/max(float(env['ENTRY_CONFIRM_MIN_BODY_RATIO']),1e-9))
 quality=.30*float(px>=op)+.25*bquality+.25*(1-retrace)+.20*location
 can=(px>=op and retrace<float(env['ENTRY_CONFIRM_MAX_RETRACE_RATIO'])
  and body>=float(env['ENTRY_CONFIRM_MIN_BODY_RATIO'])
  and quality>=float(env['ENTRY_CONFIRM_MIN_QUALITY']))
 return {'direction':px>=op,'has_span':True,'body_ratio':round(body,6),
  'native_retrace_ratio':round(retrace,6),'native_entry_quality_proxy':round(quality,6),
  'would_closed_bar_pass_native_shape_only':bool(can)}
rows=[]
for n,(r,res,dt) in enumerate(zip(avoid,tp35,detail)):
 i=r['i']
 assert T[i]+60000==r['time_ms']
 assert dt['origin_close_tr']==dt['entry_next_open_tr']
 assert dt['index']==n+1 or dt['index']>0
 f=r['features']
 checks={
  'closed_green_arm022':f['green_arm'],
  'body_ge_0p22':f['body']>=.22,
  'retrace_le_0p35':f['retrace']<=.35,
  'flow1_ge_0p03':f['flow1']>=.03,
  'flow3_positive':f['flow3']>0,
  'flow3_delta_ge_0p08':f['flow3delta']>=.08,
  'r3_positive':f['r3']>0,
  'r3_delta_ge_0p10pp':f['r3delta']>=.10,
  'r5_positive':f['r5']>0}
 assert all(checks.values()),(i,checks)
 native=closed_native_shape(bars[i])
 observed=models.get(T[i],[])
 row={'entry_time_tr':dt['entry_next_open_tr'],
  'outcome_5m_fixed_tp035_net_roi_pp':res['net_roi_pp'],
  'outcome_5m_fixed_tp035':res['reason'],
  'original_fifth_close_net_roi_pp':r['end_5m_net_roi_pp'],
  'research_entry_source':'CLOSED_1M_GREEN_ARM022',
  'research_closed1m_passed_gates':checks,
  'research_features':f,
  'closed_bar_native_entry_shape_illustration':native,
  'same_minute_archived_model_events':len(observed),
  'same_minute_model_decisions':[z['decision'] for z in observed],
  'same_minute_scores':[z.get('model_score_pass') for z in observed],
  'actual_fresh_model_intent_ancestry_verified':False,
  'actual_live_sniper_verified':False,'actual_live_entry_confirmation_verified':False,
  'actual_live_market_context_guard_verified':False,
  'actual_risk_master_order_authority_verified':False,
  'future_mfe_5m_roi_pp':dt['five_minute_price_path']['peak_roi_pp'],
  'future_mae_5m_roi_pp':dt['five_minute_price_path']['trough_roi_pp']}
 rows.append(row)
loss=[z for z in rows if z['outcome_5m_fixed_tp035_net_roi_pp']<0]
win=[z for z in rows if z['outcome_5m_fixed_tp035_net_roi_pp']>0]
assert len(loss)==48 and len(win)==36
def agg(items):
 return {'count':len(items),
 'model_same_minute':sum(z['same_minute_archived_model_events']>0 for z in items),
 'native_closed_shape_proxy_pass':sum(z['closed_bar_native_entry_shape_illustration'] and z['closed_bar_native_entry_shape_illustration'].get('would_closed_bar_pass_native_shape_only',False) for z in items),
 'net_roi_pp_sum':round(sum(z['outcome_5m_fixed_tp035_net_roi_pp'] for z in items),6),
 'mfe_below_0p22':sum(z['future_mfe_5m_roi_pp']<.22 for z in items),
 'mfe_below_0p35':sum(z['future_mfe_5m_roi_pp']<.35 for z in items)}
report={'schema':'long1_avoid84_research_vs_live_entry_gate_attribution_v1',
 'date_basis':'2026-11-11_to_2026-11-15_TRT',
 'scope':'84_DIAGNOSTIC_SYNTHETIC_AVOID_SIGNALS_NOT_ACTUAL_ORDERS',
 'env_whitelisted_snapshot':env,
 'research_gate_requirements':base,
 'research_all_84_passed_all_research_gates':True,
 'native_entry_retrace_uses_directional_span_not_full_candle_range':True,
 'native_body_abs_price_vs_open_not_research_max_positive_body':True,
 'native_partial_minute_decisions_unavailable':True,
 'archived_model_same_minute_not_sufficient_for_true_intent_lineage':True,
 'rolling_gate_cannot_be_inferred_when_model_missing':True,
 'no_real_model_score_gate_attribution_for_84':True,
 'no_full_market_context_whale_sniper_reproduction':True,
 'no_actual_orders_for_84':True,
 'historical_wanted_avoid_labels_only_for_reporting':True,
 'fee_roi_pp_assumed':.24,
 'real_orders':0,'production_redis_writes':0,
 'summary_all':agg(rows),'summary_fixed_tp035_losses':agg(loss),
 'summary_fixed_tp035_wins':agg(win),
 'fixed_tp035_losing_details':loss,
 'all_rows':rows}
p=OUT/'LONG1_AVOID84_RESEARCH_VS_LIVE_GATE_ATTRIBUTION_20261120.json'
p.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','all':report['summary_all'],
 'losers':report['summary_fixed_tp035_losses'],'winners':report['summary_fixed_tp035_wins'],
 'trio':[{k:v for k,v in a.items() if k in ('entry_time_tr','outcome_5m_fixed_tp035_net_roi_pp','research_features','closed_bar_native_entry_shape_illustration','same_minute_archived_model_events')} for a in rows if any(q in a['entry_time_tr'] for q in ('2026-11-14T01:01','2026-11-14T18:28','2026-11-14T19:27'))],
 'orders':0},sort_keys=True))
