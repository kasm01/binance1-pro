"""One-shot read-only public research. No alerts/trades, no persistent data."""
from __future__ import annotations
import argparse,json,statistics,time,requests,collections
from scanner.early_motion_shadow_v1 import inspect_early
from scanner.extreme_momentum_v1 import inspect,MS
from scanner.shared_market_snapshot_v1 import parse_closed_klines

def score(rows,idx,direction,horizon=15):
 if idx+horizon>=len(rows):return None
 future=rows[idx+1:idx+horizon+1]
 if any(future[j]['t']!=rows[idx]['t']+(j+1)*MS for j in range(horizon)):
  return None
 ref=rows[idx]['c'];sign=1 if direction=='LONG' else -1
 high=max(b['h'] for b in future);low=min(b['l'] for b in future)
 return {'terminal':sign*100*(future[-1]['c']/ref-1),
  'mfe':100*((high/ref-1) if sign==1 else (1-low/ref)),
  'mae':100*((low/ref-1) if sign==1 else (1-high/ref))}

def sample(rows):
 early=[];strong=[];last_e={};last_s={}
 for i in range(180,len(rows)-15):
  asof=rows[i]['t']+MS
  window=rows[i-180:i+1]
  a=inspect_early('NEARUSDT',window,observed_at_ms=asof)
  b=inspect('NEARUSDT',window,observed_at_ms=asof)
  if a['state']=='EARLY_CANDIDATE_SHADOW':
   d=a['direction']
   if asof-last_e.get(d,0)>=60*MS:
    v=score(rows,i,d)
    if v is not None:early.append((i,d,v))
    last_e[d]=asof
  if b['status'] in ('STRONG_WATCH','EXTREME_WATCH'):
   d=b['direction']
   if asof-last_s.get(d,0)>=60*MS:
    v=score(rows,i,d)
    if v is not None:strong.append((i,d,v))
    last_s[d]=asof
 return early,strong

def describe(events):
 if not events:return {'n':0}
 results=[x[2] for x in events]
 return {'n':len(results),
  'mean_terminal15_pct':round(statistics.mean(r['terminal'] for r in results),4),
  'mean_mfe15_pct':round(statistics.mean(r['mfe'] for r in results),4),
  'mean_mae15_pct':round(statistics.mean(r['mae'] for r in results),4),
  'reversed15_count':sum(r['terminal']<0 for r in results)}

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--all-40',action='store_true',help='Include all currently selected 40 symbols')
 args=parser.parse_args()
 s=requests.Session()
 u=json.load(open('run/signal_center/status.json'))
 symbols=u['selected_symbols']
 # Equal slots from four groups, no post hoc selection based on returns.
 sampled=(symbols if args.all_40 else
          [symbols[i] for i in (0,1,2,10,11,12,20,21,22,30,31,32)
           if i<len(symbols)])
 current=int(s.get('https://fapi.binance.com/fapi/v1/time',timeout=8).json()['serverTime'])
 all_early=[];all_strong=[];details=[];matches=[]
 for symbol in sampled:
  try:
   r=s.get('https://fapi.binance.com/fapi/v1/klines',
      params={'symbol':symbol,'interval':'1m','limit':750},timeout=10)
   r.raise_for_status()
   raw=r.json()
   rows=parse_closed_klines(raw,asof_ms=current)
   if len(rows)<300:raise ValueError('short history')
   early,strong=sample(rows)
   for i,d,m in early:all_early.append((symbol,i,d,m))
   for i,d,m in strong:all_strong.append((symbol,i,d,m))
   for i,d,v in strong:
    previous=[j for j,ed,_ in early if ed==d and 0<=i-j<=30]
    if previous:matches.append(i-max(previous))
   details.append({'symbol':symbol,'bars':len(rows),
      'early':describe(early),'strong':describe(strong),
      'early_precedes_strong_30m':sum(bool([j for j,ed,_ in early if ed==d and 0<=i-j<=30])
                                       for i,d,_ in strong)})
  except Exception as e:
   details.append({'symbol':symbol,'error_type':type(e).__name__})
 def combined(events):
  return describe([(i,d,m) for symbol,i,d,m in events])
 print(json.dumps({'source':'Binance public USD-M closed 1m klines',
  'sample_policy':('all current 40 universe symbols' if args.all_40
                    else 'first three symbols of each ten-slot allocation'),
  'symbols_checked':len(sampled),'rest_requests':1+len(sampled),
  'actual_success_symbols':sum('error_type' not in x for x in details),
  'evaluation':'750 latest 1m bars per symbol; 60min same-direction episode dedup',
  'early':combined(all_early),'strong':combined(all_strong),
  'strong_matched_early_30m':len(matches),
  'early_median_lead_min':statistics.median(matches) if matches else None,
  'per_coin':details,'no_orders':True,'no_alerts_sent':True,
  'no_proof_of_profitability':True},ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
