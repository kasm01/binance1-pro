#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd

ROOT=Path(__file__).resolve().parents[2]
CAND=ROOT/"research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz"
CTX=ROOT/"research/results/ALT_MARKET_CONTEXT_3M.csv"
D1=ROOT/"data/offline_cache/NEARUSDT_1m_360d.csv"
OUT=ROOT/"research/results/NEAR_REGIME_FOLD_DIFFERENCES.csv"
MAKER=.0002; TAKER=.0005
CFG=dict(early_window=5,early_mfe=.0010,early_mae=.0025,arm=.0020,giveback=.0008,hard_stop=.0050,max_hold=10)

def down_exit(op,lo,thr):
    if op<=thr:return op
    if lo<=thr:return thr
    return None

def life_from_open(idx,entry,exit_fee,max_hold=10):
    mx=-np.inf; mn=np.inf; armed=False; trail=None
    for step in range(max_hold):
        j=idx+step; op=o[j]/entry-1; hi=h[j]/entry-1; lo=l[j]/entry-1; cl=c[j]/entry-1
        if trail is not None:
            x=down_exit(op,lo,trail)
            if x is not None:return x-exit_fee
        x=down_exit(op,lo,-CFG["hard_stop"])
        if x is not None:return x-exit_fee
        mx=max(mx,hi); mn=min(mn,lo)
        if step+1==CFG["early_window"] and mx<CFG["early_mfe"] and mn<=-CFG["early_mae"]: return cl-exit_fee
        if mx>=CFG["arm"]:armed=True
        if armed:trail=mx-CFG["giveback"]
    return c[idx+max_hold-1]/entry-1-exit_fee

def life_after_fill(fill_idx,entry,exit_fee):
    if l[fill_idx]/entry-1<=-CFG["hard_stop"]: return -CFG["hard_stop"]-exit_fee
    return life_from_open(fill_idx+1,entry,exit_fee,max_hold=CFG["max_hold"]-1)

def run_mkr3w1(j):
    limit=o[j]*(1-3/1e4)
    if l[j]<=limit: return life_after_fill(j,limit,TAKER)-MAKER,1
    k=j+1; return life_from_open(k,o[k],TAKER)-TAKER,0

ds=pd.read_csv(CAND); d1=pd.read_csv(D1); ctx=pd.read_csv(CTX)
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
ds["entry_idx"]=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side="left")
# merge latest causal alt context timestamp <= feature_close_time
ctx_time=[x for x in ctx.columns if "time" in x.lower()]
ct=ctx_time[0]
ctx=ctx.sort_values(ct)
ds=ds.sort_values("feature_close_time")
ds=pd.merge_asof(ds,ctx,left_on="feature_close_time",right_on=ct,direction="backward",suffixes=("","_ctx"))
rows=[]
for test_fold in [2,3,4]:
    cal=ds[ds.gate_fold<test_fold]
    q70,q80=cal.gate_quality.quantile([.70,.80]).tolist()
    test=ds[ds.gate_fold==test_fold]
    for _,r in test.iterrows():
        q=float(r.gate_quality); j=int(r.entry_idx)
        if not(q70<=q<q80) or j<25 or j+12>=len(o): continue
        r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1; recovery=c[j-1]/l[j-1]-1
        if not(((r3<=-.003) or (r1<=-.002)) and recovery<.001): continue
        ret,fill=run_mkr3w1(j)
        ts=pd.to_datetime(int(r.entry_open_time),unit="ms",utc=True)
        rec=dict(fold=test_fold,ret_bps=ret*1e4,maker_fill=fill,hour=ts.hour,
                 m3_atr=float(r.m3_atr14),m5_atr=float(r.m5_atr14),m15_atr=float(r.m15_atr14),
                 m3_trend=float(r.m3_e5e20),m5_trend=float(r.m5_e5e20),m15_trend=float(r.m15_e5e20),
                 m3_slope=float(r.m3_e20_slope3),m5_slope=float(r.m5_e20_slope3),m15_slope=float(r.m15_e20_slope3),
                 m3_buy=float(r.m3_buy_ratio),m5_buy=float(r.m5_buy_ratio),m15_buy=float(r.m15_buy_ratio),
                 m3_volz=float(r.m3_vol_z20),m5_volz=float(r.m5_vol_z20),
                 pull3=r3,pull1=r1,recovery=recovery,quality=q)
        for col in ctx.columns:
            if col==ct or col in rec: continue
            if col in r.index and isinstance(r[col],(int,float,np.integer,np.floating)):
                rec[col]=float(r[col])
        rows.append(rec)
z=pd.DataFrame(rows)
print("N=",len(z),"fold_counts=",z.fold.value_counts().sort_index().to_dict())
# compact fold medians + economics
feature_candidates=[c for c in ["m3_atr","m5_atr","m15_atr","m3_trend","m5_trend","m3_slope","m5_slope","m3_buy","m5_buy","m3_volz","m5_volz","pull3","pull1","recovery","quality"] if c in z]
# add selected market context cols
for c0 in [c for c in z.columns if any(k in c.lower() for k in ["breadth","peer_mean","peer_median","dispersion","near_rel","trend_slope"])][:12]:
    if c0 not in feature_candidates: feature_candidates.append(c0)
for f,g in z.groupby("fold"):
    pos=g.ret_bps[g.ret_bps>0].sum(); neg=-g.ret_bps[g.ret_bps<0].sum(); pf=pos/neg if neg>0 else np.inf
    print("\nFOLD",f,"n",len(g),"net_bps",round(g.ret_bps.mean(),4),"pf",round(pf,4),"fill%",round(g.maker_fill.mean()*100,2))
    print(g[feature_candidates].median().round(6).to_string())
# effect-size style: fold3 vs bad folds2+4
if set(z.fold.unique())>={2,3,4}:
    good=z[z.fold==3]; bad=z[z.fold.isin([2,4])]
    comp=[]
    for col in feature_candidates:
        a=good[col].dropna(); b=bad[col].dropna()
        if len(a)<3 or len(b)<3: continue
        scale=np.nanmedian(np.abs(pd.concat([a,b])-np.nanmedian(pd.concat([a,b]))))+1e-12
        comp.append((col,float(a.median()),float(b.median()),float((a.median()-b.median())/scale)))
    comp=sorted(comp,key=lambda x:abs(x[3]),reverse=True)
    print("\n===== FOLD3 VS FOLD2+4 MEDIAN DIFFERENCES =====")
    for x in comp[:20]: print(x[0],"good",round(x[1],6),"bad",round(x[2],6),"robust_diff",round(x[3],3))
z.to_csv(OUT,index=False)
print("OUTPUT=",OUT)
