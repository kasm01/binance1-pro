#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
OI=ROOT/'research/results/OKX_NEAR_OI_4H_360d.csv.gz'
OUT=ROOT/'research/results/NEAR_OKX_POSITIONING_REGIMES_WF.csv'

df=pd.read_csv(CAND)
strong=(df.mfe_5m_pct>=0.20)&(df.mae_5m_pct>=-0.15)&(df.time_to_mfe_5m<=3)
danger=(df.mae_10m_pct<=-0.50)|(df.net_10m_pct<=-0.30)
df=df.loc[strong|danger].copy(); df['y']=strong[strong|danger].astype(int).to_numpy()
df['t']=pd.to_datetime(df.feature_close_time,unit='ms',utc=True)

oi=pd.read_csv(OI); oi['t']=pd.to_datetime(oi.ts,unit='ms',utc=True); oi=oi.sort_values('t')
oi['oi']=oi['oi_ccy'].astype(float)
for k in [1,2,3,6]: oi[f'oi_ret{k}']=oi['oi'].pct_change(k)
oi['oi_z20']=(oi.oi-oi.oi.rolling(20,min_periods=5).mean())/(oi.oi.rolling(20,min_periods=5).std()+1e-12)
keep=['t','oi_ret1','oi_ret2','oi_ret3','oi_ret6','oi_z20']
df=pd.merge_asof(df.sort_values('t'),oi[keep],on='t',direction='backward',tolerance=pd.Timedelta('8h'))

df['px_up']=df.m5_ret1>0
df['oi_up']=df.oi_ret1>0
df['regime']=np.select([
    df.px_up & df.oi_up,
    df.px_up & ~df.oi_up,
    ~df.px_up & df.oi_up,
    ~df.px_up & ~df.oi_up,
],[
    'PRICE_UP_OI_UP_NEW_LONG',
    'PRICE_UP_OI_DOWN_SHORT_COVER',
    'PRICE_DOWN_OI_UP_NEW_SHORT',
    'PRICE_DOWN_OI_DOWN_LONG_LIQ',
],default='UNKNOWN')

rows=[]
for fold in sorted(df.gate_fold.unique()):
    z=df[df.gate_fold.eq(fold)]
    for r,g in z.groupby('regime'):
        if len(g)<5: continue
        rows.append(dict(fold=int(fold),regime=r,n=len(g),strong_rate=g.y.mean(),danger_rate=1-g.y.mean(),mfe5_bps=g.mfe_5m_pct.mean()*100,mae5_bps=g.mae_5m_pct.mean()*100,net10_bps=g.net_10m_pct.mean()*100,gate_q=g.gate_quality.mean(),oi_ret1=g.oi_ret1.mean()*100,m5_ret1=g.m5_ret1.mean()*100))
r=pd.DataFrame(rows); r.to_csv(OUT,index=False)
print('LABELED',len(df),'OI_COVERAGE',round(df.oi_ret1.notna().mean(),4))
print('\n===== ALL FOLDS COMBINED =====')
agg=df.groupby('regime').agg(n=('y','size'),strong_rate=('y','mean'),net10_pct=('net_10m_pct','mean'),mfe5=('mfe_5m_pct','mean'),mae5=('mae_5m_pct','mean'),gate_q=('gate_quality','mean')).reset_index()
agg['net10_bps']=agg.net10_pct*100; agg['mfe5_bps']=agg.mfe5*100; agg['mae5_bps']=agg.mae5*100
print(agg[['regime','n','strong_rate','net10_bps','mfe5_bps','mae5_bps','gate_q']].round(4).sort_values('strong_rate',ascending=False).to_string(index=False))
print('\n===== BY FOLD =====')
print(r[['fold','regime','n','strong_rate','net10_bps','mfe5_bps','mae5_bps']].round(4).to_string(index=False))

sel=[]
for tf in [2,3,4]:
    tr=df[df.gate_fold<tf]; te=df[df.gate_fold.eq(tf)]
    stats=tr.groupby('regime').agg(n=('y','size'),strong=('y','mean'),net=('net_10m_pct','mean'))
    stats=stats[stats.n>=30].copy()
    if stats.empty: continue
    stats['score']=stats.strong + 0.05*stats.net.clip(-1,1)
    best=stats.score.idxmax(); worst=stats.score.idxmin()
    for label,reg in [('BEST_PRIOR',best),('WORST_PRIOR',worst)]:
        g=te[te.regime.eq(reg)]
        if len(g)==0: continue
        sel.append(dict(test_fold=tf,selection=label,regime=reg,n=len(g),strong_rate=g.y.mean(),net10_bps=g.net_10m_pct.mean()*100,mfe5_bps=g.mfe_5m_pct.mean()*100,mae5_bps=g.mae_5m_pct.mean()*100))
s=pd.DataFrame(sel)
print('\n===== CAUSAL PRIOR-FOLD REGIME SELECTION =====')
print(s.round(4).to_string(index=False))
print('\nOUTPUT',OUT)
