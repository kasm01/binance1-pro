#!/usr/bin/env python3
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'
CAND=R/'NEAR_DUAL_GATE_CANDIDATES.csv.gz'; D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'; OI=R/'OKX_NEAR_OI_4H_360d.csv.gz'; OUT=R/'NEAR_NESTED_OI_EXACT_ROLLING.csv'
TP=.002;SL=.015;H=720

ds=pd.read_csv(CAND);d1=pd.read_csv(D1);oi=pd.read_csv(OI)
ot=d1.open_time.to_numpy(np.int64);o=d1.open.to_numpy(float);h=d1.high.to_numpy(float);l=d1.low.to_numpy(float);c=d1.close.to_numpy(float)
ds['entry_idx']=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left');ds['ts']=pd.to_datetime(ds.entry_open_time,unit='ms',utc=True)
oi['t']=pd.to_datetime(oi.ts,unit='ms',utc=True);oi=oi.sort_values('t');oi['oi_ret1']=oi.oi_contracts.pct_change()
left=pd.DataFrame({'rid':np.arange(len(ds)),'t':ds.ts}).sort_values('t');m=pd.merge_asof(left,oi[['t','oi_ret1']],on='t',direction='backward').sort_values('rid');ds['oi_ret1']=m.oi_ret1.to_numpy()

def fh(j):
 e=o[j]
 for k in range(H):
  jj=j+k
  if l[jj]/e-1<=-SL:return 'SL',k+1,-SL
  if h[jj]/e-1>=TP:return 'TP',k+1,TP
 return 'UNRES',H,c[j+H-1]/e-1

def eligible(r):
 j=int(r.entry_idx)
 if j<4 or j+H>=len(o):return False
 r3=c[j-1]/c[j-4]-1;r1=c[j-1]/c[j-2]-1
 return ((r3<=-.003) or (r1<=-.002)) and ((c[j-1]/l[j-1]-1)<.001) and pd.notna(r.oi_ret1)

valid=ds.apply(eligible,axis=1); rows=[]
for tf in [2,3,4]:
 tr=ds[(ds.gate_fold<tf)&valid].copy();te=ds[(ds.gate_fold==tf)&valid].copy()
 qlo,qhi=tr.gate_quality.quantile([.80,.90]);trb=tr[(tr.gate_quality>=qlo)&(tr.gate_quality<=qhi)];teb=te[(te.gate_quality>=qlo)&(te.gate_quality<=qhi)]
 # Exact regime fixed by prior nested discovery: PXDN_OIUP. Price-down is guaranteed by deep/r3 when r1 branch may fire, so enforce r3<0.
 ter=teb[(teb.oi_ret1>0)]
 for _,r in ter.iterrows():
  j=int(r.entry_idx);r3=c[j-1]/c[j-4]-1
  if r3>=0:continue
  st,dur,gross=fh(j);rows.append(dict(ts=r.ts,fold=tf,state=st,dur=dur,net=gross-.001,q=r.gate_quality,oi_ret1=r.oi_ret1))
z=pd.DataFrame(rows).sort_values('ts')
print('OOS_N',len(z),'TP',round((z.state=='TP').mean(),4),'NET',round(z.net.mean()*1e4,4))
# de-overlap 30m
keep=[];last=None
for i,r in z.iterrows():
 if last is None or r.ts-last>=pd.Timedelta(minutes=30):keep.append(i);last=r.ts
z=z.loc[keep].reset_index(drop=True);print('OOS_COOL30_N',len(z),'TP',round((z.state=='TP').mean(),4),'NET',round(z.net.mean()*1e4,4))
out=[]
for days,step in [(30,15),(60,30)]:
 cur=z.ts.min().floor('D');end=z.ts.max().ceil('D')
 while cur<end:
  a=z[(z.ts>=cur)&(z.ts<cur+pd.Timedelta(days=days))]
  if len(a):out.append(dict(window_days=days,start=cur,n=len(a),tp=(a.state=='TP').mean(),netbps=a.net.mean()*1e4,folds=a['fold'].nunique()))
  cur+=pd.Timedelta(days=step)
r=pd.DataFrame(out);r.to_csv(OUT,index=False)
print(r.round(4).to_string(index=False))
for d in [30,60]:
 a=r[r.window_days.eq(d)];print('SUMMARY',d,'pos',int((a.netbps>0).sum()),'neg',int((a.netbps<0).sum()),'zero',int((a.netbps==0).sum()),'median',round(a.netbps.median(),4),'worst',round(a.netbps.min(),4),'median_n',round(a.n.median(),1))
print('OUTPUT',OUT)
