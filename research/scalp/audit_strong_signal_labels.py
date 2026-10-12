#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

DATASET = (
    ROOT
    / "research/results"
    / "NEAR_STRONG_SIGNAL_DATASET.csv.gz"
)

D1 = (
    ROOT
    / "data/offline_cache"
    / "NEARUSDT_1m_360d.csv"
)

OUT = (
    ROOT
    / "research/results"
    / "NEAR_STRONG_SIGNAL_LABEL_AUDIT.csv"
)

ds = pd.read_csv(DATASET)
d1 = pd.read_csv(D1)

ot = d1["open_time"].to_numpy(dtype=np.int64)
o = d1["open"].astype(float).to_numpy()
h = d1["high"].astype(float).to_numpy()
l = d1["low"].astype(float).to_numpy()

# Predefined first-hit contracts.
CONTRACTS = [
    ("TP15_SL30", 0.0015, 0.0030),
    ("TP20_SL30", 0.0020, 0.0030),
    ("TP25_SL30", 0.0025, 0.0030),
    ("TP20_SL50", 0.0020, 0.0050),
    ("TP25_SL50", 0.0025, 0.0050),
]

HORIZON = 10

rows = []

for _, r in ds.iterrows():

    entry_time = int(r["entry_open_time"])

    idx = int(
        np.searchsorted(
            ot,
            entry_time,
            side="left",
        )
    )

    if idx >= len(d1):
        continue

    entry = float(o[idx])

    if entry <= 0:
        continue

    row = {
        "feature_close_time":
            int(r["feature_close_time"]),

        "entry_open_time":
            entry_time,
    }

    for name, tp, sl in CONTRACTS:

        result = "HOLD"
        hit_minute = HORIZON

        for k in range(HORIZON):

            j = idx + k

            if j >= len(d1):
                break

            # Conservative ordering:
            # if both happen in same 1m candle,
            # count SL first.
            sl_hit = (
                l[j] / entry - 1.0
                <= -sl
            )

            tp_hit = (
                h[j] / entry - 1.0
                >= tp
            )

            if sl_hit:
                result = "SL"
                hit_minute = k + 1
                break

            if tp_hit:
                result = "TP"
                hit_minute = k + 1
                break

        row[f"{name}_result"] = result
        row[f"{name}_minute"] = hit_minute

    rows.append(row)

out = pd.DataFrame(rows)

print("===== FIRST HIT LABEL AUDIT =====")
print("ROWS=", len(out))

summary_rows = []

for name, tp, sl in CONTRACTS:

    col = f"{name}_result"

    counts = (
        out[col]
        .value_counts()
    )

    tp_n = int(counts.get("TP", 0))
    sl_n = int(counts.get("SL", 0))
    hold_n = int(counts.get("HOLD", 0))

    total = len(out)

    tp_rate = tp_n / total
    sl_rate = sl_n / total
    hold_rate = hold_n / total

    decided = tp_n + sl_n

    tp_first_rate = (
        tp_n / decided
        if decided
        else np.nan
    )

    summary_rows.append({
        "contract": name,
        "tp_pct": tp * 100,
        "sl_pct": sl * 100,
        "total": total,
        "tp_n": tp_n,
        "sl_n": sl_n,
        "hold_n": hold_n,
        "tp_rate": tp_rate,
        "sl_rate": sl_rate,
        "hold_rate": hold_rate,
        "tp_first_rate":
            tp_first_rate,
    })

summary = pd.DataFrame(summary_rows)

print()
print(
    summary.round(5)
    .to_string(index=False)
)

print()
print("===== DANGER LABELS =====")

danger = pd.DataFrame({
    "danger_mae5_30":
        ds["mae_5m_pct"] <= -0.30,

    "danger_mae10_50":
        ds["mae_10m_pct"] <= -0.50,

    "danger_mae10_100":
        ds["mae_10m_pct"] <= -1.00,
})

for c in danger.columns:
    print(
        c,
        "rate=",
        round(
            danger[c].mean(),
            5,
        ),
        "n=",
        int(danger[c].sum()),
    )

print()
print("===== FOLLOW LABELS =====")

follow = pd.DataFrame({
    "follow_A":
        (
            (ds["mfe_5m_pct"] >= 0.15)
            & (ds["mae_5m_pct"] > -0.25)
        ),

    "follow_B":
        (
            (ds["mfe_5m_pct"] >= 0.20)
            & (ds["mae_5m_pct"] > -0.25)
        ),

    "follow_C":
        (
            (ds["mfe_10m_pct"] >= 0.25)
            & (ds["mae_10m_pct"] > -0.30)
        ),
})

for c in follow.columns:
    print(
        c,
        "rate=",
        round(
            follow[c].mean(),
            5,
        ),
        "n=",
        int(follow[c].sum()),
    )

summary.to_csv(
    OUT,
    index=False,
)

print()
print("OUTPUT=", OUT)
print("STRONG_SIGNAL_LABEL_AUDIT_COMPLETE")
