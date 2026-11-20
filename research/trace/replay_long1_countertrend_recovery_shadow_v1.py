"""LONG1 default-off research: countertrend recovery detector and fixed 16-Nov holdout.

Decision input is ONLY fully closed 1m candle + prior completed 1m
history, with 5m context a rolling five-closed-1m proxy (NOT exact
production 5m Market Context). Retrospective user labels do NOT
create entry signals; one global chronological 5-minute occupancy
cooldown and explicit both-label CONFLICT veto on 11-15 Nov.
Genuine fresh MODEL/Intent, Sniper partial 1m, Whale, Risk Master
remain UNVERIFIED, so all entries are diagnostic and no orders
may be authorized. Proceeds with fixed parameters on Nov16 holdout.
"""
from __future__ import annotations
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
from zipfile import ZipFile
from io import TextIOWrapper
import gzip,csv,json
R=Path(__file__).resolve().parents[2]
REF=json.loads((R/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json').read_text())
S=json.loads((R/'research/results/LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 train=[dict(t=int(x['open_time_ms']),o=float(x['open']),h=float(x['high']),
         l=float(x['low']),c=float(x['close']),q=float(x['quote_volume']),
         buy=float(x['taker_buy_quote_volume'])) for x in csv.DictReader(f)]
assert len(train)==8640
with ZipFile(R/'research/local_market_data/near_usdm_20261110_16_holdout/NEARUSDT-1m-2026-11-16.zip') as z:
 with z.open(z.namelist()[0]) as f:
  test=[dict(t=int(x['open_time']),o=float(x['open']),h=float(x['high']),
          l=float(x['low']),c=float(x['close']),q=float(x['quote_volume']),
          buy=float(x['taker_buy_quote_volume'])) for x in csv.DictReader(TextIOWrapper(f))]
assert len(test)==1440
assert test[0]['t']==train[-1]['t']+60000
bars=train+test
assert all(bars[i]['t']-bars[i-1]['t']==60000 for i in range(1,len(bars)))
ranges=[(int(datetime.fromisoformat(x['start_tr']).timestamp()*1000),
         int(datetime.fromisoformat(x['end_tr']).timestamp()*1000),x['user_label'])
         for x in REF['user_intervals']]
model_minutes={int(datetime.fromisoformat(e['model_time_tr']).timestamp()*1000)//60000*60000
               for e in S['events']}
def labels(t):
 return sorted({lab for lo,hi,lab in ranges if lo<=t<hi})
def flow(rows):
 q=sum(x['q'] for x in rows)
 return 2*sum(x['buy'] for x in rows)/q-1 if q else 0.
def features(i):
 bar=bars[i];prev=bars[i-3]
 span=bar['h']-bar['l']
 return dict(green_arm=bar['c']>bar['o'] and 300*(bar['c']/bar['o']-1)>=.22,
  body=max(0.,bar['c']-bar['o'])/span if span else 0.,
  retrace=(bar['h']-bar['c'])/span if span else 1.,
  flow1=flow([bar]),flow3=flow(bars[i-2:i+1]),
  flow3_delta=flow(bars[i-2:i+1])-flow(bars[i-5:i-2]),
  r3=100*(bar['c']/bars[i-3]['c']-1),
  r3_delta=100*((bar['c']/bars[i-3]['c']-1)-
             (bars[i-3]['c']/bars[i-6]['c']-1)),
  r5=100*(bar['c']/bars[i-5]['c']-1))
def entry_gates(f):
 common=(f['green_arm'] and f['body']>=.22 and f['retrace']<=.35
  and f['flow1']>=.03 and f['flow3']>0 and f['r3']>0
  and f['flow3_delta']>=.08 and f['r3_delta']>=.10)
 return {'strict_positive_5m_proxy':common and f['r5']>0,
  # Strict 1m, improving positive 3m, yet 5m rolling close still weak.
  # This is an extra WATCH candidate, not override of live contra guard.
  'contra_recovery_watch_negative_5m':common and -.35<=f['r5']<0,
  'common_strict_closed_1m':common}
def outcome(i):
 entry=bars[i+1]['o'];rs=bars[i+1:i+6]
 end=300*(rs[-1]['c']/entry-1)
 hi=300*(max(x['h'] for x in rs)/entry-1)
 lo=300*(min(x['l'] for x in rs)/entry-1)
 return {'entry_next_1m_open':entry,'end_5m_net_roi_pp':round(end-.24,6),
  'mfe_5m_roi_pp':round(hi,6),'mae_5m_roi_pp':round(lo,6),
  'arm_022_gross_touch':hi>=.22,
  'arm_035_gross_touch':hi>=.35,
  'end_positive_net':end>.24}
def analyze(start_idx,end_idx,tag):
 pool=[]
 for i in range(start_idx,end_idx):
  if i<6 or i+6>len(bars):continue
  # No outcomes outside analyzed period
  if i+6>end_idx:continue
  f=features(i);g=entry_gates(f)
  if not g['strict_positive_5m_proxy'] and not g['contra_recovery_watch_negative_5m']:continue
  name='strict' if g['strict_positive_5m_proxy'] else 'contra_watch'
  la=labels(bars[i]['t']) if tag=='development' else []
  next_la=labels(bars[i]['t']+60000) if tag=='development' else []
  # Only explicit user conflict is a veto; WANTED/AVOID not a trade gate.
  both=('LONG_WANTED' in la and 'LONG_AVOID' in la) or ('LONG_WANTED' in next_la and 'LONG_AVOID' in next_la)
  pool.append({'decision_close_ms':bars[i]['t']+60000,'group':name,
    'reference_labels':la,'conflict_veto':both,
    'observed_model_same_minute':bars[i]['t'] in model_minutes,
    'features':{k:round(v,6) if isinstance(v,float) else v for k,v in f.items()},
    'outcome':outcome(i),'idx':i})
 def book(watch_enabled):
  chosen=[];busy=-1
  for z in pool:
   if z['group']=='contra_watch' and not watch_enabled:continue
   if z['conflict_veto']:continue
   if z['idx']<=busy:continue
   chosen.append(z);busy=z['idx']+5
  return {'entries':len(chosen),
   'strict_count':sum(z['group']=='strict' for z in chosen),
   'watch_count':sum(z['group']=='contra_watch' for z in chosen),
   'avoid_label_count':sum(z['reference_labels']==['LONG_AVOID'] for z in chosen),
   'wanted_label_count':sum(z['reference_labels']==['LONG_WANTED'] for z in chosen),
   'no_reference_label_count':sum(not z['reference_labels'] for z in chosen),
   'sum_net_roi_pp_at_5m_close':round(sum(z['outcome']['end_5m_net_roi_pp'] for z in chosen),5),
   'net_positive_5m_close_count':sum(z['outcome']['end_positive_net'] for z in chosen),
   'mfe_arm_022_touch_count':sum(z['outcome']['arm_022_gross_touch'] for z in chosen),
   'mfe_arm_035_touch_count':sum(z['outcome']['arm_035_gross_touch'] for z in chosen),
   'sum_net_roi_pp_extra_0p1_pp_each':round(sum(z['outcome']['end_5m_net_roi_pp']-.1 for z in chosen),5),
   'fixed_500_margin_usdt_pnl_only_one_engine':round(5*sum(z['outcome']['end_5m_net_roi_pp'] for z in chosen),5),
   'trades':chosen}
 strict=book(False);both=book(True)
 return {'period':tag,'strict_candidate_count':sum(z['group']=='strict' for z in pool),
  'contra_watch_candidate_count':sum(z['group']=='contra_watch' for z in pool),
  'conflict_veto_candidates':sum(z['conflict_veto'] for z in pool),
  'strict_only_5m_one_position':strict,'strict_plus_contra_watch_5m_one_position':both,
  'all_candidates':pool}
dev=analyze(1440,8640,'development')
hold=analyze(8640,10080,'nov16_holdout')
report={'schema':'long1_countertrend_recovery_watch_asof_holdout_v1',
 'status':'SHADOW_ONLY_NO_GO',
 'strategy':'NEARUSDT LONG1',
 'background_research_target':'closed_1m_0p22_gross_roi_then_positive_3m_recovery',
 'strict_gates_used_unchanged':True,
 'research_contra_extra_5m_return_min':-.35,
 'research_contra_extra_5m_return_max_exclusive':0,
 'contra_extra_requires_positive_3m_return_and_flow':True,
 'closed_5x_1m_proxy_not_true_5m_market_context':True,
 'strict_and_contra_watch_one_global_position_for_only_one_coin':True,
 'labels_not_used_as_wanted_avoid_entry_whitelist':True,
 'historical_conflict_veto_observed':True,
 'future_1m_high_not_used_for_decisions':True,
 'nov16_parameters_frozen_without_holdout_tuning':True,
 'no_real_model_intent_for_new_candidates':True,
 'no_verified_partial_1m_sniper_whale':True,
 'five_minute_exit_at_fifth_close_is_a_diagnostic_not_live_tp':True,
 'fees_roi_pp':.24,
 'funding_slippage_spread_actual_stop_not_modeled':True,
 'four_bot_cap_500_eight_bot_cap_250_only_reprice_not_joint_bot_book':True,
 'real_orders':0,'prod_redis_writes':0,
 'development':dev,'holdout':hold}
p=R/'research/results/LONG1_COUNTERTREND_RECOVERY_WATCH_NOV16_HOLDOUT_20261120.json'
p.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','development':{k:v for k,v in dev.items() if k not in ('all_candidates',) and not isinstance(v,dict)}|{
 k:{q:t for q,t in v.items() if q!='trades'} for k,v in dev.items() if isinstance(v,dict)},
 'holdout':{k:v for k,v in hold.items() if k!='all_candidates' and not isinstance(v,dict)}|{
 k:{q:t for q,t in v.items() if q!='trades'} for k,v in hold.items() if isinstance(v,dict)},
 'orders':0},sort_keys=True))
