#!/usr/bin/env python3
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'
x=pd.read_csv(R/'NEAR_RECOVERY_DECILES_OI.csv')
# Need original event times: rebuild selected D9 PXDN_OIUP events from source using same logic.
ds=pd.read_csv(R/'NEAR_DUAL_GATE_CANDIDATES.csv.gz'); d1=pd.read_csv(ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'); oi=pd.read_csv(R/'OKX_NEAR_OI_4H_360d.csv.gz')
ot=d1.open_time.to_numpy(np.int64);o=d1.open.to_numpy(float);h=d1.high.to_numpy(float);l=d1.low.to_numpy(float);c=d1.close.to_numpy(float)
ds['entry_idx']=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left');ds['decile']=pd.qcut(ds.gate_quality.rank(method='first'),10,labels=False)+1
oi=oi.sort_values('ts');oi['oi_ret1']=oi.oi_contracts.pct_change(); left=pd.DataFrame({'rid':np.arange(len(ds)),'t':pd.to_datetime(ds.entry_open_time,unit='ms',utc=True)}).sort_values('t'); ox=pd.DataFrame({'t':pd.to_datetime(oi.ts,unit='ms',utc=True),'oi_ret1':oi.oi_ret1})
m=pd.merge_asof(left,ox.sort_values('t'),on='t',direction='backward').sort_values('rid');ds['oi_ret1']=m.oi_ret1.to_numpy()
TP=.002;SL=.015;H=720;rows=[]
for _,r in ds[ds.decile.eq(9)].iterrows():
 j=int(r.entry_idx)
 if j<4 or j+H>=len(o) or pd.isna(r.oi_ret1):continue
 r3=c[j-1]/c[j-4]-1;r1=c[j-1]/c[j-2]-1
 if not (((r3<=-.003) or (r1<=-.002)) and ((c[j-1]/l[j-1]-1)<.001) and r3<=0 and r.oi_ret1>=0):continue
 e=o[j];st='UNRES';gross=c[j+H-1]/e-1;dur=H
 for k in range(H):
  if l[j+k]/e-1<=-SL:st='SL';gross=-SL;dur=k+1;break
  if h[j+k]/e-1>=TP:st='TP';gross=TP;dur=k+1;break
 fee_bnb=.00036 if st=='TP' else .00063; fee_nobnb=.00040 if st=='TP' else .00070
 rows.append(dict(t=int(r.entry_open_time),fold=int(r.gate_fold),state=st,dur=dur,grossbps=gross*1e4,net_bnb=(gross-fee_bnb)*1e4,net_nobnb=(gross-fee_nobnb)*1e4))
e=pd.DataFrame(rows).sort_values('t')

def thin(df,coolmin):
 keep=[];last=-10**30
 for i,r in df.iterrows():
  if int(r.t)-last>=coolmin*60000:
   keep.append(i);last=int(r.t)
 return df.loc[keep]
print('D9 PXDN_OIUP DEOVERLAP')
for cm in [0,5,15,30,60,120]:
 z=e if cm==0 else thin(e,cm)
 print('cool',cm,'n',len(z),'tp',round((z.state=='TP').mean(),4),'bnb',round(z.net_bnb.mean(),4),'nobnb',round(z.net_nobnb.mean(),4),'folds',z.fold.value_counts().sort_index().to_dict())
print('\n30M BY FOLD')
z=thin(e,30)
print(z.groupby('fold').agg(n=('state','size'),tp=('state',lambda s:(s=='TP').mean()),bnb=('net_bnb','mean'),nobnb=('net_nobnb','mean'),dur=('dur','mean')).round(4).to_string())
print('\n30M BY MONTH')
z['month']=pd.to_datetime(z.t,unit='ms',utc=True).dt.strftime('%Y-%m')
print(z.groupby('month').agg(n=('state','size'),tp=('state',lambda s:(s=='TP').mean()),bnb=('net_bnb','mean'),nobnb=('net_nobnb','mean')).round(4).to_string())
