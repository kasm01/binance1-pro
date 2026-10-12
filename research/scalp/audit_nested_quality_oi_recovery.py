#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OI=ROOT/'research/results/OKX_NEAR_OI_4H_360d.csv.gz'
OUT=ROOT/'research/results/NEAR_NESTED_QUALITY_OI_RECOVERY.csv'
TP=.0020; SL=.015; H=720
BANDS=[(.60,.80),(.70,.80),(.70,.90),(.60,.90),(.80,.90),(.80,1.00),(.70,1.00),(.60,1.00)]

ds=pd.read_csv(CAND); d1=pd.read_csv(D1); oi=pd.read_csv(OI)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
ds['entry_idx']=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
oi['t']=pd.to_datetime(oi.ts,unit='ms',utc=True); oi=oi.sort_values('t')
oi['oi_ret1']=oi.oi_contracts.pct_change(1)
left=pd.DataFrame({'_rid':np.arange(len(ds)),'t':pd.to_datetime(ds.entry_open_time,unit='ms',utc=True)}).sort_values('t')
mapdf=pd.merge_asof(left,oi[['t','oi_ret1']],on='t',direction='backward').sort_values('_rid')
ds['oi_ret1']=mapdf.oi_ret1.to_numpy()

def first_hit(j):
    if j<4 or j+H>=len(o): return None
    e=o[j]
    for k in range(H):
        jj=j+k; up=h[jj]/e-1; dn=l[jj]/e-1
        if dn<=-SL: return ('SL',k+1,-SL)
        if up>=TP: return ('TP',k+1,TP)
    return ('UNRES',H,c[j+H-1]/e-1)

def enrich(r):
    j=int(r.entry_idx)
    if j<4 or j+H>=len(o): return None
    r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1
    deep=(r3<=-.0030) or (r1<=-.0020)
    lowrec=(c[j-1]/l[j-1]-1)<.0010
    if not (deep and lowrec): return None
    fh=first_hit(j)
    if fh is None:return None
    st,dur,gross=fh
    fee=.00036 if st=='TP' else .00063
    pxdir='UP' if r3>0 else 'DN'
    oidir='UP' if float(r.oi_ret1)>=0 else 'DN'
    return pd.Series({'state':st,'dur':dur,'gross':gross,'net':gross-fee,'regime':f'PX{pxdir}_OI{oidir}','r3':r3})

extra=[]
for i,r in ds.iterrows():
    z=enrich(r)
    if z is not None:
        z['idx']=i; extra.append(z)
e=pd.DataFrame(extra).set_index('idx')
ds=ds.join(e)
valid=ds.state.notna() & ds.oi_ret1.notna()
print('RECOVERY_VALID',int(valid.sum()))
rows=[]
for tf in [2,3,4]:
    tr=ds[(ds.gate_fold<tf)&valid].copy(); te=ds[(ds.gate_fold==tf)&valid].copy()
    if len(tr)<20 or len(te)<3: continue
    band_stats=[]
    for lo,hi in BANDS:
        qlo,qhi=tr.gate_quality.quantile([lo,hi])
        z=tr[(tr.gate_quality>=qlo)&(tr.gate_quality<=qhi)]
        if len(z)<12: continue
        band_stats.append((float(z.net.mean()),len(z),lo,hi,float(qlo),float(qhi)))
    if not band_stats: continue
    band_stats.sort(reverse=True)
    train_net,ntr,lo,hi,qlo,qhi=band_stats[0]
    trb=tr[(tr.gate_quality>=qlo)&(tr.gate_quality<=qhi)]
    teb=te[(te.gate_quality>=qlo)&(te.gate_quality<=qhi)]
    if teb.empty: continue
    regstats=[]
    for rg,z in trb.groupby('regime'):
        if len(z)>=5: regstats.append((float(z.net.mean()),len(z),rg))
    regstats.sort(reverse=True)
    best_reg=regstats[0][2] if regstats else 'NONE'
    trr=trb[trb.regime.eq(best_reg)] if best_reg!='NONE' else trb.iloc[:0]
    ter=teb[teb.regime.eq(best_reg)] if best_reg!='NONE' else teb.iloc[:0]
    def stats(z):
        if len(z)==0:return dict(n=0,tp=np.nan,sl=np.nan,netbps=np.nan,dur=np.nan)
        return dict(n=len(z),tp=(z.state=='TP').mean(),sl=(z.state=='SL').mean(),netbps=z.net.mean()*1e4,dur=z.dur.mean())
    sb,sr=stats(teb),stats(ter)
    rows.append(dict(test_fold=tf,band=f'{lo:.2f}-{hi:.2f}',train_band_n=ntr,train_band_netbps=train_net*1e4,qlo=qlo,qhi=qhi,best_regime=best_reg,train_reg_n=len(trr),train_reg_netbps=(trr.net.mean()*1e4 if len(trr) else np.nan),test_band_n=sb['n'],test_band_tp=sb['tp'],test_band_sl=sb['sl'],test_band_netbps=sb['netbps'],test_band_dur=sb['dur'],test_reg_n=sr['n'],test_reg_tp=sr['tp'],test_reg_sl=sr['sl'],test_reg_netbps=sr['netbps'],test_reg_dur=sr['dur']))

out=pd.DataFrame(rows); out.to_csv(OUT,index=False)
print('\nNESTED RESULTS')
print(out.round(4).to_string(index=False))
if not out.empty:
    b=out.dropna(subset=['test_band_netbps']); r=out.dropna(subset=['test_reg_netbps'])
    if len(b): print('\nWEIGHTED BASE',round(np.average(b.test_band_netbps,weights=b.test_band_n),4),'bps n',int(b.test_band_n.sum()))
    if len(r) and r.test_reg_n.sum()>0: print('WEIGHTED OI',round(np.average(r.test_reg_netbps,weights=r.test_reg_n),4),'bps n',int(r.test_reg_n.sum()))
print('OUTPUT',OUT)
