#!/usr/bin/env python3
"""Research only: counterfactual guard on 26 observed real OPEN intents, no execution writes."""
from __future__ import annotations
import importlib.util, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('life',ROOT/'research/shadow/long1_lifecycle_1m_bounds_v1.py')
life=importlib.util.module_from_spec(spec);spec.loader.exec_module(life)
raw=pd.read_csv(life.DATA).sort_values('open_time').reset_index(drop=True)
arr=life.build();events=pd.read_csv(ROOT/'research/results/LONG1_REAL133_INTENT_CONTEXT_AUDIT.csv').sort_values('signal_ts_ms');decisions=pd.read_csv(ROOT/'research/results/LONG1_REAL133_INTENT_DECISION_LOG_AUDIT.csv')
events=events.merge(decisions[['intent_id','first_reason','first_action']],left_on='signal_id',right_on='intent_id',how='left')
events=events[events.actually_open==True].copy().sort_values('signal_ts_ms')
# Use completed 3m and 5m bars only: each bucket label refers to the subsequent minute (known at close).
bars={}
for n in (3,5):
 d=raw.copy();d['bucket']=(d.open_time//(n*60000)).astype('int64')
 b=d.groupby('bucket',sort=True).agg(start=('open_time','first'),end=('close_time','last'),open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),count=('close','size'))
 b=b[b['count']==n].copy();b['known_ms']=(b.index.to_numpy()+1)*n*60000
 bars[n]=b
mt=raw.open_time.to_numpy();q=(raw.quote_asset_volume.to_numpy(dtype=float));tb=raw.taker_buy_quote_volume.to_numpy(dtype=float)
def completed_move(n,t):
 b=bars[n];i=int(np.searchsorted(b.known_ms.to_numpy(),t,side='right'))-1
 if i<1:return False
 return float(b.iloc[i]['close'])>float(b.iloc[i-1]['close'])
def flow15(t):
 i=int(np.searchsorted(mt,t,side='left'));start=max(0,i-15)
 if i-start!=15 or mt[i-1]+60000!=t:return None
 vol=q[start:i].sum()
 return float((2*tb[start:i].sum()-vol)/vol) if vol>0 else None
def revalidate(t0,rule):
 # open at first *next* minute with data based only on closes strictly before the entry minute
 ix=int(np.searchsorted(mt,t0,side='right'))
 for j in range(ix+3,min(len(mt),ix+31)):
  t=int(mt[j]);
  if t-t0>30*60000:break
  three=completed_move(3,t);five=completed_move(5,t)
  if rule=='3m_5m' and three and five:return j,t,float(arr['open'][j])
  if rule=='3m_5m_flow15' and three and five and flow15(t) is not None and flow15(t)>=0:return j,t,float(arr['open'][j])
 return None
life.LEV=5.;life.ARM=.01;life.GIVEBACK=0;life.SL=.0299;life.CAT=.035;life.ROI_HARD=-.135;life.STALL_SEC=10**9
allrows=[]
for path in ('OHLC','OLHC'):
 for rule in ('observed_base','contra_skip','pending_3m_5m','pending_3m_5m_flow15'):
  occupied=-1;rows=[];nondual_skipped=0
  for ev in events.itertuples(index=False):
   t0=int(ev.signal_ts_ms)
   if t0<occupied:continue
   dual=bool(ev.dual_contra)
   if rule=='contra_skip' and dual:continue
   if rule.startswith('pending_') and dual:
    re=revalidate(t0,rule.replace('pending_',''))
    if re is None:continue
    _,entry_t,entry_p=re
   else:
    idx=int(np.searchsorted(mt,t0,side='right'))
    if idx>=len(mt) or int(mt[idx])-t0>120000:continue
    entry_t=int(mt[idx]);entry_p=float(arr['open'][idx])
   if entry_t<occupied:continue
   sim=life.replay_market(arr,entry_t,entry_p,path)
   if not sim:continue
   if 'censored' in sim['exit_reason']:
    occupied=int(sim['exit_t'])+1;continue
   ret=(float(sim['exit_px'])/entry_p-1-.0008)*100
   rows.append(dict(path=path,policy=rule,signal_id=ev.signal_id,dual=dual,signal_ms=t0,entry_ms=entry_t,entry=entry_p,delay_min=round((entry_t-t0)/60000,2),exit_ms=sim['exit_t'],exit=sim['exit_px'],reason=sim['exit_reason'],net_notional_pct=ret))
   occupied=int(sim['exit_t'])+1
  if rows:allrows.extend(rows)
  w=[x['net_notional_pct'] for x in rows if x['net_notional_pct']>0];l=[x['net_notional_pct'] for x in rows if x['net_notional_pct']<0]
  print('SERIAL',path,rule,'N',len(rows),'W',len(w),'L',len(l),'PF',round(sum(w)/-sum(l),3) if l else None,'SUM_PP',round(sum(w)+sum(l),3),'DUAL_ACCEPTED',sum(x['dual'] for x in rows),'PENDING_DELAY_AVG',round(np.mean([x['delay_min'] for x in rows if x['dual']]),2) if any(x['dual'] for x in rows) else None)
# Independent candidate shadow guard tallies independent of occupancy/order
for rule in ['3m_5m','3m_5m_flow15']:
 dual_events=events[events.dual_contra==True]
 passed=[];failed=[]
 for ev in dual_events.itertuples(index=False):
  re=revalidate(int(ev.signal_ts_ms),rule)
  (passed if re else failed).append((ev.signal_id,round((re[1]-ev.signal_ts_ms)/60000,2) if re else None))
 print('CANDIDATE',rule,'dual_observed',len(dual_events),'revalidated',len(passed),'expired',len(failed),'median_delay_min',float(np.median([x[1] for x in passed])) if passed else None)
 df=pd.DataFrame([dict(signal_id=k,revalidated=True,delay_min=v) for k,v in passed]+[dict(signal_id=k,revalidated=False,delay_min=None) for k,_ in failed]);df.to_csv(ROOT/f'research/results/LONG1_GUARD_{rule}_OBSERVED26_20261111.csv',index=False)
pd.DataFrame(allrows).to_csv(ROOT/'research/results/LONG1_GUARD_SERIAL_OBSERVED26_20261111.csv',index=False)
print('SOURCE_INPUT_OBSERVED_OPEN',len(events),'DUAL',sum(events.dual_contra),'NON_DUAL',sum(~events.dual_contra))
