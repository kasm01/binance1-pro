#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_MICRO_CONFIRM_FILTERS.csv'
FEE=0.0008
cand=pd.read_csv(CAND).sort_values('feature_close_time').reset_index(drop=True)
cand['decile']=pd.qcut(cand['gate_quality'],10,labels=False,duplicates='drop')+1
d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.astype(float).to_numpy(); h=d1.high.astype(float).to_numpy(); l=d1.low.astype(float).to_numpy(); c=d1.close.astype(float).to_numpy()

def down(op,lo,thr):
    if op<=thr:return op
    if lo<=thr:return thr
    return None

def sim(idx):
    entry=o[idx]; max_seen=-np.inf; min_seen=np.inf; armed=False; trail=None
    for k in range(10):
        j=idx+k; op=o[j]/entry-1; hi=h[j]/entry-1; lo=l[j]/entry-1; cl=c[j]/entry-1
        if trail is not None:
            x=down(op,lo,trail)
            if x is not None:return x,k+1
        x=down(op,lo,-.005)
        if x is not None:return x,k+1
        max_seen=max(max_seen,hi); min_seen=min(min_seen,lo)
        if (k+1)==5 and max_seen<.0010 and min_seen<=-.0025:return cl,k+1
        if max_seen>=.0020: armed=True
        if armed: trail=max_seen-.0008
    return c[idx+9]/entry-1,10

recs=[]
for _,r in cand.iterrows():
    if int(r.decile)<7:continue
    idx=int(np.searchsorted(ot,int(r.entry_open_time),side='left'))
    if idx<3 or idx+10>len(d1):continue
    gross,dur=sim(idx)
    p1=(c[idx-1]/o[idx-1]-1)
    r1=(c[idx-1]/c[idx-2]-1)
    rng=max(h[idx-1]-l[idx-1],1e-12)
    loc=(c[idx-1]-l[idx-1])/rng
    recs.append({'fold':int(r.gate_fold),'decile':int(r.decile),'gross':gross,'r1':r1,'body':p1,'loc':loc,'dur':dur})
z=pd.DataFrame(recs)
filters={
'ALL':np.ones(len(z),dtype=bool),
'R1_POS':z.r1>0,
'R1_GE_M5BPS':z.r1>=-.0005,
'BODY_POS':z.body>0,
'CLOSE_UPPER_HALF':z['loc']>=.5,
'R1_POS_AND_UPPER':(z.r1>0)&(z['loc']>=.5),
'R1_GE_M5_AND_UPPER':(z.r1>=-.0005)&(z['loc']>=.5),
}
rows=[]
for dset,base in [('D7_10',z.decile>=7),('D8',z.decile==8),('D9_10',z.decile>=9)]:
  for name,m in filters.items():
    q=z[base & m]
    if len(q)==0:continue
    pos=q.gross[q.gross>0].sum(); neg=-q.gross[q.gross<0].sum(); pf=pos/neg if neg>0 else np.inf
    fm=q.groupby('fold').gross.mean()*1e4
    rows.append({'set':dset,'filter':name,'n':len(q),'coverage_pct':100*len(q)/base.sum(),'gross_bps':q.gross.mean()*1e4,'net_8bps':q.gross.mean()*1e4-8,'gross_pf':pf,'positive_folds':int((fm>0).sum()),'worst_fold_bps':fm.min(),'mean_dur':q.dur.mean()})
res=pd.DataFrame(rows).sort_values(['set','gross_bps'],ascending=[True,False])
print('===== MICRO CONFIRMATION FILTER AUDIT =====')
print(res.round(4).to_string(index=False))
res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
