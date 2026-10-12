#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
from zoneinfo import ZoneInfo

ROOT=Path('/home/kasm920/binance1-pro')
DATA=ROOT/'data/offline_cache'; OUT=ROOT/'research/results/ALT_LONG_SHORT_CLOCK_ECON_360D.csv'
COINS=['NEAR','SOL','LINK','AVAX','DOGE']
TP=.0020; SL=.0150; H=60
# BNB-discount execution assumption used in prior research: maker entry; maker TP; taker SL/timeout
FEE_WIN=.00036; FEE_LOSS=.00063; FEE_TIMEOUT=.00063
rows=[]

for coin in COINS:
    p=DATA/f'{coin}USDT_1m_360d.csv'
    d=pd.read_csv(p,usecols=['open_time','open','high','low','close'])
    ot=d.open_time.to_numpy(np.int64); o=d.open.to_numpy(float); hi=d.high.to_numpy(float); lo=d.low.to_numpy(float); cl=d.close.to_numpy(float)
    dt=pd.to_datetime(ot,unit='ms',utc=True).tz_convert('Europe/Istanbul')
    # 5m causal anchors: each observation starts at a real 5-minute boundary; avoids counting every overlapping minute as independent.
    anchor=np.flatnonzero((dt.minute.to_numpy()%5)==0)
    anchor=anchor[anchor+H < len(d)]
    for j in anchor:
        e=o[j]; hh=hi[j:j+H]; ll=lo[j:j+H]; cc=cl[j:j+H]
        long_up=hh/e-1; long_dn=ll/e-1
        # SHORT favorable move is price down; adverse is price up
        short_fav=1-ll/e; short_adv=hh/e-1
        bucket=f'{dt[j].hour:02d}:{0 if dt[j].minute<30 else 30:02d}'
        wd=dt[j].weekday()<5
        month=dt[j].strftime('%Y-%m')
        for side in ('LONG','SHORT'):
            if side=='LONG': fav,adv=long_up,-long_dn
            else: fav,adv=short_fav,short_adv
            # conservative same-candle ambiguity: SL first
            state='TIMEOUT'; dur=H; gross=(cc[-1]/e-1) if side=='LONG' else (1-cc[-1]/e)
            for k in range(H):
                if adv[k]>=SL and fav[k]>=TP: state='SL'; dur=k+1; gross=-SL; break
                if adv[k]>=SL: state='SL'; dur=k+1; gross=-SL; break
                if fav[k]>=TP: state='TP'; dur=k+1; gross=TP; break
            fee=FEE_WIN if state=='TP' else (FEE_LOSS if state=='SL' else FEE_TIMEOUT)
            rows.append((coin,side,bucket,wd,month,state,dur,gross,fee,
                         fav[:5].max(),adv[:5].max(),fav[:15].max(),adv[:15].max(),fav[:30].max(),adv[:30].max(),
                         (cc[4]/e-1)*(1 if side=='LONG' else -1),(cc[14]/e-1)*(1 if side=='LONG' else -1),(cc[29]/e-1)*(1 if side=='LONG' else -1)))

cols=['coin','side','bucket','weekday','month','state','dur','gross','fee','mfe5','mae5','mfe15','mae15','mfe30','mae30','ret5','ret15','ret30']
x=pd.DataFrame(rows,columns=cols); x['net']=x.gross-x.fee

out=[]
for (side,bucket),g in x.groupby(['side','bucket'],sort=True):
    coin_net=g.groupby('coin').net.mean()*1e4
    monthly=g.groupby('month').net.mean()*1e4
    weekday=g[g.weekday]; weekend=g[~g.weekday]
    out.append(dict(side=side,bucket=bucket,n=len(g),
        tp_pct=100*(g.state=='TP').mean(),sl_pct=100*(g.state=='SL').mean(),timeout_pct=100*(g.state=='TIMEOUT').mean(),
        gross_bps=1e4*g.gross.mean(),net_bps=1e4*g.net.mean(),pf=(g.net[g.net>0].sum()/(-g.net[g.net<0].sum())) if (g.net<0).any() else np.inf,
        median_dur=float(g.dur.median()),p90_dur=float(g.dur.quantile(.9)),
        mfe5_bps=1e4*g.mfe5.mean(),mae5_bps=1e4*g.mae5.mean(),mfe15_bps=1e4*g.mfe15.mean(),mae15_bps=1e4*g.mae15.mean(),mfe30_bps=1e4*g.mfe30.mean(),mae30_bps=1e4*g.mae30.mean(),
        ret5_bps=1e4*g.ret5.mean(),ret15_bps=1e4*g.ret15.mean(),ret30_bps=1e4*g.ret30.mean(),
        weekday_net_bps=1e4*weekday.net.mean(),weekend_net_bps=1e4*weekend.net.mean(),
        positive_coins=int((coin_net>0).sum()),worst_coin_bps=float(coin_net.min()),best_coin_bps=float(coin_net.max()),
        positive_months=int((monthly>0).sum()),months=len(monthly),median_month_bps=float(monthly.median()),worst_month_bps=float(monthly.min())))
res=pd.DataFrame(out)
res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
for side in ('LONG','SHORT'):
    z=res[res.side.eq(side)]
    print(f'\n===== {side} TOP NET WINDOWS =====')
    print(z.nlargest(12,'net_bps')[['bucket','n','net_bps','pf','tp_pct','sl_pct','timeout_pct','mfe30_bps','mae30_bps','positive_coins','positive_months','months','weekday_net_bps','weekend_net_bps']].round(3).to_string(index=False))
    print(f'\n===== {side} WORST NET WINDOWS =====')
    print(z.nsmallest(8,'net_bps')[['bucket','net_bps','pf','tp_pct','sl_pct','positive_coins','positive_months','worst_month_bps']].round(3).to_string(index=False))
