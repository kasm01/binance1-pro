#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'
CAND=R/'NEAR_DUAL_GATE_CANDIDATES.csv.gz'; D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'; OI=R/'OKX_NEAR_OI_4H_360d.csv.gz'
TP=.002; SL=.015; H=720
BANDS=[(.75,.90),(.80,.90),(.80,.95),(.75,.95),(.70,.90),(.85,.95)]
DEEP3=[-.0025,-.0030,-.0035,-.0040]; DEEP1=[-.0015,-.0020,-.0025,-.0030]
LOWREC=[.0005,.0010,.0015,.0020]
OI_MAG_Q=[0.0,.25,.50,.75]

ds=pd.read_csv(CAND); d1=pd.read_csv(D1); oi=pd.read_csv(OI).sort_values('ts')
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
ds['entry_idx']=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
oi['oi_ret1']=oi.oi_contracts.pct_change(); oi['t']=pd.to_datetime(oi.ts,unit='ms',utc=True)
left=pd.DataFrame({'rid':np.arange(len(ds)),'t':pd.to_datetime(ds.entry_open_time,unit='ms',utc=True)}).sort_values('t')
m=pd.merge_asof(left,oi[['t','oi_ret1']].sort_values('t'),on='t',direction='backward').sort_values('rid')
ds['oi_ret1']=m.oi_ret1.to_numpy()

def fh(j):
    if j<5 or j+H>=len(o): return None
    e=o[j]
    for k in range(H):
        jj=j+k
        if l[jj]/e-1<=-SL:return 'SL',k+1,-SL
        if h[jj]/e-1>=TP:return 'TP',k+1,TP
    return 'UNRES',H,c[j+H-1]/e-1

def eval_set(z):
    if len(z)==0:return None
    arr=[]
    for _,r in z.iterrows():
        q=fh(int(r.entry_idx))
        if q is None: continue
        st,dur,g=q; fee=.0010; arr.append((st,dur,(g-fee)*1e4))
    if not arr:return None
    a=pd.DataFrame(arr,columns=['st','dur','net'])
    return len(a),(a.st=='TP').mean(),a.net.mean(),a.dur.mean()
rows=[]
for lo,hi in BANDS:
  for d3 in DEEP3:
   for d1thr in DEEP1:
    for lr in LOWREC:
      base=[]
      for _,r in ds.iterrows():
        j=int(r.entry_idx)
        if j<5 or j+H>=len(o):continue
        r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1
        deep=(r3<=d3) or (r1<=d1thr); low=(c[j-1]/l[j-1]-1)<lr
        if deep and low and pd.notna(r.oi_ret1): base.append((r.name,r3))
      if not base:continue
      ids=[x[0] for x in base]; z=ds.loc[ids].copy(); z['r3x']=[x[1] for x in base]
      qlo,qhi=z.gate_quality.quantile([lo,hi]); z=z[(z.gate_quality>=qlo)&(z.gate_quality<=qhi)]
      z=z[(z.r3x<0)&(z.oi_ret1>0)]
      if len(z)<8:continue
      for oq in OI_MAG_Q:
        zz=z.copy()
        if oq>0:
            cut=zz.oi_ret1.quantile(oq); zz=zz[zz.oi_ret1>=cut]
        res=eval_set(zz)
        if res is None:continue
        n,tp,net,dur=res
        folds=zz.gate_fold.nunique()
        rows.append(dict(lo=lo,hi=hi,d3=d3,d1=d1thr,lowrec=lr,oi_q=oq,n=n,tp=tp,netbps=net,dur=dur,folds=folds))
out=pd.DataFrame(rows)
out.to_csv(R/'NEAR_OI_SENSITIVITY.csv',index=False)
print('ROWS',len(out))
print('\nTOP ROBUST')
z=out[(out.n>=20)&(out.folds>=3)].copy(); z['score']=z.netbps*np.log1p(z.n)
print(z.sort_values(['netbps','n'],ascending=False).head(40).round(4).to_string(index=False))
print('\nGRID STABILITY BY BAND')
print(z.groupby(['lo','hi']).agg(cases=('n','size'),n_med=('n','median'),tp_med=('tp','median'),net_med=('netbps','median'),net_min=('netbps','min'),net_max=('netbps','max')).round(4).sort_values('net_med',ascending=False).to_string())
print('\nFAIL RATE (<0 bps) BY BAND')
print(z.assign(neg=z.netbps<0).groupby(['lo','hi']).agg(cases=('neg','size'),neg_rate=('neg','mean')).round(4).to_string())
