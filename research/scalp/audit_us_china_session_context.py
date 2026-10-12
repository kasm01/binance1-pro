#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/offline_cache'
OUT=ROOT/'research/results/NEAR_US_CHINA_SESSION_CONTEXT.csv'
COINS=['NEAR','SOL','LINK','AVAX','DOGE']

frames={}
for coin in COINS:
    df=pd.read_csv(DATA/f'{coin}USDT_1m_360d.csv',usecols=['open_time','open','high','low','close'])
    ts=pd.to_datetime(df.open_time,unit='ms',utc=True)
    df=df.assign(ts=ts)
    df['ret1']=df.close.pct_change()
    df['abs_ret1']=df.ret1.abs()
    df['range1']=(df.high/df.low-1)
    frames[coin]=df

near=frames['NEAR'].copy()
# timezone-aware clocks; Turkey has fixed UTC+3, China UTC+8, NY DST-aware.
near['tr']=near.ts.dt.tz_convert('Europe/Istanbul')
near['cn']=near.ts.dt.tz_convert('Asia/Shanghai')
near['ny']=near.ts.dt.tz_convert('America/New_York')
near['tr_min']=near.tr.dt.hour*60+near.tr.dt.minute
near['cn_min']=near.cn.dt.hour*60+near.cn.dt.minute
near['ny_min']=near.ny.dt.hour*60+near.ny.dt.minute

# Event windows: first 60 min after China cash open, US cash open, US cash close.
sessions={
 'CHINA_OPEN_0930_1030_CST': (near.cn_min>=570)&(near.cn_min<630),
 'US_OPEN_0930_1030_ET': (near.ny_min>=570)&(near.ny_min<630),
 'US_CLOSE_1600_1700_ET': (near.ny_min>=960)&(near.ny_min<1020),
 'USER_TR_2330_0130': (near.tr_min>=1410)|(near.tr_min<90),
 'USER_TR_0430_0600': (near.tr_min>=270)&(near.tr_min<360),
}
rows=[]
for name,mask in sessions.items():
    x=near.loc[mask]
    rows.append(dict(scope='NEAR_1M_ALL',session=name,n=len(x),mean_abs_ret_bps=x.abs_ret1.mean()*1e4,
                     p90_abs_ret_bps=x.abs_ret1.quantile(.9)*1e4,mean_range_bps=x.range1.mean()*1e4,
                     p90_range_bps=x.range1.quantile(.9)*1e4))
# baseline all minutes
x=near
rows.append(dict(scope='NEAR_1M_ALL',session='ALL_MINUTES',n=len(x),mean_abs_ret_bps=x.abs_ret1.mean()*1e4,
                 p90_abs_ret_bps=x.abs_ret1.quantile(.9)*1e4,mean_range_bps=x.range1.mean()*1e4,
                 p90_range_bps=x.range1.quantile(.9)*1e4))

# Cross-coin breadth: average 1m return and share negative at NEAR timestamps.
base=pd.DataFrame({'open_time':near.open_time})
for coin in COINS:
    d=frames[coin][['open_time','ret1']].rename(columns={'ret1':coin})
    base=base.merge(d,on='open_time',how='left')
rets=base[COINS]
base['breadth_mean']=rets.mean(axis=1)
base['breadth_neg_share']=(rets<0).mean(axis=1)
base['breadth_disp']=rets.std(axis=1)
for name,mask in sessions.items():
    x=base.loc[mask.to_numpy()]
    rows.append(dict(scope='ALT_BREADTH_1M',session=name,n=len(x),mean_abs_ret_bps=x.breadth_mean.abs().mean()*1e4,
                     p90_abs_ret_bps=x.breadth_mean.abs().quantile(.9)*1e4,mean_range_bps=x.breadth_neg_share.mean()*100,
                     p90_range_bps=x.breadth_disp.quantile(.9)*1e4))
x=base
rows.append(dict(scope='ALT_BREADTH_1M',session='ALL_MINUTES',n=len(x),mean_abs_ret_bps=x.breadth_mean.abs().mean()*1e4,
                 p90_abs_ret_bps=x.breadth_mean.abs().quantile(.9)*1e4,mean_range_bps=x.breadth_neg_share.mean()*100,
                 p90_range_bps=x.breadth_disp.quantile(.9)*1e4))

res=pd.DataFrame(rows)
res.to_csv(OUT,index=False)
print('===== SESSION VOLATILITY / BREADTH AUDIT =====')
print(res.round(4).to_string(index=False))

# Relative ratios vs baseline for easy interpretation.
print('\n===== RATIOS VS ALL MINUTES =====')
for scope,g in res.groupby('scope'):
    b=g[g.session.eq('ALL_MINUTES')].iloc[0]
    print('\n',scope)
    for _,r in g[~g.session.eq('ALL_MINUTES')].iterrows():
        print(r.session,'abs_ret_x',round(r.mean_abs_ret_bps/b.mean_abs_ret_bps,3),
              'p90_abs_x',round(r.p90_abs_ret_bps/b.p90_abs_ret_bps,3),
              'third_metric_x',round(r.mean_range_bps/b.mean_range_bps,3))
print('OUTPUT=',OUT)
