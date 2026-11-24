"""40-coin first-preparation versus early/strong signals, historical observation.

One-shot read-only Binance public 1m data; no trade, Telegram, READY.
Trigger and preparation both constructed from prefix ending at their
own CLOSED-1m timestamp. 5-45m historical preparation window.
"""
from __future__ import annotations
import collections,json,statistics,requests
from scanner.scalp_preparation_shadow_v1 import inspect_preparation
from scanner.early_motion_shadow_v1 import inspect_early
from scanner.extreme_momentum_v1 import inspect,MS
from scanner.shared_market_snapshot_v1 import parse_closed_klines

HORIZONS=(1,3,5,10,15)

def forward(rows,i,d):
 ref=rows[i]['c'];sgn=1 if d=='LONG' else -1
 out={}
 for n in HORIZONS:
  future=rows[i+1:i+1+n]
  if len(future)!=n or any(x['t']!=rows[i]['t']+MS*(j+1) for j,x in enumerate(future)):
   return None
  high=max(x['h'] for x in future);low=min(x['l'] for x in future)
  out[str(n)]={'close':round(100*sgn*(future[-1]['c']/ref-1),4),
    'mfe':round(100*(high/ref-1 if sgn==1 else 1-low/ref),4),
    'mae':round(100*(low/ref-1 if sgn==1 else 1-high/ref),4)}
 return out

def one_coin(symbol,rows):
 # Build preparation inventory at each minute with no future observations.
 prep=[];early_last={};strong_last={};res=[]
 for i in range(180,len(rows)-16):
  now=rows[i]['t']+MS
  prefix=rows[:i+1]
  p=inspect_preparation(symbol,prefix,observed_at_ms=now)
  if p['state']=='PREPARATION_SHADOW':
   prep.append((now,p['direction'],p['mode']))
  e=inspect_early(symbol,prefix,observed_at_ms=now)
  s=inspect(symbol,prefix,observed_at_ms=now)
  decisions=[]
  if e['state']=='EARLY_CANDIDATE_SHADOW':
   decisions.append(('EARLY',e['direction'],early_last))
  if s.get('status') in ('STRONG_WATCH','EXTREME_WATCH'):
   decisions.append(('STRONG',s['direction'],strong_last))
  for typ,d,seen in decisions:
   if now-seen.get(d,0)<60*MS:continue
   seen[d]=now
   score=forward(rows,i,d)
   if score is None:continue
   prior=[(t,mode) for t,dd,mode in prep if dd==d and 5*MS<=now-t<=45*MS]
   # Closest preparation (most recent; gap may be 5 min).
   chosen=max(prior,key=lambda x:x[0]) if prior else None
   # earliest preparation event in that window is also recorded.
   first=min(prior,key=lambda x:x[0]) if prior else None
   res.append({'symbol':symbol,'t':now,'type':typ,'direction':d,
     'prepared':bool(chosen),'mode':chosen[1] if chosen else None,
     'latest_lead_min':(now-chosen[0])//MS if chosen else None,
     'earliest_lead_min':(now-first[0])//MS if first else None,
     'forward':score})
 return res

def stats(rows):
 if not rows:return {'n':0}
 return {'n':len(rows),'reversed_5m':sum(x['forward']['5']['close']<0 for x in rows),
   'reversed_15m':sum(x['forward']['15']['close']<0 for x in rows),
   'mean_close_5m':round(statistics.mean(x['forward']['5']['close'] for x in rows),4),
   'mean_close_15m':round(statistics.mean(x['forward']['15']['close'] for x in rows),4),
   'mean_mfe_5m':round(statistics.mean(x['forward']['5']['mfe'] for x in rows),4),
   'mean_mae_5m':round(statistics.mean(x['forward']['5']['mae'] for x in rows),4),
   'median_earliest_preparation_lead_min':statistics.median(
      x['earliest_lead_min'] for x in rows if x['prepared'])
     if any(x['prepared'] for x in rows) else None}

def main():
 s=requests.Session()
 symbols=json.load(open('run/signal_center/status.json'))['selected_symbols']
 now=int(s.get('https://fapi.binance.com/fapi/v1/time',timeout=8).json()['serverTime'])
 all_events=[];errors=[]
 for symbol in symbols:
  try:
   r=s.get('https://fapi.binance.com/fapi/v1/klines',
      params={'symbol':symbol,'interval':'1m','limit':750},timeout=10)
   r.raise_for_status()
   rows=parse_closed_klines(r.json(),asof_ms=now)
   if len(rows)<300:raise ValueError('too few bars')
   all_events.extend(one_coin(symbol,rows))
  except (ValueError,KeyError,TypeError,requests.RequestException) as exc:
   errors.append({'symbol':symbol,'error':type(exc).__name__,
                  'detail':str(exc)[:120]})
 groups=collections.defaultdict(list)
 for row in all_events:
  groups[(row['type'],row['prepared'],row['mode'])].append(row)
 print(json.dumps({'schema':'preparation_40coin_observational_v1',
   'requests':1+len(symbols),'symbols':len(symbols),
   'valid_symbols':len(symbols)-len(errors),'errors':errors,
   'events':len(all_events),'by_type':{typ:stats([x for x in all_events if x['type']==typ]) for typ in ('EARLY','STRONG')},
   'by_preparation':{str(k):stats(v) for k,v in sorted(groups.items(),key=lambda x:str(x[0]))},
   'examples':[{'symbol':x['symbol'],'type':x['type'],'direction':x['direction'],
     'mode':x['mode'],'earliest_lead_min':x['earliest_lead_min'],
     'close_5m':x['forward']['5']['close']} for x in all_events if x['prepared']][:15],
   'warnings':['short contemporaneous sample, not proof of forecasting 30-45m in advance',
    'preparation classifications may persist for many minutes; retrospective matching selects any matching precursor',
    'event windows and cross-coins overlap; no fees, fill latency, spread, market impact',
    'pure SHADOW no order/no Telegram changes'],
   'order_authorized':False,'telegram_sent':False},ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
