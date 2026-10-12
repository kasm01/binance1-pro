#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"research/results/NEAR_REGIME_FOLD_DIFFERENCES.csv"
OUT=ROOT/"research/results/NEAR_NESTED_REGIME_GATE.csv"
z=pd.read_csv(SRC)
# fixed, interpretable rules; thresholds learned only from earlier folds
FEATURES=["m15_atr","m5_atr","m3_slope","m5_slope","near_rel_ret3","near_rel_ret2","m5_volz"]
rows=[]
for test_fold in [3,4]:
    cal=z[z.fold<test_fold].copy(); test=z[z.fold==test_fold].copy()
    if len(cal)<20 or len(test)==0: continue
    med={c:cal[c].median() for c in FEATURES}
    rules={
      "ALL":lambda d:np.ones(len(d),dtype=bool),
      "LOW_M15_ATR":lambda d:d.m15_atr<=med["m15_atr"],
      "REL_WEAK3":lambda d:d.near_rel_ret3<=med["near_rel_ret3"],
      "NEG_M3_SLOPE":lambda d:d.m3_slope<=med["m3_slope"],
      "HIGH_M5_VOLZ":lambda d:d.m5_volz>=med["m5_volz"],
      "LOWATR_RELWEAK":lambda d:(d.m15_atr<=med["m15_atr"])&(d.near_rel_ret3<=med["near_rel_ret3"]),
      "RELWEAK_NEGSLOPE":lambda d:(d.near_rel_ret3<=med["near_rel_ret3"])&(d.m3_slope<=med["m3_slope"]),
      "LOWATR_HIGHVOL":lambda d:(d.m15_atr<=med["m15_atr"])&(d.m5_volz>=med["m5_volz"]),
    }
    per=[]
    for name,fn in rules.items():
        m=fn(cal); q=cal[m]
        if len(q)<10: continue
        pos=q.ret_bps[q.ret_bps>0].sum(); neg=-q.ret_bps[q.ret_bps<0].sum(); pf=pos/neg if neg>0 else np.inf
        per.append((name,len(q),q.ret_bps.mean(),pf))
    best=max(per,key=lambda x:x[2])
    name=best[0]; tq=test[rules[name](test)]
    pos=tq.ret_bps[tq.ret_bps>0].sum(); neg=-tq.ret_bps[tq.ret_bps<0].sum(); tpf=pos/neg if neg>0 else (np.inf if len(tq) else np.nan)
    rows.append(dict(test_fold=test_fold,cal_n=len(cal),test_n=len(test),selected=name,cal_sel_n=best[1],cal_net_bps=best[2],cal_pf=best[3],test_sel_n=len(tq),test_coverage_pct=100*len(tq)/len(test),test_net_bps=tq.ret_bps.mean() if len(tq) else np.nan,test_pf=tpf))
    print("\nTEST_FOLD",test_fold,"thresholds",{k:round(v,6) for k,v in med.items()})
    print("CAL RULES",sorted(per,key=lambda x:x[2],reverse=True))
    print("SELECT",name,"TEST_N",len(tq),"TEST_NET",round(tq.ret_bps.mean(),4) if len(tq) else None,"TEST_PF",round(tpf,4) if np.isfinite(tpf) else tpf)
res=pd.DataFrame(rows)
print("\n===== NESTED REGIME GATE =====")
print(res.round(4).to_string(index=False))
if len(res):
    v=res[res.test_sel_n>0]
    if len(v): print("WEIGHTED_TEST_NET_BPS=",round(np.average(v.test_net_bps,weights=v.test_sel_n),4),"TOTAL_N=",int(v.test_sel_n.sum()),"POS_FOLDS=",int((v.test_net_bps>0).sum()),"/",len(v))
res.to_csv(OUT,index=False)
print("OUTPUT=",OUT)
