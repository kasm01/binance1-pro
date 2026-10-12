#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

D1 = ROOT / "data/offline_cache/NEARUSDT_1m_360d.csv"
D3 = ROOT / "data/offline_cache/NEARUSDT_3m_360d.csv"
D5 = ROOT / "data/offline_cache/NEARUSDT_5m_360d.csv"
D15 = ROOT / "data/offline_cache/NEARUSDT_15m_360d.csv"

OUT = (
    ROOT
    / "research/results"
    / "NEAR_STRONG_SIGNAL_DATASET.csv.gz"
)

FEE = 0.0008


def build_features(df, prefix):
    df = df.copy()

    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    v = df["volume"].astype(float)
    tb = df["taker_buy_base_volume"].astype(float)

    x = pd.DataFrame({
        "close_time": df["close_time"].astype("int64")
    })

    r1 = c.pct_change()

    x[f"{prefix}_ret1"] = r1
    x[f"{prefix}_ret2"] = c.pct_change(2)
    x[f"{prefix}_ret3"] = c.pct_change(3)

    x[f"{prefix}_body"] = (
        (c - o) / o.replace(0, np.nan)
    )

    x[f"{prefix}_range"] = (
        (h - l) / c.replace(0, np.nan)
    )

    x[f"{prefix}_close_loc"] = (
        (c - l)
        / (h - l).replace(0, np.nan)
    )

    e5 = c.ewm(span=5, adjust=False).mean()
    e20 = c.ewm(span=20, adjust=False).mean()

    x[f"{prefix}_e5e20"] = e5 / e20 - 1.0

    x[f"{prefix}_e20_slope3"] = (
        e20 / e20.shift(3) - 1.0
    )

    pc = c.shift(1)

    tr = pd.concat(
        [
            h - l,
            (h - pc).abs(),
            (l - pc).abs(),
        ],
        axis=1,
    ).max(axis=1)

    x[f"{prefix}_atr14"] = (
        tr.rolling(14).mean()
        / c.replace(0, np.nan)
    )

    vm = v.rolling(20).mean()
    vs = v.rolling(20).std()

    x[f"{prefix}_vol_z20"] = (
        (v - vm)
        / vs.replace(0, np.nan)
    )

    buy = tb / v.replace(0, np.nan)

    x[f"{prefix}_buy_ratio"] = buy
    x[f"{prefix}_imbalance"] = 2.0 * buy - 1.0

    # Persistence / acceleration
    x[f"{prefix}_up_frac3"] = (
        (r1 > 0)
        .astype(float)
        .rolling(3)
        .mean()
    )

    x[f"{prefix}_ret1_mean3"] = (
        r1.rolling(3).mean()
    )

    x[f"{prefix}_ret1_accel"] = (
        r1 - r1.shift(1)
    )

    x[f"{prefix}_imb_mean3"] = (
        x[f"{prefix}_imbalance"]
        .rolling(3)
        .mean()
    )

    return x.replace(
        [np.inf, -np.inf],
        np.nan,
    )


d1 = pd.read_csv(D1)
d3 = pd.read_csv(D3)
d5 = pd.read_csv(D5)
d15 = pd.read_csv(D15)

print("===== SOURCE =====")
print("1M=", len(d1))
print("3M=", len(d3))
print("5M=", len(d5))
print("15M=", len(d15))

f5 = build_features(d5, "m5")
f3 = build_features(d3, "m3")
f15 = build_features(d15, "m15")

# 5m is the primary setup timeline.
base = f5.sort_values("close_time").copy()

base = pd.merge_asof(
    base,
    f3.sort_values("close_time"),
    on="close_time",
    direction="backward",
    allow_exact_matches=True,
    suffixes=("", "_m3join"),
)

base = pd.merge_asof(
    base,
    f15.sort_values("close_time"),
    on="close_time",
    direction="backward",
    allow_exact_matches=True,
    suffixes=("", "_m15join"),
)

# merge_asof uses one common close_time.
feature_cols = [
    c for c in base.columns
    if c != "close_time"
]

base = (
    base.replace(
        [np.inf, -np.inf],
        np.nan,
    )
    .dropna()
    .reset_index(drop=True)
)

# ---------------------------------------------------------
# Future 1m scalp path
# Entry = first 1m OPEN strictly after 5m feature close.
# ---------------------------------------------------------

o1 = d1["open"].astype(float).to_numpy()
h1 = d1["high"].astype(float).to_numpy()
l1 = d1["low"].astype(float).to_numpy()
c1 = d1["close"].astype(float).to_numpy()

