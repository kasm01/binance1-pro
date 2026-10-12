#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'
CAND=R/'NEAR_DUAL_GATE_CANDIDATES.csv.gz'; D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'; OI=R/'OKX_NEAR_OI_4H_360d.csv.gz'
OUT=R/'NEAR_OKX_OI_ROLLING_STABILITY.csv'
TP=.0020; SL=.015; H=720

ds=pd.read_csv(CAND); d1=pd.read_csv(D1); oi=pd.read_csv(OI)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
ds['entry_idx']=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
oi['t']=pd.to_datetime(oi.ts,unit='ms',utc=True); oi=oi.sort_values('t'); oi['oi_ret1']=oi.oi_contracts.pct_change()
left=pd.DataFrame({'rid':np.arange(len(ds)),'t':pd.to_datetime(ds.entry_open_time,unit='ms',utc=True)}).sort_values('t')
mm=pd.merge_asof(left,oi[['t','oi_ret1']],on='t',direction='backward').sort_values('rid'); ds['oi_ret1']=mm.oi_ret1.to_numpy()
ds['ts']=pd.to_datetime(ds.entry_open_time,unit='ms',utc=True)

def first_hit(j):
    if j<4 or j+H>=len(o): return None
    e=o[j]
    for k in range(H):
        jj=j+k; dn=l[jj]/e-1; up=h[jj]/e-1
        if dn<=-SL:return ('SL',k+1,-SL)
        if up>=TP:return ('TP',k+1,TP)
    return ('UNRES',H,c[j+H-1]/e-1)

# Fixed robust rule chosen from previous sensitivity region, not re-optimized per window.
qlo,qhi=ds.gate_quality.quantile([.75,.90])
rows=[]
for _,r in ds.iterrows():
    j=int(r.entry_idx)
    if j<4 or j+H>=len(o):continue
    r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1
    lowrec=(c[j-1]/l[j-1]-1)<.0010
    if not (qlo<=r.gate_quality<=qhi):continue
    if not ((r3<=-.0025) or (r1<=-.0030)):continue
    if not lowrec:continue
    if not (pd.notna(r.oi_ret1) and r.oi_ret1>0):continue
    fh=first_hit(j)
    if fh is None:continue
    st,dur,gross=fh; fee=.0010 if st in ('TP','SL','UNRES') else .0010
    rows.append(dict(ts=r.ts,fold=int(r.gate_fold),state=st,dur=dur,gross=gross,net=gross-fee,oi_ret1=float(r.oi_ret1),q=float(r.gate_quality),r3=r3,r1=r1))
z=pd.DataFrame(rows).sort_values('ts').reset_index(drop=True)
print('FIXED_RULE_N',len(z),'TP',round((z.state=='TP').mean(),4),'NET_BPS',round(z.net.mean()*1e4,4))

# 30m de-overlap globally
keep=[]; last=None
for i,r in z.iterrows():
    if last is None or (r.ts-last)>=pd.Timedelta(minutes=30): keep.append(i); last=r.ts
z=z.loc[keep].reset_index(drop=True)
print('DEOVERLAP_N',len(z),'TP',round((z.state=='TP').mean(),4),'NET_BPS',round(z.net.mean()*1e4,4))

out=[]
for days,step in [(30,15),(60,30)]:
    start=z.ts.min().floor('D'); end=z.ts.max().ceil('D')
    cur=start
    while cur<end:
        nxt=cur+pd.Timedelta(days=days); a=z[(z.ts>=cur)&(z.ts<nxt)]
        if len(a):
            out.append(dict(window_days=days,start=cur,end=nxt,n=len(a),tp_rate=(a.state=='TP').mean(),sl_rate=(a.state=='SL').mean(),net_bps=a.net.mean()*1e4,mean_dur=a.dur.mean(),median_oi_pct=a.oi_ret1.median()*100,folds=a['fold'].nunique()))
        cur+=pd.Timedelta(days=step)
res=pd.DataFrame(out); res.to_csv(OUT,index=False)
print('\n30D WINDOWS')
print(res[res.window_days.eq(30)].round(4).to_string(index=False))
print('\n60D WINDOWS')
print(res[res.window_days.eq(60)].round(4).to_string(index=False))
for d in [30,60]:
    a=res[res.window_days.eq(d)]
    print('\nSUMMARY',d,'windows',len(a),'positive',int((a.net_bps>0).sum()),'negative',int((a.net_bps<0).sum()),'median_net',round(a.net_bps.median(),4),'worst',round(a.net_bps.min(),4),'best',round(a.net_bps.max(),4),'median_n',round(a.n.median(),1))
print('OUTPUT',OUT)
