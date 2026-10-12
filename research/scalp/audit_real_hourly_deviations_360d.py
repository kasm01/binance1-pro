#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/'data/offline_cache'
OUT=ROOT/'research/results/ALT_REAL_HOURLY_DEVIATIONS_360D.csv'
COINS=['NEARUSDT','SOLUSDT','LINKUSDT','AVAXUSDT','DOGEUSDT']

frames=[]
for coin in COINS:
    p=CACHE/f'{coin}_1m_360d.csv'
    d=pd.read_csv(p,usecols=['open_time','open','high','low','close'])
    d['dt']=pd.to_datetime(d.open_time,unit='ms',utc=True).dt.tz_convert('Europe/Istanbul')
    d['coin']=coin
    o=d.open.to_numpy(float); h=d.high.to_numpy(float); l=d.low.to_numpy(float); c=d.close.to_numpy(float)
    d['ret1']=c/o-1
    d['abs1']=np.abs(d.ret1)
    d['range1']=h/l-1
    for k in [5,15]:
        d[f'fwd{k}']=np.r_[c[k:]/c[:-k]-1, np.full(k,np.nan)]
        d[f'absf{k}']=np.abs(d[f'fwd{k}'])
    d['bucket']=d.dt.dt.strftime('%H:')+np.where(d.dt.dt.minute<30,'00','30')
    frames.append(d[['open_time','dt','coin','bucket','ret1','abs1','range1','fwd5','absf5','fwd15','absf15']])
allm=pd.concat(frames,ignore_index=True)

wide=allm.pivot(index='open_time',columns='coin',values='ret1').sort_index()
meanret=wide.mean(axis=1); same_up=(wide>0).mean(axis=1); same_dn=(wide<0).mean(axis=1)
breadth=pd.DataFrame({'open_time':wide.index,'mkt_ret1':meanret.values,'up_frac':same_up.values,'dn_frac':same_dn.values})
allm=allm.merge(breadth,on='open_time',how='left')

base=allm.groupby('coin').agg(abs1_base=('abs1','mean'),range1_base=('range1','mean'),absf5_base=('absf5','mean'),absf15_base=('absf15','mean')).reset_index()
allm=allm.merge(base,on='coin')
allm['abs1_ratio']=allm.abs1/allm.abs1_base
allm['range1_ratio']=allm.range1/allm.range1_base
allm['absf5_ratio']=allm.absf5/allm.absf5_base
allm['absf15_ratio']=allm.absf15/allm.absf15_base

rows=[]
for b,g in allm.groupby('bucket'):
    gm=g.drop_duplicates('open_time')
    rows.append(dict(
        bucket=b,n=len(g),days=g.dt.dt.date.nunique(),
        vol1_ratio=g.abs1_ratio.mean(),range1_ratio=g.range1_ratio.mean(),
        vol5_ratio=g.absf5_ratio.mean(),vol15_ratio=g.absf15_ratio.mean(),
        up5_tail_pct=100*np.mean(g.fwd5>=.005),down5_tail_pct=100*np.mean(g.fwd5<=-.005),
        up15_tail_pct=100*np.mean(g.fwd15>=.01),down15_tail_pct=100*np.mean(g.fwd15<=-.01),
        mean_fwd5_bps=g.fwd5.mean()*1e4,mean_fwd15_bps=g.fwd15.mean()*1e4,
        market_abs1_bps=gm.mkt_ret1.abs().mean()*1e4,
        breadth_up80_pct=100*np.mean(gm.up_frac>=.8),breadth_dn80_pct=100*np.mean(gm.dn_frac>=.8),
    ))
res=pd.DataFrame(rows).sort_values('bucket').reset_index(drop=True)
for col in ['vol1_ratio','range1_ratio','vol5_ratio','vol15_ratio','up5_tail_pct','down5_tail_pct','up15_tail_pct','down15_tail_pct','market_abs1_bps','breadth_up80_pct','breadth_dn80_pct']:
    med=res[col].median(); mad=(res[col]-med).abs().median()
    res[col+'_rz']=(res[col]-med)/(1.4826*mad) if mad>0 else 0
res['vol_score']=res[['vol1_ratio_rz','range1_ratio_rz','vol5_ratio_rz','vol15_ratio_rz','market_abs1_bps_rz']].mean(axis=1)
res['long_oppty_score']=res[['up5_tail_pct_rz','up15_tail_pct_rz','breadth_up80_pct_rz']].mean(axis=1)
res['short_oppty_score']=res[['down5_tail_pct_rz','down15_tail_pct_rz','breadth_dn80_pct_rz']].mean(axis=1)
res['asym_bps']=res.mean_fwd15_bps
res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
print('\n===== TOP VOLATILITY WINDOWS =====')
print(res.nlargest(12,'vol_score')[['bucket','vol_score','vol1_ratio','vol5_ratio','vol15_ratio','market_abs1_bps','up5_tail_pct','down5_tail_pct']].round(3).to_string(index=False))
print('\n===== TOP LONG-OPPORTUNITY WINDOWS =====')
print(res.nlargest(10,'long_oppty_score')[['bucket','long_oppty_score','up5_tail_pct','up15_tail_pct','breadth_up80_pct','mean_fwd15_bps']].round(3).to_string(index=False))
print('\n===== TOP SHORT-OPPORTUNITY WINDOWS =====')
print(res.nlargest(10,'short_oppty_score')[['bucket','short_oppty_score','down5_tail_pct','down15_tail_pct','breadth_dn80_pct','mean_fwd15_bps']].round(3).to_string(index=False))
print('\n===== LOWEST VOLATILITY WINDOWS =====')
print(res.nsmallest(8,'vol_score')[['bucket','vol_score','vol1_ratio','vol5_ratio','vol15_ratio','market_abs1_bps']].round(3).to_string(index=False))
