#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
ALT=ROOT/'research/results/ALT_MARKET_CONTEXT_3M.csv'
OUT=ROOT/'research/results/NEAR_RECOVERY_FOLD4_FAILURE.csv'
TP=.0020; SL=.015; H=720

ds=pd.read_csv(CAND); d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float); v=d1.volume.to_numpy(float)
ds['entry_idx']=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
ds['decile']=pd.qcut(ds.gate_quality.rank(method='first'),10,labels=False)+1

def first_hit(j):
    e=o[j]
    for k in range(H):
        jj=j+k; up=h[jj]/e-1; dn=l[jj]/e-1
        if dn<=-SL and up>=TP:return 'SL',k+1,-SL
        if dn<=-SL:return 'SL',k+1,-SL
        if up>=TP:return 'TP',k+1,TP
    return 'UNRES',H,c[j+H-1]/e-1

rows=[]
for _,r in ds[ds.decile.eq(8)].iterrows():
    j=int(r.entry_idx)
    if j<25 or j+H>=len(o):continue
    r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1
    deep=(r3<=-.0030) or (r1<=-.0020)
    lowrec=(c[j-1]/l[j-1]-1)<.0010
    if not (deep and lowrec):continue
    st,dur,ret=first_hit(j)
    # causal 1m pre-entry context
    ret5=c[j-1]/c[j-6]-1; ret15=c[j-1]/c[j-16]-1
    vol20=v[j-21:j-1]; volz=(v[j-1]-vol20.mean())/(vol20.std()+1e-12)
    rng20=(h[j-20:j].max()/l[j-20:j].min()-1)
    ts=pd.to_datetime(int(r.entry_open_time),unit='ms',utc=True)
    rows.append(dict(fold=int(r.gate_fold),state=st,dur=dur,ret=ret,quality=float(r.gate_quality),hour=int(ts.hour),dow=int(ts.dayofweek),r1=r1,r3=r3,ret5=ret5,ret15=ret15,recovery=c[j-1]/l[j-1]-1,volz1=volz,range20=rng20,
      m3_atr=float(r.m3_atr14),m5_atr=float(r.m5_atr14),m15_atr=float(r.m15_atr14),m3_ret1=float(r.m3_ret1),m5_ret1=float(r.m5_ret1),m15_ret1=float(r.m15_ret1),m3_slope=float(r.m3_e20_slope3),m5_slope=float(r.m5_e20_slope3),m15_slope=float(r.m15_e20_slope3),m3_buy=float(r.m3_buy_ratio),m5_buy=float(r.m5_buy_ratio),m15_buy=float(r.m15_buy_ratio),m3_volz=float(r.m3_vol_z20),m5_volz=float(r.m5_vol_z20),m15_volz=float(r.m15_vol_z20)))
z=pd.DataFrame(rows)
print('N=',len(z),'fold_counts=',z.fold.value_counts().sort_index().to_dict())
print('\n===== FOLD OUTCOMES TP20 / SL150 =====')
for f,g in z.groupby('fold'):
    print('FOLD',f,'n',len(g),'TP%',round((g.state=='TP').mean()*100,2),'SL%',round((g.state=='SL').mean()*100,2),'gross_bps',round(g.ret.mean()*1e4,4),'med_dur',round(g.dur.median(),2),'mean_dur',round(g.dur.mean(),2))

features=['quality','r1','r3','ret5','ret15','recovery','volz1','range20','m3_atr','m5_atr','m15_atr','m3_ret1','m5_ret1','m15_ret1','m3_slope','m5_slope','m15_slope','m3_buy','m5_buy','m15_buy','m3_volz','m5_volz','m15_volz']
print('\n===== FOLD4 VS FOLD1-3 MEDIANS =====')
bad=z[z.fold==4]; good=z[z.fold<4]
for col in features:
    a=float(bad[col].median()); b=float(good[col].median()); mad=float(np.median(np.abs(good[col]-b)))+1e-12
    rd=(a-b)/mad
    if abs(rd)>=0.5: print(col,'fold4',round(a,6),'prev',round(b,6),'robust_diff',round(rd,3))

print('\n===== WITHIN FOLD4: TP vs SL MEDIANS =====')
f4=z[z.fold==4]
for col in features:
    tp=f4[f4.state=='TP'][col]; sl=f4[f4.state=='SL'][col]
    if len(tp)==0 or len(sl)==0:continue
    a=float(tp.median()); b=float(sl.median()); allmed=float(f4[col].median()); mad=float(np.median(np.abs(f4[col]-allmed)))+1e-12
    rd=(a-b)/mad
    if abs(rd)>=0.5: print(col,'TP',round(a,6),'SL',round(b,6),'robust_diff',round(rd,3))

print('\n===== FOLD4 TIME-OF-DAY =====')
tab=f4.groupby('hour').agg(n=('state','size'),tp_rate=('state',lambda s:(s=='TP').mean()),gross_bps=('ret',lambda x:x.mean()*1e4)).reset_index()
print(tab[tab.n>=2].round(4).to_string(index=False))
z.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