ot1 = d1["open_time"].to_numpy(dtype=np.int64)
ct1 = d1["close_time"].to_numpy(dtype=np.int64)

rows = []

for _, row in base.iterrows():

    feature_close = int(row["close_time"])

    entry_idx = int(
        np.searchsorted(
            ot1,
            feature_close,
            side="right",
        )
    )

    if entry_idx >= len(d1):
        continue

    # Need complete 10-minute path.
    if entry_idx + 10 > len(d1):
        continue

    entry = float(o1[entry_idx])

    if entry <= 0:
        continue

    out = {
        "feature_close_time":
            feature_close,

        "entry_open_time":
            int(ot1[entry_idx]),

        "entry_price":
            entry,
    }

    for c in feature_cols:
        out[c] = float(row[c])

    for horizon in (3, 5, 10):

        end = entry_idx + horizon

        highs = h1[
            entry_idx:end
        ]

        lows = l1[
            entry_idx:end
        ]

        exit_price = float(
            c1[end - 1]
        )

        max_pos = int(np.argmax(highs))
        min_pos = int(np.argmin(lows))

        mfe = (
            float(np.max(highs))
            / entry - 1.0
        )

        mae = (
            float(np.min(lows))
            / entry - 1.0
        )

        net = (
            exit_price / entry
            - 1.0
            - FEE
        )

        out[f"mfe_{horizon}m"] = mfe
        out[f"mae_{horizon}m"] = mae
        out[f"net_{horizon}m"] = net

        out[f"mfe_{horizon}m_pct"] = (
            mfe * 100.0
        )

        out[f"mae_{horizon}m_pct"] = (
            mae * 100.0
        )

        out[f"net_{horizon}m_pct"] = (
            net * 100.0
        )

        out[f"time_to_mfe_{horizon}m"] = (
            max_pos + 1
        )

        out[f"time_to_mae_{horizon}m"] = (
            min_pos + 1
        )

    rows.append(out)


ds = pd.DataFrame(rows)

print()
print("===== DATASET INTEGRITY =====")
print("ROWS=", len(ds))
print("FEATURES=", len(feature_cols))

print(
    "DUP_FEATURE_TIME=",
    int(
        ds["feature_close_time"]
        .duplicated()
        .sum()
    ),
)

print(
    "NAN_TOTAL=",
    int(ds.isna().sum().sum()),
)

bad_entry = (
    ds["entry_open_time"]
    <= ds["feature_close_time"]
)

print(
    "BAD_ENTRY_ORDER=",
    int(bad_entry.sum()),
)

if bad_entry.any():
    raise SystemExit(
        "ENTRY_CAUSALITY_FAILURE"
    )

if ds.isna().any().any():
    raise SystemExit(
        "DATASET_NAN_FAILURE"
    )

print()
print("===== FUTURE PATH SUMMARY =====")

for horizon in (3, 5, 10):

    print()
    print(f"--- {horizon} MIN ---")

    print(
        "MFE_MEAN_PCT=",
        round(
            ds[f"mfe_{horizon}m_pct"]
            .mean(),
            5,
        ),
    )

    print(
        "MAE_MEAN_PCT=",
        round(
            ds[f"mae_{horizon}m_pct"]
            .mean(),
            5,
        ),
    )

    print(
        "NET_MEAN_PCT=",
        round(
            ds[f"net_{horizon}m_pct"]
            .mean(),
            5,
        ),
    )

    print(
        "NET_POS_RATE=",
        round(
            (
                ds[f"net_{horizon}m_pct"]
                > 0
            ).mean(),
            5,
        ),
    )

print()
print("===== 10M TAIL DIAGNOSTIC =====")

for x in (0.15, 0.25, 0.40):
    rate = (
        ds["mfe_10m_pct"] >= x
    ).mean()

    print(
        f"MFE10_GE_{x:.2f}=",
        round(rate, 5),
    )

for x in (-0.30, -0.50, -1.00):
    rate = (
        ds["mae_10m_pct"] <= x
    ).mean()

    print(
        f"MAE10_LE_{x:.2f}=",
        round(rate, 5),
    )

OUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

ds.to_csv(
    OUT,
    index=False,
    compression="gzip",
)

print()
print("OUTPUT=", OUT)

print(
    "FILE_MB=",
    round(
        OUT.stat().st_size
        / 1024
        / 1024,
        3,
    ),
)

print(
    "STRONG_SIGNAL_DATASET_COMPLETE"
)
