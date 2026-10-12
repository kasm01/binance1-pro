#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz"
D1 = ROOT / "data/offline_cache/NEARUSDT_1m_360d.csv"
OUT = ROOT / "research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz"
SUMMARY = ROOT / "research/results/NEAR_DUAL_GATE_CANDIDATES_SUMMARY.csv"
TP, SL, FEE, HORIZON = 0.0025, 0.0050, 0.0008, 10
QUANTILES = [0.60, 0.70, 0.80, 0.90]
MIN_VAL_TRADES = 40
FOLDS = [
    (0.50, 0.625, 0.75),
    (0.625, 0.75, 0.8333),
    (0.70, 0.8333, 0.9166),
    (0.75, 0.9166, 1.00),
]

def economics(x):
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return {"n":0,"mean":np.nan,"pf":np.nan,"win":np.nan}
    pos = x[x > 0].sum(); neg = -x[x < 0].sum()
    return {"n":len(x),"mean":float(x.mean()),"pf":float(pos/neg if neg>0 else np.inf),"win":float((x>0).mean()*100)}

def model(seed):
    return HistGradientBoostingClassifier(
        learning_rate=0.05,max_iter=200,max_leaf_nodes=15,
        min_samples_leaf=150,l2_regularization=5.0,
        early_stopping=False,random_state=seed,
    )

ds = pd.read_csv(DATA).sort_values("feature_close_time").reset_index(drop=True)
feature_cols = [c for c in ds.columns if c.startswith(("m3_","m5_","m15_"))]
d1 = pd.read_csv(D1)
ot = d1["open_time"].to_numpy(np.int64)
o = d1["open"].astype(float).to_numpy(); h = d1["high"].astype(float).to_numpy(); l = d1["low"].astype(float).to_numpy(); c = d1["close"].astype(float).to_numpy()
follow=np.zeros(len(ds),int); danger=np.zeros(len(ds),int); econ=np.zeros(len(ds),float)
for i,r in ds.iterrows():
    idx=int(np.searchsorted(ot,int(r["entry_open_time"]),side="left")); entry=float(o[idx]); result="HOLD"
    for k in range(HORIZON):
        j=idx+k
        if l[j]/entry-1.0 <= -SL: result="SL"; break
        if h[j]/entry-1.0 >= TP: result="TP"; break
    if result=="TP": follow[i]=1; econ[i]=TP-FEE
    elif result=="SL": danger[i]=1; econ[i]=-SL-FEE
    else: econ[i]=float(c[idx+HORIZON-1])/entry-1.0-FEE
X=ds[feature_cols].to_numpy(float); n=len(ds)
selected=[]; summary=[]
for fold_no,(train_frac,val_frac,test_frac) in enumerate(FOLDS,1):
    tr_end=int(n*train_frac); va_end=int(n*val_frac); te_end=int(n*test_frac); fit_end=max(tr_end-3,1)
    mf=model(42); md=model(43); mf.fit(X[:fit_end],follow[:fit_end]); md.fit(X[:fit_end],danger[:fit_end])
    qval=mf.predict_proba(X[tr_end:va_end])[:,1]-md.predict_proba(X[tr_end:va_end])[:,1]
    qtest=mf.predict_proba(X[va_end:te_end])[:,1]-md.predict_proba(X[va_end:te_end])[:,1]
    eval_val=econ[tr_end:va_end]; best=None
    for q in QUANTILES:
        cut=float(np.quantile(qval,q)); keep=qval>=cut; ev=economics(eval_val[keep])
        if ev["n"] < MIN_VAL_TRADES: continue
        if best is None or ev["mean"] > best["ev"]["mean"]: best={"q":q,"cut":cut,"ev":ev}
    if best is None: raise SystemExit(f"NO_GATE_FOLD={fold_no}")
    keep=qtest>=best["cut"]
    idxs=np.arange(va_end,te_end)[keep]
    part=ds.iloc[idxs].copy(); part["gate_fold"]=fold_no; part["gate_quality"]=qtest[keep]; part["gate_q"]=best["q"]; part["gate_cut"]=best["cut"]
    selected.append(part)
    ge=economics(econ[idxs]); be=economics(econ[va_end:te_end])
    summary.append({"fold":fold_no,"q":best["q"],"cut":best["cut"],"n":len(idxs),"gate_net_pct":ge["mean"]*100,"gate_pf":ge["pf"],"gate_win_pct":ge["win"],"base_net_pct":be["mean"]*100,"delta_pct":(ge["mean"]-be["mean"])*100})
out=pd.concat(selected,ignore_index=True).sort_values("feature_close_time").reset_index(drop=True)
sumdf=pd.DataFrame(summary)
out.to_csv(OUT,index=False,compression="gzip"); sumdf.to_csv(SUMMARY,index=False)
print("===== OOS DUAL-GATE CANDIDATES =====")
print(sumdf.round(5).to_string(index=False))
print("TOTAL=",len(out),"DUP_TIME=",int(out["feature_close_time"].duplicated().sum()))
weighted=(sumdf.gate_net_pct*sumdf.n).sum()/sumdf.n.sum()
print("WEIGHTED_NET_PCT=",round(weighted,5))
print("OUTPUT=",OUT)
print("DUAL_GATE_CANDIDATES_COMPLETE")
