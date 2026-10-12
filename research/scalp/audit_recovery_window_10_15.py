#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_RECOVERY_WINDOW_10_15.csv'
CFG_BASE=dict(early_window=5,early_mfe=.0010,early_mae=.0025,arm=.0020,giveback=.0008)

def down_exit(op,lo,thr):
    if op<=thr:return op
    if lo<=thr:return thr
    return None

def sim(idx,hard_stop,max_hold):
    e=float(o[idx]); mx=-np.inf; mn=np.inf; armed=False; trail=None
    for k in range(max_hold):
        j=idx+k; op=o[j]/e-1; hi=h[j]/e-1; lo=l[j]/e-1; cl=c[j]/e-1
        if trail is not None:
            x=down_exit(op,lo,trail)
            if x is not None:return x,k+1,'GIVEBACK'
        x=down_exit(op,lo,-hard_stop)
        if x is not None:return x,k+1,'HARD_STOP'
        mx=max(mx,hi); mn=min(mn,lo)
        if k+1==CFG_BASE['early_window'] and mx<CFG_BASE['early_mfe'] and mn<=-CFG_BASE['early_mae']:
            return cl,k+1,'EARLY_EXIT'
        if mx>=CFG_BASE['arm']: armed=True
        if armed: trail=mx-CFG_BASE['giveback']
    return c[idx+max_hold-1]/e-1,max_hold,'TIME_EXIT'

ds=pd.read_csv(CAND); d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
ds['entry_idx']=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
ds['decile']=pd.qcut(ds.gate_quality.rank(method='first'),10,labels=False)+1

def is_deep_lowrec(j):
    if j<4:return False
    r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1
    return ((r3<=-.0030) or (r1<=-.0020)) and ((c[j-1]/l[j-1]-1)<.0010)

sets={
 'ALL_GATE':np.ones(len(ds),dtype=bool),
 'D8':ds.decile.eq(8).to_numpy(),
 'D8_DEEP_LOWREC':np.array([bool(ds.decile.iloc[i]==8 and is_deep_lowrec(int(ds.entry_idx.iloc[i]))) for i in range(len(ds))])
}
variants=[('CURRENT_H10_HS05',10,.005),('WIDE_H10_HS15',10,.015),('WIDE_H15_HS15',15,.015)]
rows=[]
for sname,mask in sets.items():
    ids=np.where(mask)[0]
    for vname,mh,hs in variants:
        vals=[]; durs=[]; reasons=[]; folds=[]
        for ii in ids:
            j=int(ds.entry_idx.iloc[ii])
            if j<4 or j+mh>=len(o):continue
            r,d,why=sim(j,hs,mh); vals.append(r); durs.append(d); reasons.append(why); folds.append(int(ds.gate_fold.iloc[ii]))
        a=np.asarray(vals,float); f=np.asarray(folds,int)
        gross_bps=a.mean()*1e4
        pos=a[a>0].sum(); neg=-a[a<0].sum(); gross_pf=pos/neg if neg>0 else np.inf
        fm=[a[f==x].mean()*1e4 for x in sorted(set(f))]
        for fee_bps in [8.0,10.0,9.0]:
            net=a-fee_bps/1e4
            p=net[net>0].sum(); n=-net[net<0].sum(); pf=p/n if n>0 else np.inf
            rows.append(dict(set=sname,variant=vname,max_hold=mh,hard_stop_pct=hs*100,fee_bps=fee_bps,n=len(a),gross_bps=gross_bps,net_bps=net.mean()*1e4,pf=pf,win_pct=100*(net>0).mean(),mean_dur=np.mean(durs),hard_stop_hit_pct=100*np.mean(np.array(reasons)=='HARD_STOP'),tail_le_m100_pct=100*np.mean(a<=-.0100),tail_le_m150_pct=100*np.mean(a<=-.0150),positive_gross_folds=sum(x>0 for x in fm),worst_gross_fold_bps=min(fm)))
res=pd.DataFrame(rows)
print('===== RECOVERY WINDOW 10 vs 15 / HARD STOP 1.5% =====')
for s in sets:
    print('\nSET',s)
    print(res[(res['set']==s)&(res.fee_bps.isin([8.0,10.0]))].round(4).to_string(index=False))
res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
