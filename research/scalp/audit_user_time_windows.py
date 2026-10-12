#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_USER_TIME_WINDOWS.csv'
TP=.0020; SL=.0150; H=720

ds=pd.read_csv(CAND); d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
idx=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
ds['decile']=pd.qcut(ds.gate_quality.rank(method='first'),10,labels=False)+1; ds['entry_idx']=idx

def first_hit(j):
    e=o[j]
    for k in range(H):
        jj=j+k; up=h[jj]/e-1; dn=l[jj]/e-1
        if dn<=-SL and up>=TP:return 'SL',k+1,-SL
        if dn<=-SL:return 'SL',k+1,-SL
        if up>=TP:return 'TP',k+1,TP
    return 'UNRES',H,c[j+H-1]/e-1

def in_window(minute):
    w1=(minute>=23*60+30) or (minute<1*60+30)
    w2=(minute>=4*60+30) and (minute<6*60)
    return 'CRITICAL' if (w1 or w2) else 'OTHER'

rows=[]
for _,r in ds[ds.decile.eq(8)].iterrows():
    j=int(r.entry_idx)
    if j<4 or j+H>=len(o):continue
    r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1
    deep=(r3<=-.0030) or (r1<=-.0020)
    lowrec=(c[j-1]/l[j-1]-1)<.0010
    if not (deep and lowrec):continue
    ts=pd.to_datetime(int(r.entry_open_time),unit='ms',utc=True).tz_convert('Europe/Istanbul')
    minute=ts.hour*60+ts.minute
    state,dur,gross=first_hit(j)
    fee=.00036 if state=='TP' else .00063
    net=gross-fee
    rows.append(dict(fold=int(r.gate_fold),local_time=ts.strftime('%Y-%m-%d %H:%M'),hour=ts.hour,minute=ts.minute,window=in_window(minute),state=state,duration_min=dur,gross_bps=gross*1e4,net_bps=net*1e4))
z=pd.DataFrame(rows)
print('N=',len(z),'window_counts=',z.window.value_counts().to_dict())
print('\n===== USER TIME WINDOWS / TP20 SL150 / BNB MIXED FEES =====')
for name,g in z.groupby('window'):
    print(name,'n',len(g),'TP%',round((g.state=='TP').mean()*100,2),'SL%',round((g.state=='SL').mean()*100,2),'net_bps',round(g.net_bps.mean(),4),'med_dur',round(g.duration_min.median(),2),'mean_dur',round(g.duration_min.mean(),2),'folds',g.groupby('fold').net_bps.mean().round(4).to_dict())
print('\n===== BY HALF-HOUR LOCAL BUCKET =====')
z['bucket']=z.hour.map(lambda x:f'{x:02d}:')+np.where(z.minute<30,'00','30')
print(z.groupby('bucket').agg(n=('state','size'),tp_rate=('state',lambda s:(s=='TP').mean()),net_bps=('net_bps','mean')).sort_index().round(4).to_string())
z.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
