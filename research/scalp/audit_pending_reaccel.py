#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_PENDING_REACCEL_AUDIT.csv'
FEE=0.0008

ds=pd.read_csv(CAND)
d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
entry_idx=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')

# Recreate score deciles globally for diagnostic subsets.
ds['decile']=pd.qcut(ds.gate_quality.rank(method='first'),10,labels=False)+1

CFG=dict(early_window=5,early_mfe=.0010,early_mae=.0025,arm=.0020,giveback=.0008,hard_stop=.0050,max_hold=10)

def down_exit(op,lo,thr):
    if op<=thr:return op
    if lo<=thr:return thr
    return None

def simulate(idx):
    entry=float(o[idx]); max_seen=-np.inf; min_seen=np.inf; armed=False; prior=None
    for k in range(CFG['max_hold']):
        j=idx+k; op=o[j]/entry-1; hi=h[j]/entry-1; lo=l[j]/entry-1; cl=c[j]/entry-1
        if prior is not None:
            x=down_exit(op,lo,prior)
            if x is not None:return x-FEE,k+1
        x=down_exit(op,lo,-CFG['hard_stop'])
        if x is not None:return x-FEE,k+1
        max_seen=max(max_seen,hi); min_seen=min(min_seen,lo)
        if k+1==CFG['early_window'] and max_seen<CFG['early_mfe'] and min_seen<=-CFG['early_mae']:
            return cl-FEE,k+1
        if max_seen>=CFG['arm']:armed=True
        if armed:prior=max_seen-CFG['giveback']
    return c[idx+CFG['max_hold']-1]/entry-1-FEE,CFG['max_hold']

def candle_loc(j):
    rng=h[j]-l[j]
    return 0.5 if rng<=0 else (c[j]-l[j])/rng

def choose_entry(base_idx,variant):
    # All decisions use only completed candles before the chosen next-open entry.
    if variant=='IMMEDIATE': return base_idx
    pre3=c[base_idx-1]/o[base_idx-3]-1 if base_idx>=3 else np.nan
    pre1=c[base_idx-1]/o[base_idx-1]-1 if base_idx>=1 else np.nan
    controlled=(np.isfinite(pre3) and -0.0030<=pre3<=0.0005 and pre1>-0.0020)
    if not controlled:return None
    wait=2 if '2M' in variant else 3
    for step in range(wait):
        j=base_idx+step
        r=c[j]/o[j]-1; loc=candle_loc(j)
        prev_r=(c[j-1]/o[j-1]-1) if j>=1 else 0.0
        low_recovery=(c[j]/l[j]-1) if l[j]>0 else 0.0
        if variant.endswith('BASIC'):
            ok=(r>0 and loc>=0.55)
        elif variant.endswith('ACCEL'):
            ok=(r>0 and r>prev_r and loc>=0.55)
        else: # RECOVERY
            ok=(r>-0.0005 and loc>=0.60 and low_recovery>=0.0008)
        if ok:return j+1
    return None

variants=['IMMEDIATE','PEND_2M_BASIC','PEND_3M_BASIC','PEND_2M_ACCEL','PEND_3M_ACCEL','PEND_2M_RECOVERY','PEND_3M_RECOVERY']
sets={'D7_10':ds.decile>=7,'D8':ds.decile==8,'D9_10':ds.decile>=9}
rows=[]
for sname,smask in sets.items():
    ids=np.where(smask.to_numpy())[0]
    for v in variants:
        rets=[]; durs=[]; folds=[]; triggered=0
        for ii in ids:
            b=int(entry_idx[ii]); e=choose_entry(b,v)
            if e is None or e+CFG['max_hold']>=len(o):continue
            triggered+=1; r,d=simulate(e); rets.append(r); durs.append(d); folds.append(int(ds.iloc[ii].gate_fold))
        arr=np.asarray(rets,float)
        if len(arr)==0:continue
        pos=arr[arr>0].sum(); neg=-arr[arr<0].sum(); pf=pos/neg if neg>0 else np.inf
        fold_means=[]
        for f in sorted(set(folds)):
            fa=arr[np.asarray(folds)==f]; fold_means.append(fa.mean()*1e4)
        rows.append(dict(set=sname,variant=v,n=len(arr),trigger_pct=100*len(arr)/len(ids),net_bps=arr.mean()*1e4,pf=pf,win_pct=100*(arr>0).mean(),mean_dur=np.mean(durs),positive_folds=sum(x>0 for x in fold_means),worst_fold_bps=min(fold_means)))
res=pd.DataFrame(rows)
print('===== PENDING / REACCEL AUDIT =====')
print(res.sort_values(['set','net_bps'],ascending=[True,False]).round(4).to_string(index=False))
res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
