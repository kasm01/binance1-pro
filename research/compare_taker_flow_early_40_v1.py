"""Read-only one-shot Binance 40 coin taker-flow research; no trade/alerts."""
from __future__ import annotations
import json,statistics,requests
from scanner.shared_market_snapshot_v1 import parse_closed_klines
from scanner.early_motion_shadow_v1 import inspect_early
from scanner.taker_flow_quality_shadow_v1 import assess_flow
from scanner.extreme_momentum_v1 import MS
from research.compare_early_watch_12coins_v1 import score

def describe(events):
 if not events:return {'n':0}
 return {'n':len(events),
  'terminal15_mean_pct':round(statistics.mean(x['terminal'] for x in events),4),
  'mfe15_mean_pct':round(statistics.mean(x['mfe'] for x in events),4),
  'mae15_mean_pct':round(statistics.mean(x['mae'] for x in events),4),
  'reversal_count':sum(x['terminal']<0 for x in events)}

def evaluate(rows,symbol):
 seen={};results=[]
 for i in range(180,len(rows)-15):
  asof=rows[i]['t']+MS
  window=rows[i-180:i+1]
  early=inspect_early(symbol,window,observed_at_ms=asof)
  if early['state']!='EARLY_CANDIDATE_SHADOW':continue
  direction=early['direction']
  if asof-seen.get(direction,0)<60*MS:continue
  seen[direction]=asof
  f=assess_flow(window,direction,observed_at_ms=asof)
  value=score(rows,i,direction,horizon=15)
  if value is None:continue
  results.append((f['state'],value,asof))
 return results

def main():
 with requests.Session() as s:
  u=json.load(open('run/signal_center/status.json'))
  symbols=u['selected_symbols']
  server=int(s.get('https://fapi.binance.com/fapi/v1/time',timeout=8).json()['serverTime'])
  grouped={};details=[];failed=[];half={'first':{},'second':{}}
  for coin in symbols:
   try:
    resp=s.get('https://fapi.binance.com/fapi/v1/klines',
       params={'symbol':coin,'interval':'1m','limit':750},timeout=10)
    resp.raise_for_status()
    rows=parse_closed_klines(resp.json(),asof_ms=server)
    if len(rows)<300:raise ValueError('insufficient history')
    events=evaluate(rows,coin)
    pivot=rows[len(rows)//2]['t']
    for state,metric,ts in events:
     grouped.setdefault(state,[]).append(metric)
     key='first' if ts<pivot else 'second'
     half[key].setdefault(state,[]).append(metric)
    details.append({'symbol':coin,'candidate_count':len(events),
                    'flow_supportive':sum(state=='FLOW_SUPPORTIVE' for state,_,_ in events)})
   except (requests.RequestException,ValueError,TypeError,KeyError,ZeroDivisionError) as e:
    failed.append({'symbol':coin,'error_type':type(e).__name__})
  output={'schema':'manual_early_taker_flow_research.v1',
   'sources':'Binance public 1m closed kline index10 taker buy quote',
   'sample':'most recent approximately 12.5 hours, selected 40 symbols',
   'coins_success':len(details),'coins_failed':failed,'public_requests':1+len(symbols),
   'all_early':describe([v for a in grouped.values() for v in a]),
   'flow_groups':{k:describe(v) for k,v in grouped.items()},
   'time_halves':{h:{k:describe(v) for k,v in d.items()} for h,d in half.items()},
   'per_symbol':details,'no_ready':True,'telegram_sent':False,
   'real_trades':0,'no_proof_of_profitability':True}
  print(json.dumps(output,sort_keys=True,ensure_ascii=False))
if __name__=='__main__':main()
