"""One-shot, read-only retrospective early WATCH 1/3/5m revalidation study.

No orders, signals, server-state mutations or account calls. Uses
closed public Binance 1m candles only, fixed algorithm thresholds.
Avoids lookahead by running revalidation on a prefix ending at the
specific post-candidate checkpoint. Episodes dedup by symbol/direction.
"""
from __future__ import annotations
import collections,json,statistics,requests
from scanner.early_motion_shadow_v1 import inspect_early
from scanner.early_revalidation_shadow_v1 import revalidate,CHECKPOINTS
from scanner.extreme_momentum_v1 import MS
from scanner.shared_market_snapshot_v1 import parse_closed_klines

def stats(records):
 if not records:return {'n':0}
 returns=[r['outcome']['terminal_pct'] for r in records]
 return {'n':len(records),
   'reversed':sum(v<0 for v in returns),
   'reversal_fraction':round(sum(v<0 for v in returns)/len(returns),4),
   'mean_terminal_pct':round(statistics.mean(returns),4),
   'median_terminal_pct':round(statistics.median(returns),4),
   'mean_mfe_pct':round(statistics.mean(r['outcome']['mfe_pct'] for r in records),4),
   'mean_mae_pct':round(statistics.mean(r['outcome']['mae_pct'] for r in records),4)}

def forward_at_fixed_horizon(rows,index,direction,horizon,ref):
 if index+horizon>=len(rows):return None
 future=rows[index+1:index+horizon+1]
 if any(b['t']!=rows[index]['t']+j*MS for j,b in enumerate(future,1)):
  return None
 sign=1 if direction=='LONG' else -1
 hi=max(b['h'] for b in future)
 lo=min(b['l'] for b in future)
 return {'terminal_pct':round(100*sign*(future[-1]['c']/ref-1),4),
   'mfe_pct':round(100*((hi/ref-1) if sign==1 else (1-lo/ref)),4),
   'mae_pct':round(100*((lo/ref-1) if sign==1 else (1-hi/ref)),4)}

def delayed_close_return(rows,index,direction,check,horizon):
 if index+horizon>=len(rows) or index+check>=len(rows):return None
 a=rows[index+check]['c'];b=rows[index+horizon]['c']
 return round(100*(1 if direction=='LONG' else -1)*(b/a-1),4)

def inspect_symbol(symbol,rows):
 all_rows=[]
 last_episode={}
 for i in range(180,len(rows)-31):
  snapshot=rows[i-180:i+1]
  early=inspect_early(symbol,snapshot,observed_at_ms=rows[i]['t']+MS)
  if early['state']!='EARLY_CANDIDATE_SHADOW':continue
  d=early['direction'];ts=rows[i]['t']+MS
  if ts-last_episode.get(d,0)<60*MS:continue
  last_episode[d]=ts
  ref=rows[i]['c']
  event={'symbol':symbol,'direction':d,'reference_close_ms':ts,'reference_price':ref}
  fwd={str(h):forward_at_fixed_horizon(rows,i,d,h,ref) for h in (15,30)}
  if any(x is None for x in fwd.values()):continue
  checks={}
  for k in CHECKPOINTS:
   # pass only prefix available as of checkpoint, not later 30m data.
   checks[str(k)]=revalidate(event,rows[:i+k+1],checkpoint=k)
  if any(c['state']=='REVALIDATION_UNVERIFIED' for c in checks.values()):
   continue
  all_rows.append({'symbol':symbol,'t':ts,'direction':d,
    'checks':checks,'forward':fwd,'delayed_return_15m':{
      str(k):delayed_close_return(rows,i,d,k,15) for k in CHECKPOINTS}})
 return all_rows

def evaluate(all_rows):
 result={'episode_count':len(all_rows)}
 for horizon in ('15','30'):
  result[f'horizon_{horizon}m_baseline']=stats(
    [{'outcome':r['forward'][horizon]} for r in all_rows])
 for point in CHECKPOINTS:
  key=str(point)
  for horizon in ('15','30'):
   grouped=collections.defaultdict(list)
   for row in all_rows:
    grouped[row['checks'][key]['state']].append({'outcome':row['forward'][horizon]})
   result[f'checkpoint_{point}m_forward_{horizon}m']={
    state:stats(v) for state,v in sorted(grouped.items())}
  for state in ('CONTINUE_OBSERVE','PENDING_RECHECK','INVALIDATE_RESEARCH'):
   cohort=[r['delayed_return_15m'][key] for r in all_rows if r['checks'][key]['state']==state]
   result[f'checkpoint_{point}m_delayed_close15_{state}']={
    'n':len(cohort),'mean_after_checkpoint_pct':round(statistics.mean(cohort),4) if cohort else None,
    'reversed_after_checkpoint':sum(v<0 for v in cohort)}
 return result

def main():
 s=requests.Session()
 source=json.load(open('run/signal_center/status.json'))
 symbols=source['selected_symbols']
 now=int(s.get('https://fapi.binance.com/fapi/v1/time',timeout=8).json()['serverTime'])
 all_events=[];errors=[]
 for symbol in symbols:
  try:
   r=s.get('https://fapi.binance.com/fapi/v1/klines',
      params={'symbol':symbol,'interval':'1m','limit':750},timeout=10)
   r.raise_for_status()
   rows=parse_closed_klines(r.json(),asof_ms=now)
   if len(rows)<300:raise ValueError('short history')
   all_events.extend(inspect_symbol(symbol,rows))
  except (requests.RequestException,ValueError,TypeError,KeyError) as ex:
   errors.append({'symbol':symbol,'error':type(ex).__name__})
 # Fixed two halves of the observation period only exploratory robustness,
 # and halves can still share synchronized moves, not validation.
 stamps=sorted(r['t'] for r in all_events)
 midpoint=stamps[len(stamps)//2] if stamps else 0
 first=[x for x in all_events if x['t']<midpoint]
 second=[x for x in all_events if x['t']>=midpoint]
 obj={'schema':'binance1_early_135_revalidation_comparison_v1',
   'source':'Binance public USD-M consecutive closed 1m klines + taker quote flow',
   'method':'fixed 60m dedup per symbol/direction; checkpoints 1/3/5m; outcomes from original at +15m/+30m, plus hypothetical close-to-close delayed 15m changes',
   'exchange_asof_ms':now,'symbols_requested':len(symbols),
   'public_requests':len(symbols)+1,'errors':errors,
   'all':evaluate(all_events),'first_half':evaluate(first),'second_half':evaluate(second),
   'caveats':['No true fills, no commissions, spread/slippage/funding, close-based hypothetical delay does not include realizable execution','Overlapping episodes across coins and short 12h sample, not independent or out-of-sample','No strategy tuning or Telegram rule changes','Existing thresholds are exploratory'],
   'ready':False,'orders':0,'telegram_sent':False}
 print(json.dumps(obj,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
