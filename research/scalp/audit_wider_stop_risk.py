#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd

ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_WIDER_STOP_RISK.csv'
FEE=.0008

# Isolate stop-width effect while keeping the current best lifecycle logic fixed.
# early fail-follow-through + runner unchanged; only hard stop widens.
STOPS=[.0050,.0075,.0100,.0150,.0200,None]
CFG_BASE=dict(early_window=5,early_mfe=.0010,early_mae=.0025,arm=.0020,giveback=.0008,max_hold=10)

def down_exit(op,lo,thr):
    if op<=thr:return op
    if lo<=thr:return thr
    return None

def sim(idx,stop,o,h,l,c):
    e=float(o[idx]); mx=-np.inf; mn=np.inf; armed=False; trail=None
    for k in range(CFG_BASE['max_hold']):
        j=idx+k; op=o[j]/e-1; hi=h[j]/e-1; lo=l[j]/e-1; cl=c[j]/e-1
        if trail is not None:
            x=down_exit(op,lo,trail)
            if x is not None:return x-FEE,k+1,'GIVEBACK'
        if stop is not None:
            x=down_exit(op,lo,-stop)
            if x is not None:return x-FEE,k+1,'HARD_STOP'
        mx=max(mx,hi); mn=min(mn,lo)
        if k+1==CFG_BASE['early_window'] and mx<CFG_BASE['early_mfe'] and mn<=-CFG_BASE['early_mae']:
            return cl-FEE,k+1,'EARLY_EXIT'
        if mx>=CFG_BASE['arm']:armed=True
        if armed:trail=mx-CFG_BASE['giveback']
    return c[idx+CFG_BASE['max_hold']-1]/e-1-FEE,CFG_BASE['max_hold'],'TIME_EXIT'

ds=pd.read_csv(CAND); d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
idx=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
ds['entry_idx']=idx; ds['decile']=pd.qcut(ds.gate_quality.rank(method='first'),10,labels=False)+1

def deep_lowrec(r):
    j=int(r.entry_idx)
    if j<4 or j+12>=len(o): return False
    r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1
    return ((r3<=-.0030) or (r1<=-.0020)) and ((c[j-1]/l[j-1]-1)<.0010)

sets={
    'ALL_GATE':np.ones(len(ds),bool),
    'D7_10':ds.decile.ge(7).to_numpy(),
    'D8':ds.decile.eq(8).to_numpy(),
}
mask_deep=np.array([deep_lowrec(r) for _,r in ds.iterrows()])
sets['D8_DEEP_LOWREC']=ds.decile.eq(8).to_numpy() & mask_deep

rows=[]
for sname,mask in sets.items():
    ids=np.where(mask)[0]
    for stop in STOPS:
        vals=[]; durs=[]; reasons=[]; folds=[]
        for ii in ids:
            j=int(ds.iloc[ii].entry_idx)
            if j+12>=len(o): continue
            ret,dur,reason=sim(j,stop,o,h,l,c)
            vals.append(ret); durs.append(dur); reasons.append(reason); folds.append(int(ds.iloc[ii].gate_fold))
        a=np.asarray(vals,float); f=np.asarray(folds,int)
        pos=a[a>0].sum(); neg=-a[a<0].sum(); pf=pos/neg if neg>0 else np.inf
        fmeans=[a[f==x].mean()*1e4 for x in sorted(set(f)) if np.any(f==x)]
        rows.append(dict(set=sname,stop_pct=('NONE' if stop is None else stop*100),n=len(a),net_bps=a.mean()*1e4,pf=pf,
                         win_pct=(a>0).mean()*100,avg_win_bps=(a[a>0].mean()*1e4 if np.any(a>0) else np.nan),
                         avg_loss_bps=(a[a<0].mean()*1e4 if np.any(a<0) else np.nan),mean_dur=np.mean(durs),
                         tail_le_m50_pct=(a<=-.0050).mean()*100,tail_le_m75_pct=(a<=-.0075).mean()*100,
                         tail_le_m100_pct=(a<=-.0100).mean()*100,hard_stop_pct=100*np.mean(np.array(reasons)=='HARD_STOP'),
                         positive_folds=sum(x>0 for x in fmeans),worst_fold_bps=min(fmeans)))
res=pd.DataFrame(rows)
print('===== WIDER STOP / RISK AUDIT =====')
for s in sets:
    print('\nSET',s)
    print(res[res['set']==s].round(4).to_string(index=False))
res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
