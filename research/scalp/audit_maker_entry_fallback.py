#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_MAKER_ENTRY_FALLBACK.csv'

MAKER=.0002
TAKER=.0005
MAKER_BNB=.00018
TAKER_BNB=.00045
CFG=dict(early_window=5,early_mfe=.0010,early_mae=.0025,arm=.0020,giveback=.0008,hard_stop=.0050,max_hold=10)

def down_exit(op,lo,thr):
    if op<=thr:return op
    if lo<=thr:return thr
    return None

def lifecycle(idx,entry,exit_fee,start_next=False):
    mx=-np.inf; mn=np.inf; armed=False; trail=None
    start=idx+1 if start_next else idx
    for step in range(CFG['max_hold']):
        j=start+step
        if j>=len(o):return np.nan,step
        op=o[j]/entry-1; hi=h[j]/entry-1; lo=l[j]/entry-1; cl=c[j]/entry-1
        if trail is not None:
            x=down_exit(op,lo,trail)
            if x is not None:return x-exit_fee,step+1
        x=down_exit(op,lo,-CFG['hard_stop'])
        if x is not None:return x-exit_fee,step+1
        mx=max(mx,hi); mn=min(mn,lo)
        if step+1==CFG['early_window'] and mx<CFG['early_mfe'] and mn<=-CFG['early_mae']:
            return cl-exit_fee,step+1
        if mx>=CFG['arm']:armed=True
        if armed:trail=mx-CFG['giveback']
    return c[start+CFG['max_hold']-1]/entry-1-exit_fee,CFG['max_hold']

ds=pd.read_csv(CAND)
d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
idx=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
ds['decile']=pd.qcut(ds.gate_quality.rank(method='first'),10,labels=False)+1
ds['entry_idx']=idx
rows=[]
for _,r in ds[ds.decile.eq(8)].iterrows():
    j=int(r.entry_idx)
    if j<4 or j+15>=len(o):continue
    r3=c[j-1]/c[j-4]-1
    r1=c[j-1]/c[j-2]-1
    deep=(r3<=-.0030) or (r1<=-.0020)
    recovery=c[j-1]/l[j-1]-1
    if deep and recovery<.0010:rows.append((int(r.gate_fold),j))
print('SUBSET_N=',len(rows))
scenarios=[('IMMEDIATE_TAKER',0,0,0),
('MKR0_WAIT1_FB',0,1,0),('MKR1_WAIT1_FB',1,1,0),('MKR2_WAIT1_FB',2,1,0),('MKR3_WAIT1_FB',3,1,0),
('MKR0_WAIT2_FB',0,2,0),('MKR1_WAIT2_FB',1,2,0),('MKR2_WAIT2_FB',2,2,0),('MKR3_WAIT2_FB',3,2,0),
('MKR1_WAIT1_Q1',1,1,1),('MKR2_WAIT1_Q1',2,1,1),('MKR1_WAIT2_Q1',1,2,1),('MKR2_WAIT2_Q1',2,2,1)]
out=[]
for bnb in [False,True]:
    mf=MAKER_BNB if bnb else MAKER
    tf=TAKER_BNB if bnb else TAKER
    for name,off_bps,wait,queue_bps in scenarios:
        vals=[]; folds=[]; maker_fills=0; fb=0; improvements=[]
        for fold,j in rows:
            if name=='IMMEDIATE_TAKER':
                entry=o[j]; ret,_=lifecycle(j,entry,tf,False); ret-=tf
                vals.append(ret); folds.append(fold); improvements.append(0.0); continue
            limit=o[j]*(1-off_bps/1e4)
            fill_idx=None
            for s in range(wait):
                k=j+s
                if l[k] <= limit*(1-queue_bps/1e4):fill_idx=k; break
            if fill_idx is not None:
                maker_fills+=1; entry=limit
                ret,_=lifecycle(fill_idx,entry,tf,True); ret-=mf
                improvements.append((o[j]/entry-1)*1e4)
            else:
                fb+=1; k=j+wait; entry=o[k]
                ret,_=lifecycle(k,entry,tf,False); ret-=tf
                improvements.append((o[j]/entry-1)*1e4)
            vals.append(ret); folds.append(fold)
        a=np.asarray(vals,float); f=np.asarray(folds,int)
        pos=a[a>0].sum(); neg=-a[a<0].sum(); pf=pos/neg if neg>0 else np.inf
        fmeans=[a[f==x].mean()*1e4 for x in sorted(set(f))]
        out.append(dict(bnb=bnb,scenario=name,n=len(a),maker_fill_pct=100*maker_fills/len(a) if len(a) else 0,
        fallback_pct=100*fb/len(a) if len(a) else 0,avg_entry_improve_bps=np.mean(improvements),net_bps=a.mean()*1e4,
        pf=pf,win_pct=100*(a>0).mean(),positive_folds=sum(x>0 for x in fmeans),worst_fold_bps=min(fmeans)))
res=pd.DataFrame(out)
print('\n===== MAKER ENTRY / TAKER FALLBACK =====')
print(res.sort_values(['bnb','net_bps'],ascending=[True,False]).round(4).to_string(index=False))
res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
