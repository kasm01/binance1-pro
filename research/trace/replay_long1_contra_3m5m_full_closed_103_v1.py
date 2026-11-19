"""As-of Binance kline research for LONG1 contra+3m+5m recovery.

Not production snapshot semantics: historical combined/context metrics,
whale/orderbook and partial Entry Confirmation aren't in the archive.
Uses pure existing Context.contra/recovery and five_minute_recovered with
reconstructed 1m observations. At least next full 3m and 5m close after
a contra origin plus a NEW intent are requirements; this research has
NO new intent and thus never grants full entry authority.
"""
from datetime import datetime,timezone
from pathlib import Path
from bisect import bisect_right
from collections import Counter
import gzip,csv,json
from core.long_contra_guard import Context,five_minute_recovered
R=Path(__file__).resolve().parents[2]
A=json.loads((R/'research/results/LONG1_BINANCE_ARCHIVE_ASOF_FLOW_103_MODEL_EVENTS_20261119.json').read_text())
B=json.loads((R/'research/results/LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())
with gzip.open(R/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz','rt') as f:
 bars=[{'t':int(x['open_time_ms']),'o':float(x['open']),'h':float(x['high']),
        'l':float(x['low']),'c':float(x['close']),'q':float(x['quote_volume']),
        'buy':float(x['taker_buy_quote_volume'])} for x in csv.DictReader(f)]
closes=[b['t']+60000 for b in bars]
assert len(A['events'])==103 and len(bars)==8640
def flows(i,n):
 sample=bars[i-n+1:i+1]
 q=sum(x['q'] for x in sample)
 return (2*sum(x['buy'] for x in sample)/q-1) if q>0 else 0
def m3close_indices(i):
 # latest full 3m closes, UTC aligned
 k=i
 while (bars[k]['t']+60000)%(180000)!=0:k-=1
 return [k-6,k-3,k]
def context(i):
 k0,k1,k2=m3close_indices(i)
 # three successive completed 3m returns
 r=[bars[k2-6]['c']/bars[k2-9]['c']-1,
    bars[k2-3]['c']/bars[k2-6]['c']-1,
    bars[k2]['c']/bars[k2-3]['c']-1]
 # proxy mean differs from live research_m3_ret1_mean3; explicit approximation
 return Context(True,'proxy_binance_kline',
  candle_ms=bars[k2]['t']+60000-1,
  observed_ms=bars[i]['t']+60000,
  ret3=r[-1],mean3=sum(r)/3,upfrac3=sum(x>0 for x in r)/3,
  flow15=flows(i,15),flow60=flows(i,60))
def full5(i,origin_ms,now_ms):
 k=i
 while (bars[k]['t']+60000)%300000!=0:k-=1
 def item(idx):
  start=bars[idx]['t']-4*60000
  # exact Binance API 5m close convention = start +5m -1
  return [start,None,None,None,bars[idx]['c'],None,start+300000-1]
 return five_minute_recovered([item(k-5),item(k)],
  origin_ms=origin_ms,now_ms=now_ms)
results=[]
for e in sorted(A['events'],key=lambda q:q['model_event_tr']):
 t=int(datetime.fromisoformat(e['model_event_tr']).timestamp()*1000)
 i=bisect_right(closes,t)-1
 origin=context(i)
 assert origin.valid
 found=None;reasons=Counter()
 # 30 minute as-of observation horizon; the flow guard must be recovered
 for j in range(i+1,i+31):
  ctx=context(j);now=closes[j]
  if origin.contra:
   if ctx.candle_ms<=origin.candle_ms:
    reasons['await_new_closed_3m']+=1;continue
   if not ctx.recovery:
    reasons['await_positive_ret3_and_nonnegative_flow15']+=1;continue
   if not full5(j,origin.candle_ms,now):
    reasons['await_new_full_5m_positive_close']+=1;continue
   found={'elapsed_minutes':j-i,'recovery_closed_at_ms':ctx.candle_ms,
          'last_full_1m_close_ms':now,
          'proxy_3m_recovery':ctx.recovery,'full_5m_recovered':True}
   break
  else:
   # NO prior contra pending; this stage alone has no contra veto.
   found={'elapsed_minutes':0,'recovery_closed_at_ms':origin.candle_ms,
          'last_full_1m_close_ms':closes[i],
          'proxy_3m_recovery':origin.recovery,
          'full_5m_recovered':False}
   break
 label=e['user_reference']
 results.append({'model_event_tr':e['model_event_tr'],'label':label,
  'origin_proxy_contra':origin.contra,'origin_flow15':round(origin.flow15,5),
  'origin_flow60':round(origin.flow60,5),
  'origin_proxy_m3_mean':round(origin.mean3,6),
  'origin_proxy_m3_upfrac':origin.upfrac3,
  'research_full_closed_recovery_found':found is not None,
  'research_recovery':found,
  'wait_reasons':dict(reasons),'new_independent_intent_id_verified':False,
  'real_order_open_authorized':False})
assert len(results)==103
cohorts={}
for label in ['LONG_TARGET','LONG_AVOID','UNLABELLED','CONFLICT_NO_TRADE']:
 rows=[x for x in results if x['label']==label]
 cohorts[label]={'model_events':len(rows),
  'origin_contra_proxy':sum(x['origin_proxy_contra'] for x in rows),
  'origin_noncontra_proxy':sum(not x['origin_proxy_contra'] for x in rows),
  'contra_recovered_within30m':sum(x['origin_proxy_contra'] and x['research_full_closed_recovery_found'] for x in rows),
  'contra_not_recovered_in30m':sum(x['origin_proxy_contra'] and not x['research_full_closed_recovery_found'] for x in rows)}
assert cohorts['LONG_TARGET']['model_events']==11
output={'schema':'long1_research_103_closed3m5m_contra_revalidation_v1',
 'reconstructed_binance_taker_flow_not_equal_original_live_source':True,
 'm3_structure_return_proxy_not_equal_original_live_structure':True,
 'complete_candle_only_no_lookahead':True,
 'revalidation_lookahead_window_is_outcome_not_entry_at_origin':True,
 '30m_max_revalidation':True,
 'new_intent_identity_not_available':True,
 'partial_1m_sniper_entry_confirmation_not_reproduced':True,
 'real_orders_authorized':0,'production_redis_writes':0,
 'cohorts':cohorts,'events':results}
target=R/'research/results/LONG1_STAGE12_103_BINANCE_CLOSED3M5M_CONTRA_PROXY_20261119.json'
target.write_text(json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','cohorts':cohorts,'real_orders':0},sort_keys=True))
