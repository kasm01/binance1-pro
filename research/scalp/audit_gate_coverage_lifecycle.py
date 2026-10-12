#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/"research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz"
D1=ROOT/"data/offline_cache/NEARUSDT_1m_360d.csv"
OUT=ROOT/"research/results/NEAR_GATE_COVERAGE_LIFECYCLE.csv"
FEE=0.0008
COVERAGES=[1.00,0.50,0.30,0.20,0.10]
# Best prior lifecycle on gated OOS candidates
CFG={"hard_stop":0.0050,"max_hold":10,"early_window":5,"early_mfe":0.0010,"early_mae":0.0025,"arm":0.0020,"giveback":0.0008}

def down_exit(open_ret,low_ret,thr):
    if open_ret<=thr:return open_ret
    if low_ret<=thr:return thr
    return None

def sim(idx,o,h,l,c):
    entry=float(o[idx]); mx=-np.inf; mn=np.inf; armed=False; prior_trail=None
    for k in range(CFG["max_hold"]):
        j=idx+k; op=o[j]/entry-1; hi=h[j]/entry-1; lo=l[j]/entry-1; cl=c[j]/entry-1
        if prior_trail is not None:
            x=down_exit(op,lo,prior_trail)
            if x is not None:return x-FEE,k+1,"GIVEBACK"
        x=down_exit(op,lo,-CFG["hard_stop"])
        if x is not None:return x-FEE,k+1,"HARD_STOP"
        mx=max(mx,hi); mn=min(mn,lo)
        if (k+1)==CFG["early_window"] and mx<CFG["early_mfe"] and mn<=-CFG["early_mae"]:
            return cl-FEE,k+1,"EARLY_EXIT"
        if mx>=CFG["arm"]: armed=True
        if armed: prior_trail=mx-CFG["giveback"]
    return c[idx+CFG["max_hold"]-1]/entry-1-FEE,CFG["max_hold"],"TIME_EXIT"

def stats(x):
    x=np.asarray(x,float); pos=x[x>0].sum(); neg=-x[x<0].sum()
    return {"n":len(x),"net_pct":x.mean()*100,"pf":pos/neg if neg>0 else np.inf,"win_pct":(x>0).mean()*100,"avg_win_pct":x[x>0].mean()*100 if (x>0).any() else np.nan,"avg_loss_pct":x[x<0].mean()*100 if (x<0).any() else np.nan,"tail_m030_pct":(x<=-0.003).mean()*100,"tail_m050_pct":(x<=-0.005).mean()*100}

cand=pd.read_csv(CAND).sort_values(["gate_fold","feature_close_time"]).reset_index(drop=True)
d1=pd.read_csv(D1); ot=d1.open_time.to_numpy(np.int64); o=d1.open.astype(float).to_numpy(); h=d1.high.astype(float).to_numpy(); l=d1.low.astype(float).to_numpy(); c=d1.close.astype(float).to_numpy()
idx=np.searchsorted(ot,cand.entry_open_time.to_numpy(np.int64),side="left")
rets=np.empty(len(cand)); reasons=[]; durs=np.empty(len(cand),int)
for i,j in enumerate(idx):
    r,d,reason=sim(int(j),o,h,l,c); rets[i]=r; durs[i]=d; reasons.append(reason)
cand["life_ret"]=rets; cand["life_reason"]=reasons; cand["life_dur"]=durs
rows=[]
for cov in COVERAGES:
    parts=[]
    fold_rows=[]
    for fold,g in cand.groupby("gate_fold",sort=True):
        # Rank inside fold to avoid cross-fold score calibration drift
        k=max(1,int(np.ceil(len(g)*cov)))
        sel=g.nlargest(k,"gate_quality")
        s=stats(sel.life_ret.to_numpy()); s.update({"coverage":cov,"fold":int(fold),"selected":len(sel),"fold_total":len(g)})
        fold_rows.append(s); parts.append(sel)
    allsel=pd.concat(parts,ignore_index=True)
    s=stats(allsel.life_ret.to_numpy())
    posfolds=sum(fr["net_pct"]>0 for fr in fold_rows)
    row={"coverage":cov,"n":s["n"],"net_pct":s["net_pct"],"pf":s["pf"],"win_pct":s["win_pct"],"avg_win_pct":s["avg_win_pct"],"avg_loss_pct":s["avg_loss_pct"],"tail_m030_pct":s["tail_m030_pct"],"tail_m050_pct":s["tail_m050_pct"],"positive_folds":posfolds}
    for fr in fold_rows:
        fno = int(fr["fold"])
        row[f"fold{fno}_net_pct"] = fr["net_pct"]
        row[f"fold{fno}_n"] = fr["selected"]
    rows.append(row)
res=pd.DataFrame(rows)
res.to_csv(OUT,index=False)
print("===== GATE COVERAGE + BEST LIFECYCLE =====")
print(res.round(5).to_string(index=False))
print("\nMONOTONIC_NET_IMPROVEMENT=",bool((res.net_pct.diff().dropna()>0).all()))
print("POSITIVE_ANY=",bool((res.net_pct>0).any()))
print("PF_GT1_ANY=",bool((res.pf>1).any()))
print("OUTPUT=",OUT)
print("GATE_COVERAGE_LIFECYCLE_COMPLETE")
