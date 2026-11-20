"""Fixed non-oracle bull-context entry extension. No calendar labels in gates.

Goal: count whether adding bullish-context early entries can capture
retrospectively WANTED opportunities WITHOUT changing AVOID eligible
counts. This requirement must be measured, not assumed; if AVOID increases
mark proposal NO-GO. Only fully closed 1m inputs, next-open hypothetical
entry and fifth-close evaluation. No real MODEL/Intent or order authority.
"""
from pathlib import Path
from datetime import datetime
from zipfile import ZipFile
from io import TextIOWrapper
from collections import Counter
import csv,gzip,json
R=Path(__file__).resolve().parents[2];OUT=R/'research/results'
ref=json.loads((R/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json').read_text())['user_intervals']
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 bars=[dict(t=int(z['open_time_ms']),o=float(z['open']),h=float(z['high']),l=float(z['low']),c=float(z['close']),q=float(z['quote_volume']),buy=float(z['taker_buy_quote_volume'])) for z in csv.DictReader(f)]
assert len(bars)==8640
with ZipFile(R/'research/local_market_data/near_usdm_20261110_16_holdout/NEARUSDT-1m-2026-11-16.zip') as z:
 with z.open(z.namelist()[0]) as f:
  bars.extend(dict(t=int(a['open_time']),o=float(a['open']),h=float(a['high']),l=float(a['low']),c=float(a['close']),q=float(a['quote_volume']),buy=float(a['taker_buy_quote_volume'])) for a in csv.DictReader(TextIOWrapper(f)))
assert len(bars)==10080
ranges=[(int(datetime.fromisoformat(z['start_tr']).timestamp()*1000),int(datetime.fromisoformat(z['end_tr']).timestamp()*1000),z['user_label']) for z in ref]
def labels(t):
 return sorted({v for a,b,v in ranges if a<=t<b})
def flow(rows):
 q=sum(z['q'] for z in rows)
 return 2*sum(z['buy'] for z in rows)/q-1 if q else 0
def features(i):
 z=bars[i];span=z['h']-z['l']
 f3=flow(bars[i-2:i+1])
 return dict(green_arm=z['c']>z['o'] and 300*(z['c']/z['o']-1)>=.22,
 body=max(z['c']-z['o'],0)/span if span else 0,
 retrace=(z['h']-z['c'])/span if span else 1,
 flow1=flow([z]),flow3=f3,flow3delta=f3-flow(bars[i-5:i-2]),
 r3=100*(z['c']/bars[i-3]['c']-1),
 r3delta=100*((z['c']/bars[i-3]['c']-1)-(bars[i-3]['c']/bars[i-6]['c']-1)),
 r5=100*(z['c']/bars[i-5]['c']-1))
def gates(f):
 common=(f['green_arm'] and f['flow3']>0 and f['r3']>0)
 strict=common and f['body']>=.22 and f['retrace']<=.35 and f['flow1']>=.03 and f['flow3delta']>=.08 and f['r3delta']>=.10 and f['r5']>0
 # predeclared counterfactual: independent of retrospective calendar labels.
 strong_bull=common and f['r5']>=.20 and f['r3']>=.12
 extension=strong_bull and f['body']>=.18 and f['retrace']<=.45 and f['flow1']>=.01 and f['flow3delta']>=.05 and f['r3delta']>=.08
 return strict,extension and not strict
def analyze(start,end,period):
 candidates=[]
 for i in range(max(6,start),min(end-6,len(bars)-6)):
  f=features(i);strict,extra=gates(f)
  if not (strict or extra):continue
  lo=labels(bars[i]['t']) if period=='development' else []
  hi=labels(bars[i]['t']+59999) if period=='development' else []
  if lo!=hi:continue
  cohort='CONFLICT' if len(lo)>1 else (lo[0] if lo else 'UNLABELLED')
  entry=bars[i+1]['o'];block=bars[i+1:i+6]
  close=300*(block[-1]['c']/entry-1)-.24
  mfe=300*(max(x['h'] for x in block)/entry-1)
  mae=300*(min(x['l'] for x in block)/entry-1)
  candidates.append(dict(i=i,time_ms=bars[i]['t']+60000,cohort=cohort,source='STRICT' if strict else 'BULL_CONTEXT_EXTRA',
    features={k:round(v,6) if isinstance(v,float) else v for k,v in f.items()},
    end_5m_net_roi_pp=round(close,6),gross_mfe_5m_roi_pp=round(mfe,6),gross_mae_5m_roi_pp=round(mae,6),
    arm022_after_entry=mfe>=.22,arm035_after_entry=mfe>=.35))
 def counts(rows):
  c=Counter()
  for z in rows:
   c[z['cohort']]+=1
  return dict(c)
 def book(allow_extra):
  active=-1;chosen=[]
  for z in candidates:
   if z['cohort']=='CONFLICT' or (z['source']=='BULL_CONTEXT_EXTRA' and not allow_extra):continue
   if z['i']<=active:continue
   chosen.append(z);active=z['i']+5
  return {'entries':len(chosen),'cohorts':counts(chosen),
   'new_bull_context_entries':sum(z['source']=='BULL_CONTEXT_EXTRA' for z in chosen),
   'arm022_after_entry':sum(z['arm022_after_entry'] for z in chosen),
   'positive_5m_close':sum(z['end_5m_net_roi_pp']>0 for z in chosen),
   'sum_net_roi_pp_at_5m_close':round(sum(z['end_5m_net_roi_pp'] for z in chosen),5),
   'trades':chosen}
 strict=book(False);both=book(True)
 add=[z for z in candidates if z['source']=='BULL_CONTEXT_EXTRA']
 return {'period':period,'strict_pool':sum(z['source']=='STRICT' for z in candidates),
   'extra_pool':len(add),'pool_extra_cohorts':counts(add),
   'book_strict':strict,'book_strict_plus_bull_extra':both,
   'wanted_delta_book':both['cohorts'].get('LONG_WANTED',0)-strict['cohorts'].get('LONG_WANTED',0),
   'avoid_delta_book':both['cohorts'].get('LONG_AVOID',0)-strict['cohorts'].get('LONG_AVOID',0),
   'all_candidates':candidates}
dev=analyze(1440,8640,'development');hold=analyze(8640,10080,'nov16_frozen_holdout')
out={'schema':'long1_wanted_opportunity_asof_bull_context_extension_v1',
 'decision':'NO_GO_UNLESS_AVOID_UNCHANGED_AND_HOLDOUT_OK',
 'target_651_was_green_candle_count_not_trades':True,
 'market_filters_have_no_calendar_labels':True,
 'nov16_frozen_rules':True,'green_arm_trigger_1m_close_pp':.22,
 'strict':{'body':.22,'retrace':.35,'flow1':.03,'flow3delta':.08,'r3delta':.10,'r5_positive':True,'r3_positive':True,'flow3_positive':True},
 'strong_bull_context_extra':{'body':.18,'retrace':.45,'flow1':.01,'flow3delta':.05,'r3delta':.08,'r5_min_pp':.20,'r3_min_pp':.12,'flow3_positive':True},
 'retrospective_avoid_labels_not_available_to_live_strategy':True,
 'must_not_use_clock_whitelist_for_wanted':True,
 'no_model_production_novel_events':True,'live_native_3m5m_context_not_reconstructed':True,
 'full_sniper_entry_whale_unavailable':True,'stop_and_actual_profitlock_not_tested':True,
 '5m_close_exit_is_diagnostic_only':True,'fee_3x_roi_pp':.24,
 'real_orders':0,'prod_redis_writes':0,
 'development':dev,'nov16_holdout':hold}
p=OUT/'LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json'
p.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','development':{k:v for k,v in dev.items() if k!='all_candidates' and not isinstance(v,dict)}|{k:{a:b for a,b in v.items() if a!='trades'} for k,v in dev.items() if isinstance(v,dict)},'holdout':{k:v for k,v in hold.items() if k!='all_candidates' and not isinstance(v,dict)}|{k:{a:b for a,b in v.items() if a!='trades'} for k,v in hold.items() if isinstance(v,dict)},'orders':0},sort_keys=True))
