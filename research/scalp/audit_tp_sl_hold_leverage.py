#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_TP_SL_HOLD_LEVERAGE.csv'
TPS=[.0015,.0020,.0025,.0030,.0045]
SL=.0150
H=720
FEES={'TT_NO_BNB':.0010,'TT_BNB':.0009,'MT_BNB':.00063}
LEVS=[2,3,5]

ds=pd.read_csv(CAND); d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
idx=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left')
ds['decile']=pd.qcut(ds.gate_quality.rank(method='first'),10,labels=False)+1; ds['entry_idx']=idx
subset=[]
for _,r in ds[ds.decile.eq(8)].iterrows():
    j=int(r.entry_idx)
    if j<4 or j+H>=len(o): continue
    r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1
    deep=(r3<=-.0030) or (r1<=-.0020)
    lowrec=(c[j-1]/l[j-1]-1)<.0010
    if deep and lowrec: subset.append((int(r.gate_fold),j))
print('SUBSET_N=',len(subset))

def first_hit(j,tp):
    e=o[j]
    for k in range(H):
        jj=j+k
        up=h[jj]/e-1; dn=l[jj]/e-1
        # conservative ambiguity: SL first if both touched same candle
        if dn<=-SL and up>=tp: return 'SL',k+1,-SL
        if dn<=-SL: return 'SL',k+1,-SL
        if up>=tp: return 'TP',k+1,tp
    return 'UNRES',H,c[j+H-1]/e-1

rows=[]
for tp in TPS:
    vals=[]; states=[]; durs=[]; folds=[]
    for f,j in subset:
        s,d,r=first_hit(j,tp); states.append(s); durs.append(d); vals.append(r); folds.append(f)
    a=np.asarray(vals,float); d=np.asarray(durs,int); st=np.asarray(states); f=np.asarray(folds)
    base=dict(tp_price_pct=tp*100,sl_price_pct=SL*100,n=len(a),tp_hit_pct=100*np.mean(st=='TP'),sl_hit_pct=100*np.mean(st=='SL'),unresolved_12h_pct=100*np.mean(st=='UNRES'),median_duration_min=float(np.median(d)),mean_duration_min=float(np.mean(d)),p90_duration_min=float(np.quantile(d,.9)),lock_gt30_pct=100*np.mean(d>30),lock_gt60_pct=100*np.mean(d>60),lock_gt120_pct=100*np.mean(d>120),lock_gt240_pct=100*np.mean(d>240),gross_bps=float(a.mean()*1e4))
    for fee_name,fee in FEES.items():
        net=a-fee
        pos=net[net>0].sum(); neg=-net[net<0].sum(); pf=pos/neg if neg>0 else np.inf
        fm=[net[f==x].mean()*1e4 for x in sorted(set(f))]
        row=base|dict(fee_case=fee_name,fee_bps=fee*1e4,net_bps=float(net.mean()*1e4),pf=float(pf),positive_folds=int(sum(x>0 for x in fm)),worst_fold_bps=float(min(fm)))
        rows.append(row)
res=pd.DataFrame(rows)
print('\n===== TP vs -1.5% SL, HOLD UNTIL HIT / 12H CAP =====')
print(res.round(4).to_string(index=False))
print('\n===== LEVERAGE MAPPING (NOTIONAL FIXED; ECONOMICS UNCHANGED) =====')
for lev in LEVS:
    print('LEV',lev,'x','SL_ROI%',round(-SL*lev*100,2),'TP_ROI%',{f'{tp*100:.2f}%':round(tp*lev*100,2) for tp in TPS},'margin_fraction_of_notional',round(1/lev,4))
print('\nNOTE: with fixed notional, leverage changes margin usage and ROI%, not price-path expectancy or dollar PnL per notional.')
res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
