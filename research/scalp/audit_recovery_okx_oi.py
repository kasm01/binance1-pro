#!/usr/bin/env python3
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OI=ROOT/'research/results/OKX_NEAR_OI_4H_360d.csv.gz'
OUT=ROOT/'research/results/NEAR_RECOVERY_OKX_OI.csv'
TP=.0020; SL=.015; H=720

ds=pd.read_csv(CAND); d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
ds['entry_idx']=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
ds['decile']=pd.qcut(ds.gate_quality.rank(method='first'),10,labels=False)+1

oi=pd.read_csv(OI);oi['t']=pd.to_datetime(oi.ts,unit='ms',utc=True);oi=oi.sort_values('t');oi['oi']=oi.oi_ccy.astype(float)
for k in [1,2,3,6]:oi[f'oi_ret{k}']=oi.oi.pct_change(k)

def first_hit(j):
 e=o[j]
 for k in range(H):
  jj=j+k;up=h[jj]/e-1;dn=l[jj]/e-1
  if dn<=-SL:return 'SL',k+1,-SL
  if up>=TP:return 'TP',k+1,TP
 return 'UNRES',H,c[j+H-1]/e-1
rows=[]
for _,r in ds[ds.decile.eq(8)].iterrows():
 j=int(r.entry_idx)
 if j<4 or j+H>=len(o):continue
 r3=c[j-1]/c[j-4]-1;r1=c[j-1]/c[j-2]-1
 deep=(r3<=-.0030) or (r1<=-.0020);lowrec=(c[j-1]/l[j-1]-1)<.0010
 if not(deep and lowrec):continue
 st,dur,gross=first_hit(j);fee=.00036 if st=='TP' else .00063;net=gross-fee
 rows.append(dict(entry_open_time=int(r.entry_open_time),fold=int(r.gate_fold),state=st,dur=dur,gross=gross,net=net,m5_ret1=float(r.m5_ret1)))
x=pd.DataFrame(rows);x['t']=pd.to_datetime(x.entry_open_time,unit='ms',utc=True)
x=pd.merge_asof(x.sort_values('t'),oi[['t','oi_ret1','oi_ret2','oi_ret3','oi_ret6']],on='t',direction='backward',tolerance=pd.Timedelta('8h'))
x['oi_up']=x.oi_ret1>0;x['px_up']=x.m5_ret1>0
x['regime']=np.select([x.px_up&x.oi_up,x.px_up&~x.oi_up,~x.px_up&x.oi_up,~x.px_up&~x.oi_up],['PXUP_OIUP','PXUP_OIDN','PXDN_OIUP','PXDN_OIDN'])
print('N',len(x),'TP',round((x.state=='TP').mean(),4),'SL',round((x.state=='SL').mean(),4),'NET_BPS',round(x.net.mean()*10000,4))
print('\nREGIMES')
for name,g in x.groupby('regime'):
 print(name,'n',len(g),'tp',round((g.state=='TP').mean(),4),'sl',round((g.state=='SL').mean(),4),'netbps',round(g.net.mean()*10000,4),'dur',round(g.dur.mean(),2))
print('\nOI EXTREMES CAUSAL')
out=[]
for tf in [2,3,4]:
 tr=x[x.fold<tf];te=x[x.fold.eq(tf)]
 if len(tr)<20 or len(te)<5:continue
 for k in [1,2,3,6]:
  col=f'oi_ret{k}'
  for q in [.2,.25,.3]:
   lo=tr[col].quantile(q);hi=tr[col].quantile(1-q)
   for seg,m in [('LOW',te[col]<=lo),('MID',(te[col]>lo)&(te[col]<hi)),('HIGH',te[col]>=hi)]:
    g=te[m]
    if len(g)<3:continue
    out.append(dict(fold=tf,k=k,q=q,seg=seg,n=len(g),tp=(g.state=='TP').mean(),sl=(g.state=='SL').mean(),netbps=g.net.mean()*10000,dur=g.dur.mean()))
y=pd.DataFrame(out);print(y.round(4).to_string(index=False))
x.to_csv(OUT,index=False);print('\nOUTPUT',OUT)
