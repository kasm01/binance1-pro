#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
DS=ROOT/"research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz"
D1=ROOT/"data/offline_cache/NEARUSDT_1m_360d.csv"
OUT=ROOT/"research/results/NEAR_GATE_DECILES_FEE_SCENARIOS.csv"
ds=pd.read_csv(DS).sort_values("feature_close_time").reset_index(drop=True)
d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.astype(float).to_numpy(); h=d1.high.astype(float).to_numpy(); l=d1.low.astype(float).to_numpy(); c=d1.close.astype(float).to_numpy()
idxs=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side="left")
# Best diagnostic lifecycle from prior 24-variant audit. Gross return only here.
EW,MFE,MAE,ARM,GB,HS,MH=5,.0010,.0025,.0020,.0008,.0050,10
def down(op,lo,thr):
    if op<=thr:return op
    if lo<=thr:return thr
    return None
def sim(idx):
    entry=float(o[idx]); mx=-np.inf; mn=np.inf; armed=False; trail=None
    for k in range(MH):
        j=idx+k; op=o[j]/entry-1; hi=h[j]/entry-1; lo=l[j]/entry-1; cl=c[j]/entry-1
        if trail is not None:
            x=down(op,lo,trail)
            if x is not None:return x
        x=down(op,lo,-HS)
        if x is not None:return x
        mx=max(mx,hi); mn=min(mn,lo)
        if (k+1)==EW and mx<MFE and mn<=-MAE:return cl
        if mx>=ARM: armed=True
        if armed: trail=mx-GB
    return c[idx+MH-1]/entry-1
gross=np.array([sim(int(i)) for i in idxs],float)
ds["gross_ret"]=gross
# Fold-relative deciles: 1=lowest score, 10=highest score.
ds["decile"]=0
for f,g in ds.groupby("gate_fold"):
    ranks=g.gate_quality.rank(method="first",pct=True)
    dec=np.ceil(ranks*10).clip(1,10).astype(int)
    ds.loc[g.index,"decile"]=dec
scenarios={
 "CURRENT_TAKER_TAKER_NO_BNB":.0010,
 "BNB_TAKER_TAKER":.0009,
 "BNB_MAKER_TAKER":.00063,
 "BNB_MAKER_MAKER":.00036,
}
def pf(x):
    p=x[x>0].sum(); n=-x[x<0].sum(); return float(p/n) if n>0 else np.inf
rows=[]
for d,g in ds.groupby("decile"):
    row={"decile":int(d),"n":len(g),"score_mean":g.gate_quality.mean(),"gross_bps":g.gross_ret.mean()*10000,"gross_pf":pf(g.gross_ret.to_numpy())}
    for name,fee in scenarios.items():
        x=g.gross_ret.to_numpy()-fee
        row[name+"_net_bps"]=x.mean()*10000; row[name+"_pf"]=pf(x)
    rows.append(row)
res=pd.DataFrame(rows).sort_values("decile")
res.to_csv(OUT,index=False)
print("===== GATE SCORE DECILES (1 LOW -> 10 HIGH) =====")
print(res.round(4).to_string(index=False))
print("\n===== MONOTONIC CHECK =====")
print("GROSS_MONOTONIC_INCREASING=",bool(res.gross_bps.is_monotonic_increasing))
for name in scenarios:
    col=name+"_net_bps"; print(name,"BEST_DECILE=",int(res.loc[res[col].idxmax(),"decile"]),"BEST_NET_BPS=",round(float(res[col].max()),4),"POSITIVE_DECILES=",int((res[col]>0).sum()))
print("OUTPUT=",OUT)
