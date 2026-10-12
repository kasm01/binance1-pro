#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_NESTED_EXECUTION_WF.csv'
MAKER=.0002; TAKER=.0005; MAKER_BNB=.00018; TAKER_BNB=.00045
CFG=dict(early_window=5,early_mfe=.0010,early_mae=.0025,arm=.0020,giveback=.0008,hard_stop=.0050,max_hold=10)
SCENS=[('MKR1_W1',1,1),('MKR2_W1',2,1),('MKR3_W1',3,1),('MKR1_W2',1,2),('MKR2_W2',2,2),('MKR3_W2',3,2)]

def down_exit(op,lo,thr):
    if op<=thr:return op
    if lo<=thr:return thr
    return None

def life_from_open(idx,entry,exit_fee,max_hold=10):
    mx=-np.inf; mn=np.inf; armed=False; trail=None
    for step in range(max_hold):
        j=idx+step; op=o[j]/entry-1; hi=h[j]/entry-1; lo=l[j]/entry-1; cl=c[j]/entry-1
        if trail is not None:
            x=down_exit(op,lo,trail)
            if x is not None:return x-exit_fee
        x=down_exit(op,lo,-CFG['hard_stop'])
        if x is not None:return x-exit_fee
        mx=max(mx,hi); mn=min(mn,lo)
        if step+1==CFG['early_window'] and mx<CFG['early_mfe'] and mn<=-CFG['early_mae']:return cl-exit_fee
        if mx>=CFG['arm']:armed=True
        if armed:trail=mx-CFG['giveback']
    return c[idx+max_hold-1]/entry-1-exit_fee

def life_after_fill(fill_idx,entry,exit_fee):
    if l[fill_idx]/entry-1<=-CFG['hard_stop']:
        return -CFG['hard_stop']-exit_fee
    return life_from_open(fill_idx+1,entry,exit_fee,max_hold=CFG['max_hold']-1)

def deep_lowrec(j):
    if j<4:return False
    r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1
    deep=(r3<=-.0030) or (r1<=-.0020)
    lowrec=(c[j-1]/l[j-1]-1)<.0010
    return bool(deep and lowrec)

def select_subset(frame,q70,q80):
    out=[]
    for _,r in frame.iterrows():
        if not (q70<=float(r.gate_quality)<q80):continue
        j=int(r.entry_idx)
        if j+15>=len(o):continue
        if deep_lowrec(j):out.append((int(r.gate_fold),j))
    return out

def run_subset(subset,scenario,bnb):
    name,off,wait=scenario
    mf=MAKER_BNB if bnb else MAKER; tf=TAKER_BNB if bnb else TAKER
    vals=[]; fills=0; fbacks=0
    for _,j in subset:
        limit=o[j]*(1-off/1e4); fill=None
        for s in range(wait):
            k=j+s
            if l[k]<=limit:
                fill=k; break
        if fill is not None:
            fills+=1; ret=life_after_fill(fill,limit,tf)-mf
        else:
            fbacks+=1; k=j+wait; entry=o[k]; ret=life_from_open(k,entry,tf)-tf
        vals.append(ret)
    a=np.asarray(vals,float)
    if len(a)==0:return dict(n=0,net=np.nan,pf=np.nan,fill=np.nan,fb=np.nan)
    pos=a[a>0].sum(); neg=-a[a<0].sum(); pf=pos/neg if neg>0 else np.inf
    return dict(n=len(a),net=a.mean()*1e4,pf=pf,fill=100*fills/len(a),fb=100*fbacks/len(a))

ds=pd.read_csv(CAND); d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
ds['entry_idx']=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
rows=[]
for bnb in [False,True]:
    for test_fold in [2,3,4]:
        cal=ds[ds.gate_fold<test_fold].copy(); test=ds[ds.gate_fold==test_fold].copy()
        q70=float(cal.gate_quality.quantile(.70)); q80=float(cal.gate_quality.quantile(.80))
        cal_sub=select_subset(cal,q70,q80); test_sub=select_subset(test,q70,q80)
        perf=[]
        for sc in SCENS:
            r=run_subset(cal_sub,sc,bnb); perf.append((sc,r))
        perf=[x for x in perf if x[1]['n']>=10 and np.isfinite(x[1]['net'])]
        if not perf:
            rows.append(dict(bnb=bnb,test_fold=test_fold,q70=q70,q80=q80,cal_n=len(cal_sub),test_n=len(test_sub),selected='NONE'))
            continue
        best=max(perf,key=lambda x:x[1]['net'])
        tr=best[1]; te=run_subset(test_sub,best[0],bnb)
        rows.append(dict(bnb=bnb,test_fold=test_fold,q70=q70,q80=q80,cal_n=len(cal_sub),test_n=len(test_sub),selected=best[0][0],cal_net_bps=tr['net'],cal_pf=tr['pf'],test_net_bps=te['net'],test_pf=te['pf'],maker_fill_pct=te['fill'],fallback_pct=te['fb']))
res=pd.DataFrame(rows)
print('===== NESTED EXECUTION WALK-FORWARD =====')
print(res.round(4).to_string(index=False))
for bnb,g in res.groupby('bnb'):
    valid=g[g.test_n.fillna(0)>0]
    if len(valid):
        weighted=np.average(valid.test_net_bps,weights=valid.test_n)
        print('BNB=',bnb,'WEIGHTED_TEST_NET_BPS=',round(weighted,4),'POSITIVE_FOLDS=',int((valid.test_net_bps>0).sum()),'/',len(valid),'TOTAL_TEST_N=',int(valid.test_n.sum()))
res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
