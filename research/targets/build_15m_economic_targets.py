#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SRC = (
    ROOT
    / "data/offline_cache"
    / "NEARUSDT_15m_360d.csv"
)

DST = (
    ROOT
    / "research/results"
    / "NEAR_15M_ECONOMIC_TARGETS.csv"
)

HORIZON = 4
FEE = 0.0008
MAE_LAMBDA = 0.50

df = pd.read_csv(SRC)

df = (
    df.sort_values("open_time")
    .reset_index(drop=True)
)

o = df["open"].astype(float).to_numpy()
h = df["high"].astype(float).to_numpy()
l = df["low"].astype(float).to_numpy()
c = df["close"].astype(float).to_numpy()

open_time = df["open_time"].to_numpy(dtype=np.int64)
close_time = df["close_time"].to_numpy(dtype=np.int64)

rows = []

# Feature at i is known only after bar i closes.
# Earliest executable entry is next bar open: i+1.
# Horizon covers bars i+1 ... i+HORIZON.
for i in range(
    0,
    len(df) - HORIZON
):
    entry_idx = i + 1
    exit_idx = i + HORIZON

    entry = float(o[entry_idx])

    if not np.isfinite(entry) or entry <= 0:
        continue

    future_high = float(
        np.max(
            h[
                entry_idx:
                exit_idx + 1
            ]
        )
    )

    future_low = float(
        np.min(
            l[
                entry_idx:
                exit_idx + 1
            ]
        )
    )

    exit_price = float(
        c[exit_idx]
    )

    gross_return = (
        exit_price / entry - 1.0
    )

    net_return = (
        gross_return - FEE
    )

    mfe = (
        future_high / entry - 1.0
    )

    mae = (
        future_low / entry - 1.0
    )

    quality = (
        mfe
        - MAE_LAMBDA * abs(mae)
        - FEE
    )

    rows.append({
        "feature_open_time":
            int(open_time[i]),

        "feature_close_time":
            int(close_time[i]),

        "entry_open_time":
            int(open_time[entry_idx]),

        "exit_close_time":
            int(close_time[exit_idx]),

        "entry_price":
            entry,

        "exit_price":
            exit_price,

        "gross_return":
            gross_return,

        "net_return":
            net_return,

        "net_return_pct":
            net_return * 100.0,

        "mfe":
            mfe,

        "mfe_pct":
            mfe * 100.0,

        "mae":
            mae,

        "mae_pct":
            mae * 100.0,

        "quality":
            quality,

        "quality_pct":
            quality * 100.0,

        "positive_after_fee":
            int(net_return > 0.0),
    })

out = pd.DataFrame(rows)

print("===== ECONOMIC TARGET BUILD =====")

print(
    "SOURCE_ROWS=",
    len(df),
)

print(
    "TARGET_ROWS=",
    len(out),
)

print(
    "DUP_FEATURE_TIME=",
    int(
        out["feature_close_time"]
        .duplicated()
        .sum()
    ),
)

print(
    "NAN_TOTAL=",
    int(
        out.isna()
        .sum()
        .sum()
    ),
)

print()
print("===== TARGET DISTRIBUTION =====")

print(
    "NET_MEAN_PCT=",
    round(
        out["net_return_pct"].mean(),
        5,
    ),
)

print(
    "NET_MEDIAN_PCT=",
    round(
        out["net_return_pct"].median(),
        5,
    ),
)

print(
    "POSITIVE_RATE=",
    round(
        out["positive_after_fee"].mean(),
        5,
    ),
)

print(
    "MFE_MEAN_PCT=",
    round(
        out["mfe_pct"].mean(),
        5,
    ),
)

print(
    "MAE_MEAN_PCT=",
    round(
        out["mae_pct"].mean(),
        5,
    ),
)

print(
    "QUALITY_MEAN_PCT=",
    round(
        out["quality_pct"].mean(),
        5,
    ),
)

print()
print("===== QUANTILES =====")

for col in (
    "net_return_pct",
    "mfe_pct",
    "mae_pct",
    "quality_pct",
):
    q = (
        out[col]
        .quantile(
            [
                0.05,
                0.25,
                0.50,
                0.75,
                0.95,
            ]
        )
    )

    print()
    print(col)
    print(
        q.round(5)
        .to_string()
    )

# Strict temporal ordering.
bad_entry = (
    out["entry_open_time"]
    <= out["feature_close_time"]
)

bad_exit = (
    out["exit_close_time"]
    <= out["entry_open_time"]
)

print()
print("===== CAUSAL TARGET CHECK =====")

print(
    "BAD_ENTRY_ORDER=",
    int(
        bad_entry.sum()
    ),
)

print(
    "BAD_EXIT_ORDER=",
    int(
        bad_exit.sum()
    ),
)

if bad_entry.any():
    raise SystemExit(
        "TARGET_ENTRY_CAUSALITY_FAILURE"
    )

if bad_exit.any():
    raise SystemExit(
        "TARGET_EXIT_CAUSALITY_FAILURE"
    )

if out.isna().any().any():
    raise SystemExit(
        "TARGET_NAN_FAILURE"
    )

if out[
    "feature_close_time"
].duplicated().any():
    raise SystemExit(
        "TARGET_DUPLICATE_TIME"
    )

DST.parent.mkdir(
    parents=True,
    exist_ok=True,
)

tmp = DST.with_suffix(
    ".csv.tmp"
)

out.to_csv(
    tmp,
    index=False,
)

tmp.replace(DST)

print()
print(
    "OUTPUT=",
    DST,
)

print(
    "FILE_MB=",
    round(
        DST.stat().st_size
        / 1024
        / 1024,
        3,
    ),
)

print(
    "ECONOMIC_15M_TARGETS_COMPLETE"
)
