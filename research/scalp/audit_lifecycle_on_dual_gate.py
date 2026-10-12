#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz"
D1 = ROOT / "data/offline_cache/NEARUSDT_1m_360d.csv"
OUT = ROOT / "research/results/NEAR_LIFECYCLE_DUAL_GATE.csv"
FEE = 0.0008
MAX_PATH = 10

ds = pd.read_csv(DATA).sort_values("feature_close_time").reset_index(drop=True)
d1 = pd.read_csv(D1)
ot = d1["open_time"].to_numpy(np.int64)
o = d1["open"].astype(float).to_numpy()
h = d1["high"].astype(float).to_numpy()
l = d1["low"].astype(float).to_numpy()
c = d1["close"].astype(float).to_numpy()

variants = []
def add(name,family,fixed_tp=None,hard_stop=.005,max_hold=10,early_window=None,early_mfe=None,early_mae=None,arm=None,giveback=None):
    variants.append(dict(name=name,family=family,fixed_tp=fixed_tp,hard_stop=hard_stop,max_hold=max_hold,early_window=early_window,early_mfe=early_mfe,early_mae=early_mae,arm=arm,giveback=giveback))

add("BASE_TP25_SL50_10M","BASE",fixed_tp=.0025,hard_stop=.005,max_hold=10)
for ew,mfe,mae in [(2,.0005,.0015),(2,.0005,.0020),(3,.0005,.0015),(3,.0005,.0020),(3,.0010,.0020),(3,.0010,.0025),(5,.0010,.0020),(5,.0010,.0025)]:
    add(f"EARLY_{ew}M_MFE{mfe*100:.2f}_MAE{mae*100:.2f}","EARLY",fixed_tp=.0025,hard_stop=.005,max_hold=10,early_window=ew,early_mfe=mfe,early_mae=mae)
for arm,gb,hs,mh in [(.0010,.0005,.005,10),(.0010,.0008,.005,10),(.0015,.0005,.005,10),(.0015,.0008,.005,10),(.0015,.0010,.005,10),(.0020,.0008,.005,10),(.0020,.0010,.005,10)]:
    add(f"RUN_ARM{arm*100:.2f}_GB{gb*100:.2f}_SL{hs*100:.2f}_{mh}M","RUNNER",hard_stop=hs,max_hold=mh,arm=arm,giveback=gb)
for ew,mfe,mae,arm,gb,hs in [(2,.0005,.0015,.0010,.0005,.004),(2,.0005,.0020,.0015,.0005,.004),(3,.0005,.0015,.0010,.0005,.004),(3,.0005,.0020,.0015,.0005,.004),(3,.0010,.0020,.0015,.0008,.004),(3,.0010,.0025,.0015,.0008,.005),(5,.0010,.0020,.0015,.0008,.004),(5,.0010,.0025,.0020,.0008,.005)]:
    add(f"COMBO_{ew}M_MFE{mfe*100:.2f}_MAE{mae*100:.2f}_ARM{arm*100:.2f}_GB{gb*100:.2f}_SL{hs*100:.2f}","EARLY_RUNNER",hard_stop=hs,max_hold=10,early_window=ew,early_mfe=mfe,early_mae=mae,arm=arm,giveback=gb)

entry_idx = np.searchsorted(ot, ds["entry_open_time"].to_numpy(np.int64), side="left")
valid = (entry_idx >= 0) & (entry_idx + MAX_PATH <= len(d1))
ds = ds.loc[valid].reset_index(drop=True)
entry_idx = entry_idx[valid]

def down_exit(open_ret,low_ret,thr):
    if open_ret <= thr: return open_ret
    if low_ret <= thr: return thr
    return None

def up_exit(open_ret,high_ret,thr):
    if open_ret >= thr: return open_ret
    if high_ret >= thr: return thr
    return None

