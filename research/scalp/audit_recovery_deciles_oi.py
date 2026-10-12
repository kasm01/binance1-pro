#!/usr/bin/env python3
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'
ds=pd.read_csv(R/'NEAR_DUAL_GATE_CANDIDATES.csv.gz'); d1=pd.read_csv(ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'); oi=pd.read_csv(R/'OKX_NEAR_OI_4H_360d.csv.gz')
ot=d1.open_time.to_numpy(np.int64);o=d1.open.to_numpy(float);h=d1.high.to_numpy(float);l=d1.low.to_numpy(float);c=d1.close.to_numpy(float)
ds['entry_idx']=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left'); ds['decile']=pd.qcut(ds.gate_quality.rank(method='first'),10,labels=False)+1
oi=oi.sort_values('ts'); oi['oi_ret1']=oi.oi_contracts.pct_change(); left=ds[['entry_open_time']].copy(); left['_rid']=np.arange(len(ds)); left['t']=pd.to_datetime(left.entry_open_time,unit='ms',utc=True); ox=oi[['ts','oi_ret1']].copy(); ox['t']=pd.to_datetime(ox.ts,unit='ms',utc=True)
m=pd.merge_asof(left.sort_values('t'),ox[['t','oi_ret1']].sort_values('t'),on='t',direction='backward').sort_values('_rid'); ds['oi_ret1']=m.oi_ret1.to_numpy()
TP=.002;SL=.015;H=720
rows=[]
for _,r in ds[ds.decile.ge(7)].iterrows():
 j=int(r.entry_idx)
 if j<4 or j+H>=len(o) or pd.isna(r.oi_ret1):continue
 r3=c[j-1]/c[j-4]-1;r1=c[j-1]/c[j-2]-1
 if not (((r3<=-.003) or (r1<=-.002)) and ((c[j-1]/l[j-1]-1)<.001)):continue
 e=o[j];st='UNRES';gross=c[j+H-1]/e-1;dur=H
 for k in range(H):
  up=h[j+k]/e-1;dn=l[j+k]/e-1
  if dn<=-SL:st='SL';gross=-SL;dur=k+1;break
  if up>=TP:st='TP';gross=TP;dur=k+1;break
 fee=.00036 if st=='TP' else .00063
 rg=('PXUP_' if r3>0 else 'PXDN_')+('OIUP' if r.oi_ret1>=0 else 'OIDN')
 ts=pd.to_datetime(int(r.entry_open_time),unit='ms',utc=True)
 rows.append(dict(decile=int(r.decile),fold=int(r.gate_fold),month=str(ts.to_period('M')),regime=rg,state=st,net=(gross-fee)*1e4,dur=dur))
x=pd.DataFrame(rows); out=R/'NEAR_RECOVERY_DECILES_OI.csv';x.to_csv(out,index=False)
print('ALL BY DECILE')
for d,z in x.groupby('decile'):
 print('D',d,'n',len(z),'tp',round((z.state=='TP').mean(),4),'net',round(z.net.mean(),4),'folds',z.fold.nunique())
print('\nD9 BY REGIME/FOLD')
print(x[x.decile.eq(9)].groupby(['fold','regime']).agg(n=('state','size'),tp=('state',lambda s:(s=='TP').mean()),net=('net','mean'),dur=('dur','mean')).round(4).to_string())
print('\nD9 OIUP MONTHS')
z=x[(x.decile.eq(9))&(x.regime.eq('PXDN_OIUP'))]
print(z.groupby('month').agg(n=('state','size'),tp=('state',lambda s:(s=='TP').mean()),net=('net','mean')).round(4).to_string())
print('TOTAL',len(z),'TP',round((z.state=='TP').mean(),4),'NET',round(z.net.mean(),4),'months',z.month.nunique())
print('OUTPUT',out)
