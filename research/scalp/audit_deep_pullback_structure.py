#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/"research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz"
D1=ROOT/"data/offline_cache/NEARUSDT_1m_360d.csv"
OUT=ROOT/"research/results/NEAR_D8_DEEP_PULLBACK_STRUCTURE.csv"
FEE=.0008
# best lifecycle: 5m failed-follow-through + runner
CFG=dict(hard_stop=.0050,max_hold=10,early_window=5,early_mfe=.0010,early_mae=.0025,arm=.0020,giveback=.0008)

def down_exit(op,lo,thr):
    if op<=thr:return op
    if lo<=thr:return thr
    return None

def sim(idx,o,h,l,c):
    e=float(o[idx]); mx=-np.inf; mn=np.inf; armed=False; trail=None
    for k in range(10):
        j=idx+k; op=o[j]/e-1; hi=h[j]/e-1; lo=l[j]/e-1; cl=c[j]/e-1
        if trail is not None:
            x=down_exit(op,lo,trail)
            if x is not None:return x-FEE
        x=down_exit(op,lo,-CFG["hard_stop"])
        if x is not None:return x-FEE
        mx=max(mx,hi); mn=min(mn,lo)
        if k+1==CFG["early_window"] and mx<CFG["early_mfe"] and mn<=-CFG["early_mae"]: return cl-FEE
        if mx>=CFG["arm"]: armed=True
        if armed: trail=mx-CFG["giveback"]
    return c[idx+9]/e-1-FEE

ds=pd.read_csv(CAND)
d1=pd.read_csv(D1)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.astype(float).to_numpy(); h=d1.high.astype(float).to_numpy(); l=d1.low.astype(float).to_numpy(); c=d1.close.astype(float).to_numpy(); v=d1.volume.astype(float).to_numpy()
idx=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side="left")
# deciles globally, same convention as prior audit
rank=pd.qcut(ds.gate_quality.rank(method="first"),10,labels=False)+1
ds=ds.assign(decile=rank,entry_idx=idx)
x=ds[ds.decile.eq(8)].copy()
rows=[]
for _,r in x.iterrows():
    j=int(r.entry_idx)
    if j<21 or j+10>len(d1): continue
    rr=np.array([c[j-k]/c[j-k-1]-1 for k in [3,2,1]])  # chronological t-3,t-2,t-1
    r3=(c[j-1]/c[j-4]-1)
    r1=c[j-1]/c[j-2]-1
    deep=(r3<=-.0030) or (r1<=-.0020)
    if not deep: continue
    po,ph,pl,pc=o[j-1],h[j-1],l[j-1],c[j-1]
    rng=max(ph-pl,1e-12)
    close_loc=(pc-pl)/rng
    lower_wick=(min(po,pc)-pl)/rng
    body=(pc-po)/po
    rec_from_low=(pc/pl-1)
    low_vs_prevlow=(pl/l[j-2]-1)
    vol20=v[j-21:j-1]; vz=(v[j-1]-vol20.mean())/(vol20.std()+1e-12)
    # structure intact diagnostics from causal dataset features
    m3_ok=(float(r.m3_e5e20)>0 and float(r.m3_e20_slope3)>=0)
    m5_ok=(float(r.m5_e5e20)>0 and float(r.m5_e20_slope3)>=0)
    both_ok=m3_ok and m5_ok
    future3=c[j+2]/o[j]-1
    lifecycle=sim(j,o,h,l,c)
    rows.append(dict(gate_fold=int(r.gate_fold),quality=float(r.gate_quality),r3=r3,r1=r1,close_loc=close_loc,lower_wick=lower_wick,body=body,recovery_low=rec_from_low,low_vs_prevlow=low_vs_prevlow,vol_z=vz,m3_ok=m3_ok,m5_ok=m5_ok,both_ok=both_ok,m3_buy=float(r.m3_buy_ratio),m5_buy=float(r.m5_buy_ratio),m3_imb=float(r.m3_imbalance),m5_imb=float(r.m5_imbalance),future3=future3,lifecycle=lifecycle))
z=pd.DataFrame(rows)
print("===== D8 DEEP PULLBACK BASE =====")
print("N=",len(z),"FUT3_BPS=",round(z.future3.mean()*1e4,4),"LIFECYCLE_NET_BPS=",round(z.lifecycle.mean()*1e4,4))
# Fixed diagnostic hypotheses, no optimization
conds={
"ALL":np.ones(len(z),bool),
"RECOVERY_CLOSELOC_GE50":z.close_loc>=.50,
"RECOVERY_CLOSELOC_GE67":z.close_loc>=.67,
"LOWER_WICK_GE25":z.lower_wick>=.25,
"RECOVERY_LOW_GE10BPS":z.recovery_low>=.0010,
"RECOVERY_LOW_GE15BPS":z.recovery_low>=.0015,
"BOTH_MTF_TREND_OK":z.both_ok,
"M5_TREND_OK":z.m5_ok,
"M3_TREND_OK":z.m3_ok,
"VOL_Z_GE0":z.vol_z>=0,
"VOL_Z_GE1":z.vol_z>=1,
"BUY_BOTH_GE50":(z.m3_buy>=.50)&(z.m5_buy>=.50),
"IMB_BOTH_POS":(z.m3_imb>0)&(z.m5_imb>0),
"REC50_AND_M5_OK":(z.close_loc>=.50)&z.m5_ok,
"WICK25_AND_M5_OK":(z.lower_wick>=.25)&z.m5_ok,
"REC50_BUY_BOTH":(z.close_loc>=.50)&(z.m3_buy>=.50)&(z.m5_buy>=.50),
}
out=[]
for name,m in conds.items():
    q=z[m]
    if len(q)==0: continue
    pos=q.lifecycle[q.lifecycle>0].sum(); neg=-q.lifecycle[q.lifecycle<0].sum(); pf=pos/neg if neg>0 else np.inf
    folds=q.groupby("gate_fold").lifecycle.mean()*1e4
    out.append(dict(rule=name,n=len(q),coverage_pct=len(q)/len(z)*100,future3_bps=q.future3.mean()*1e4,lifecycle_net_bps=q.lifecycle.mean()*1e4,pf=pf,win_pct=(q.lifecycle>0).mean()*100,positive_folds=int((folds>0).sum()),worst_fold_bps=folds.min()))
res=pd.DataFrame(out).sort_values("lifecycle_net_bps",ascending=False)
print("\n===== FIXED STRUCTURE DIAGNOSTICS =====")
print(res.round(4).to_string(index=False))
print("\n===== FEATURE MEDIANS BY LIFECYCLE SIGN =====")
for sign,m in [("WIN",z.lifecycle>0),("LOSS",z.lifecycle<=0)]:
    q=z[m]; print(sign,"n=",len(q),{k:round(q[k].median(),5) for k in ["close_loc","lower_wick","recovery_low","low_vs_prevlow","vol_z","m3_buy","m5_buy","m3_imb","m5_imb"]})
res.to_csv(OUT,index=False)
print("OUTPUT=",OUT)
