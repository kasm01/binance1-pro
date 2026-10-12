#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]; CACHE=ROOT/'data/offline_cache'
OUT=ROOT/'research/results/ALT_HOURLY_DEVIATION_ROBUSTNESS.csv'
COINS=['NEARUSDT','SOLUSDT','LINKUSDT','AVAXUSDT','DOGEUSDT']
WATCH=['16:30','17:00','17:30','18:00','18:30','19:00','00:00','03:00','04:00','04:30','05:00','23:30']
rows=[]
for coin in COINS:
    d=pd.read_csv(CACHE/f'{coin}_1m_360d.csv',usecols=['open_time','open','close'])
    dt=pd.to_datetime(d.open_time,unit='ms',utc=True).dt.tz_convert('Europe/Istanbul')
    ret=np.abs(d.close.to_numpy(float)/d.open.to_numpy(float)-1)
    x=pd.DataFrame({'dt':dt,'abs1':ret})
    x['bucket']=x.dt.dt.strftime('%H:')+np.where(x.dt.dt.minute<30,'00','30')
    x['month']=x.dt.dt.to_period('M').astype(str); x['weekday']=x.dt.dt.weekday<5
    # trim coin-specific top 1% to ensure not driven by a few crash candles
    cap=np.nanquantile(x.abs1,.99); x['abs1_trim']=np.minimum(x.abs1,cap)
    for period,mask in [('ALL',np.ones(len(x),bool)),('WEEKDAY',x.weekday.values),('WEEKEND',~x.weekday.values)]:
        z=x.loc[mask].copy(); base=z.abs1.mean(); baset=z.abs1_trim.mean()
        for b in WATCH:
            g=z[z.bucket.eq(b)]
            rows.append(dict(coin=coin,period=period,bucket=b,n=len(g),ratio=g.abs1.mean()/base,trim_ratio=g.abs1_trim.mean()/baset))
    # monthly stability vs each month's own baseline
    for m,g0 in x.groupby('month'):
        base=g0.abs1.mean(); baset=g0.abs1_trim.mean()
        for b in WATCH:
            g=g0[g0.bucket.eq(b)]
            rows.append(dict(coin=coin,period='MONTH_'+m,bucket=b,n=len(g),ratio=g.abs1.mean()/base,trim_ratio=g.abs1_trim.mean()/baset))
res=pd.DataFrame(rows); res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
print('\n===== CROSS-COIN ROBUSTNESS =====')
agg=res[res.period.isin(['ALL','WEEKDAY','WEEKEND'])].groupby(['period','bucket']).agg(ratio=('ratio','mean'),trim_ratio=('trim_ratio','mean'),coins=('coin','nunique')).reset_index()
for p in ['ALL','WEEKDAY','WEEKEND']:
    print('\n',p)
    print(agg[agg.period.eq(p)].sort_values('trim_ratio',ascending=False).round(3).to_string(index=False))
print('\n===== MONTHLY STABILITY, CROSS-COIN MEDIAN =====')
mo=res[res.period.str.startswith('MONTH_')].copy()
# first average across coins within month/bucket, then summarize months
mm=mo.groupby(['period','bucket']).agg(ratio=('ratio','mean'),trim_ratio=('trim_ratio','mean')).reset_index()
st=mm.groupby('bucket').agg(months=('period','nunique'),median_ratio=('ratio','median'),median_trim=('trim_ratio','median'),months_gt_110=('trim_ratio',lambda s:int((s>1.10).sum())),months_gt_120=('trim_ratio',lambda s:int((s>1.20).sum())),worst_month=('trim_ratio','min'),best_month=('trim_ratio','max')).reset_index()
print(st.sort_values('median_trim',ascending=False).round(3).to_string(index=False))
