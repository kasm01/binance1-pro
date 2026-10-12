#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_DRAWDOWN_RECOVERY.csv'

ds=pd.read_csv(CAND); d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
idx=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
ds['entry_idx']=idx; ds['decile']=pd.qcut(ds.gate_quality.rank(method='first'),10,labels=False)+1

def deep_lowrec(j):
    if j<4:return False
    r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1
    return ((r3<=-.0030) or (r1<=-.0020)) and ((c[j-1]/l[j-1]-1)<.0010)
sets={
 'ALL_GATE': np.ones(len(ds),bool),
 'D8': ds.decile.eq(8).to_numpy(),
 'D8_DEEP_LOWREC': np.array([bool(ds.decile.iloc[i]==8 and deep_lowrec(int(idx[i]))) for i in range(len(ds))])
}
levels=[.005,.0075,.010,.0125,.015]
horizons=[10,20,30]
rows=[]
for sname,mask in sets.items():
    ids=np.where(mask)[0]
    for lev in levels:
        touched=[]
        for ii in ids:
            j=int(idx[ii]);
            if j<0 or j+30>=len(o): continue
            entry=o[j]
            # first minute whose low touches drawdown threshold
            touch=None
            for k in range(30):
                if l[j+k]/entry-1 <= -lev:
                    touch=k; break
            if touch is None: continue
            rec={}
            for H in horizons:
                end=min(j+H,len(c))
                start=j+touch
                if start>=end:
                    rec[H]=(False,False,False,np.nan)
                    continue
                mx=np.max(h[start:end])/entry-1
                closeH=c[end-1]/entry-1
                rec[H]=(mx>=0, mx>=.0010, mx>=.0020, closeH)
            touched.append(rec)
        n=len(touched)
        if n==0: continue
        row=dict(set=sname,drawdown_pct=lev*100,n_touch=n,touch_rate_pct=100*n/max(1,len(ids)))
        for H in horizons:
            row[f'recover_be_{H}m_pct']=100*np.mean([x[H][0] for x in touched])
            row[f'recover_p10_{H}m_pct']=100*np.mean([x[H][1] for x in touched])
            row[f'recover_p20_{H}m_pct']=100*np.mean([x[H][2] for x in touched])
            row[f'close_{H}m_bps']=1e4*np.mean([x[H][3] for x in touched])
        rows.append(row)
res=pd.DataFrame(rows)
print('===== DRAWDOWN -> RECOVERY AUDIT =====')
for s in res['set'].unique():
    print('\nSET',s)
    cols=['drawdown_pct','n_touch','touch_rate_pct','recover_be_10m_pct','recover_be_20m_pct','recover_be_30m_pct','recover_p10_30m_pct','recover_p20_30m_pct','close_30m_bps']
    print(res[res['set']==s][cols].round(3).to_string(index=False))
res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
