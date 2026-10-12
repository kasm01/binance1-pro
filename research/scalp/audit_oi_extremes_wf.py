#!/usr/bin/env python3
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
D=pd.read_csv(ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz')
strong=(D.mfe_5m_pct>=0.20)&(D.mae_5m_pct>=-0.15)&(D.time_to_mfe_5m<=3)
danger=(D.mae_10m_pct<=-0.50)|(D.net_10m_pct<=-0.30)
D=D.loc[strong|danger].copy();D['y']=strong[strong|danger].astype(int).to_numpy();D['t']=pd.to_datetime(D.feature_close_time,unit='ms',utc=True)
O=pd.read_csv(ROOT/'research/results/OKX_NEAR_OI_4H_360d.csv.gz');O['t']=pd.to_datetime(O.ts,unit='ms',utc=True);O=O.sort_values('t');O['oi']=O.oi_ccy.astype(float)
for k in [1,2,3,6]: O[f'oi_ret{k}']=O.oi.pct_change(k)
D=pd.merge_asof(D.sort_values('t'),O[['t','oi_ret1','oi_ret2','oi_ret3','oi_ret6']],on='t',direction='backward',tolerance=pd.Timedelta('8h'))
rows=[]
for tf in [2,3,4]:
 tr=D[D.gate_fold<tf]; te=D[D.gate_fold.eq(tf)]
 for k in [1,2,3,6]:
  c=f'oi_ret{k}'
  for q in [.2,.25,.3]:
   lo=tr[c].quantile(q);hi=tr[c].quantile(1-q)
   masks={
    'EXTREME_UP':te[c]>=hi,'EXTREME_DOWN':te[c]<=lo,'MID':(te[c]>lo)&(te[c]<hi),
    'PXUP_EXTUP':(te.m5_ret1>0)&(te[c]>=hi),'PXUP_EXTDOWN':(te.m5_ret1>0)&(te[c]<=lo),
    'PXDN_EXTUP':(te.m5_ret1<=0)&(te[c]>=hi),'PXDN_EXTDOWN':(te.m5_ret1<=0)&(te[c]<=lo)}
   for name,m in masks.items():
    g=te[m]
    if len(g)<5:continue
    rows.append(dict(fold=tf,oi_horizon=k,q=q,segment=name,n=len(g),strong_rate=g.y.mean(),net10_bps=g.net_10m_pct.mean()*100,mfe5_bps=g.mfe_5m_pct.mean()*100,mae5_bps=g.mae_5m_pct.mean()*100,thr_lo=lo*100,thr_hi=hi*100))
r=pd.DataFrame(rows);out=ROOT/'research/results/NEAR_OKX_OI_EXTREMES_WF.csv';r.to_csv(out,index=False)
print('===== BEST STABLE SEGMENTS (weighted across folds) =====')
a=[]
for keys,g in r.groupby(['oi_horizon','q','segment']):
 if g['fold'].nunique()<3:continue
 w=g.n.to_numpy();a.append((*keys,g.n.sum(),np.average(g.strong_rate,weights=w),np.average(g.net10_bps,weights=w),g.strong_rate.min(),g.strong_rate.max()))
a=pd.DataFrame(a,columns=['oi_horizon','q','segment','n','strong_w','net10_w','strong_min','strong_max'])
print(a.sort_values(['strong_w','n'],ascending=[False,False]).head(25).round(4).to_string(index=False))
print('\n===== WORST / DANGER-HEAVY =====')
print(a.sort_values(['strong_w','n'],ascending=[True,False]).head(20).round(4).to_string(index=False))
print('\nOUTPUT',out)