def simulate(idx,cfg):
    entry=float(o[idx]); max_seen=-np.inf; min_seen=np.inf; armed=False; prior_trail=None
    for k in range(int(cfg["max_hold"])):
        j=idx+k
        op=o[j]/entry-1.; hi=h[j]/entry-1.; lo=l[j]/entry-1.; cl=c[j]/entry-1.
        if prior_trail is not None:
            x=down_exit(op,lo,prior_trail)
            if x is not None: return x-FEE,k+1,"GIVEBACK"
        x=down_exit(op,lo,-float(cfg["hard_stop"]))
        if x is not None: return x-FEE,k+1,"HARD_STOP"
        if cfg["fixed_tp"] is not None:
            x=up_exit(op,hi,float(cfg["fixed_tp"]))
            if x is not None: return x-FEE,k+1,"FIXED_TP"
        max_seen=max(max_seen,hi); min_seen=min(min_seen,lo)
        if cfg["early_window"] is not None and k+1==int(cfg["early_window"]) and max_seen<float(cfg["early_mfe"]) and min_seen<=-float(cfg["early_mae"]):
            return cl-FEE,k+1,"EARLY_EXIT"
        if cfg["arm"] is not None:
            if max_seen >= float(cfg["arm"]): armed=True
            if armed: prior_trail=max_seen-float(cfg["giveback"])
    return c[idx+int(cfg["max_hold"])-1]/entry-1.-FEE,int(cfg["max_hold"]),"TIME_EXIT"

print("===== DUAL-GATE LIFECYCLE INPUT =====")
print("CANDIDATES=",len(ds),"VARIANTS=",len(variants),"FOLDS=",sorted(ds.gate_fold.unique().tolist()))
rows=[]
for vi,cfg in enumerate(variants,1):
    rets=np.empty(len(entry_idx)); dur=np.empty(len(entry_idx),int); reasons=[]
    for i,idx in enumerate(entry_idx):
        r,d,reason=simulate(int(idx),cfg); rets[i]=r; dur[i]=d; reasons.append(reason)
    pos=rets[rets>0]; neg=rets[rets<0]; gp=pos.sum(); gl=-neg.sum(); pf=gp/gl if gl>0 else np.inf
    fold_means=[]; fold_ns=[]
    gf=ds["gate_fold"].to_numpy(int)
    for f in (1,2,3,4):
        m=gf==f; fold_ns.append(int(m.sum())); fold_means.append(float(rets[m].mean()) if m.any() else np.nan)
    row=dict(name=cfg["name"],family=cfg["family"],n=len(rets),net_mean_pct=rets.mean()*100,win_pct=(rets>0).mean()*100,profit_factor=pf,avg_win_pct=(pos.mean()*100 if len(pos) else np.nan),avg_loss_pct=(neg.mean()*100 if len(neg) else np.nan),avg_duration_min=dur.mean(),tail_le_m030_pct=(rets<=-.003).mean()*100,tail_le_m050_pct=(rets<=-.005).mean()*100,positive_folds=sum(np.isfinite(x) and x>0 for x in fold_means),fold1_pct=fold_means[0]*100,fold2_pct=fold_means[1]*100,fold3_pct=fold_means[2]*100,fold4_pct=fold_means[3]*100)
    rows.append(row)
    print(f"[{vi:02d}/{len(variants):02d}] {cfg['name']} net={row['net_mean_pct']:.5f}% PF={row['profit_factor']:.4f} folds={row['positive_folds']}/4")
res=pd.DataFrame(rows)
base=float(res.loc[res.name=="BASE_TP25_SL50_10M","net_mean_pct"].iloc[0]); res["delta_vs_base_pct"]=res.net_mean_pct-base
res=res.sort_values(["net_mean_pct","positive_folds","profit_factor"],ascending=[False,False,False]).reset_index(drop=True)
show=["name","family","net_mean_pct","delta_vs_base_pct","profit_factor","win_pct","avg_win_pct","avg_loss_pct","avg_duration_min","tail_le_m030_pct","tail_le_m050_pct","positive_folds","fold1_pct","fold2_pct","fold3_pct","fold4_pct"]
print("\n===== TOP 15 =====")
print(res[show].head(15).round(5).to_string(index=False))
print("\n===== BEST BY FAMILY =====")
print(res.sort_values("net_mean_pct",ascending=False).groupby("family",as_index=False).first()[["family","name","net_mean_pct","delta_vs_base_pct","profit_factor","positive_folds","tail_le_m030_pct","tail_le_m050_pct"]].round(5).to_string(index=False))
print("\n===== ROBUSTNESS =====")
print("POSITIVE_EXPECTANCY_VARIANTS=",int((res.net_mean_pct>0).sum()),"/",len(res))
print("PF_GT1_VARIANTS=",int((res.profit_factor>1).sum()),"/",len(res))
print("POSITIVE_3PLUS_FOLDS=",int((res.positive_folds>=3).sum()),"/",len(res))
res.to_csv(OUT,index=False)
print("OUTPUT=",OUT)
print("LIFECYCLE_DUAL_GATE_COMPLETE")