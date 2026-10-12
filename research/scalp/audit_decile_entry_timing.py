#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CAND = ROOT / "research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz"
D1 = ROOT / "data/offline_cache/NEARUSDT_1m_360d.csv"
OUT = ROOT / "research/results/NEAR_DECILE_ENTRY_TIMING.csv"

cand = pd.read_csv(CAND).sort_values("feature_close_time").reset_index(drop=True)
d1 = pd.read_csv(D1)
ot = d1["open_time"].to_numpy(np.int64)
o = d1["open"].astype(float).to_numpy()
h = d1["high"].astype(float).to_numpy()
l = d1["low"].astype(float).to_numpy()
c = d1["close"].astype(float).to_numpy()

# Global OOS deciles by gate quality.
cand["decile"] = pd.qcut(cand["gate_quality"], 10, labels=False, duplicates="drop") + 1

rows=[]
for dec in [7,8,9,10]:
    sub = cand[cand.decile == dec]
    rec=[]
    for _,r in sub.iterrows():
        idx = int(np.searchsorted(ot, int(r["entry_open_time"]), side="left"))
        if idx < 3 or idx >= len(d1):
            continue
        entry = float(o[idx])
        prev1_o,prev1_h,prev1_l,prev1_c = o[idx-1],h[idx-1],l[idx-1],c[idx-1]
        prev2_c,prev3_c = c[idx-2],c[idx-3]
        r1 = prev1_c/prev2_c - 1.0
        r2 = prev2_c/prev3_c - 1.0
        prev_body = (prev1_c-prev1_o)/prev1_o
        prev_range = max(prev1_h-prev1_l, 1e-12)
        prev_close_loc = (prev1_c-prev1_l)/prev_range
        entry_vs_prev_close = entry/prev1_c - 1.0
        entry_vs_prev_high = entry/prev1_h - 1.0
        local3_high = max(h[idx-1],h[idx-2],h[idx-3])
        local3_low = min(l[idx-1],l[idx-2],l[idx-3])
        entry_vs_3h = entry/local3_high - 1.0
        three_ret = prev1_c/c[idx-3]-1.0
        accel = r1-r2
        # Proxy flags for late/chased entry at decision boundary.
        spike_prev = (prev_body >= 0.0015) and (prev_close_loc >= 0.70)
        extended_3m = three_ret >= 0.0025
        near_local_high = entry_vs_3h >= -0.0005
        decelerating = accel < 0
        gap_up = entry_vs_prev_close >= 0.0005
        rec.append({
            "r1_bps":r1*1e4,"r2_bps":r2*1e4,"accel_bps":accel*1e4,
            "prev_body_bps":prev_body*1e4,"prev_close_loc":prev_close_loc,
            "entry_vs_prev_close_bps":entry_vs_prev_close*1e4,
            "entry_vs_prev_high_bps":entry_vs_prev_high*1e4,
            "entry_vs_3h_bps":entry_vs_3h*1e4,"three_ret_bps":three_ret*1e4,
            "spike_prev":spike_prev,"extended_3m":extended_3m,
            "near_local_high":near_local_high,"decelerating":decelerating,
            "gap_up":gap_up,
        })
    z=pd.DataFrame(rec)
    row={"decile":dec,"n":len(z)}
    for col in ["r1_bps","accel_bps","prev_body_bps","prev_close_loc","entry_vs_prev_close_bps","entry_vs_prev_high_bps","entry_vs_3h_bps","three_ret_bps"]:
        row[f"{col}_mean"]=z[col].mean(); row[f"{col}_median"]=z[col].median()
    for col in ["spike_prev","extended_3m","near_local_high","decelerating","gap_up"]:
        row[f"{col}_pct"]=z[col].mean()*100
    rows.append(row)

res=pd.DataFrame(rows)
print("===== DECILE 7-10 ENTRY TIMING / CHASE AUDIT =====")
print(res.round(4).to_string(index=False))
res.to_csv(OUT,index=False)
print("OUTPUT=",OUT)
