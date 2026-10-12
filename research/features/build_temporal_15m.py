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
    / "NEAR_15M_TEMPORAL_FEATURES.csv"
)

df = pd.read_csv(SRC)

df = (
    df.sort_values("open_time")
    .reset_index(drop=True)
)

o = df["open"].astype(float)
h = df["high"].astype(float)
l = df["low"].astype(float)
c = df["close"].astype(float)

v = df["volume"].astype(float)
qv = df["quote_asset_volume"].astype(float)
nt = df["number_of_trades"].astype(float)

tb = df["taker_buy_base_volume"].astype(float)
tq = df["taker_buy_quote_volume"].astype(float)

base = pd.DataFrame(index=df.index)

# ---------------------------------------------------------
# PRICE / MOMENTUM
# ---------------------------------------------------------

for n in (1, 2, 3, 6):
    base[f"ret{n}"] = c.pct_change(n)

base["body"] = (
    (c - o)
    / o.replace(0, np.nan)
)

base["range"] = (
    (h - l)
    / c.replace(0, np.nan)
)

base["upper"] = (
    h
    - pd.concat([o, c], axis=1)
      .max(axis=1)
) / c.replace(0, np.nan)

base["lower"] = (
    pd.concat([o, c], axis=1)
    .min(axis=1)
    - l
) / c.replace(0, np.nan)

base["close_loc"] = (
    (c - l)
    / (h - l).replace(0, np.nan)
)

# ---------------------------------------------------------
# TREND
# ---------------------------------------------------------

e5 = c.ewm(
    span=5,
    adjust=False,
).mean()

e10 = c.ewm(
    span=10,
    adjust=False,
).mean()

e20 = c.ewm(
    span=20,
    adjust=False,
).mean()

base["de5"] = c / e5 - 1
base["de10"] = c / e10 - 1
base["de20"] = c / e20 - 1

base["e5e20"] = (
    e5 / e20 - 1
)

base["e5_slope3"] = (
    e5 / e5.shift(3) - 1
)

base["e20_slope3"] = (
    e20 / e20.shift(3) - 1
)

# ---------------------------------------------------------
# VOLATILITY
# ---------------------------------------------------------

pc = c.shift(1)

tr = pd.concat(
    [
        h - l,
        (h - pc).abs(),
        (l - pc).abs(),
    ],
    axis=1,
).max(axis=1)

base["atr14"] = (
    tr.rolling(14).mean()
    / c.replace(0, np.nan)
)

r = c.pct_change()

base["rv6"] = (
    r.rolling(6).std()
)

base["rv12"] = (
    r.rolling(12).std()
)

base["rv24"] = (
    r.rolling(24).std()
)

# ---------------------------------------------------------
# VOLUME / FLOW
# ---------------------------------------------------------

def zscore(s, n=20):
    m = s.rolling(n).mean()
    sd = s.rolling(n).std()

    return (
        (s - m)
        / sd.replace(0, np.nan)
    )

base["vol_z20"] = zscore(v)
base["qvol_z20"] = zscore(qv)
base["trades_z20"] = zscore(nt)

base["buy_ratio"] = (
    tb / v.replace(0, np.nan)
)

base["qbuy_ratio"] = (
    tq / qv.replace(0, np.nan)
)

base["imbalance"] = (
    2.0 * base["buy_ratio"] - 1.0
)

# ---------------------------------------------------------
# POSITION IN RECENT STRUCTURE
# ---------------------------------------------------------

hh12 = h.rolling(12).max()
ll12 = l.rolling(12).min()

base["pos_12"] = (
    (c - ll12)
    / (hh12 - ll12).replace(0, np.nan)
)

hh24 = h.rolling(24).max()
ll24 = l.rolling(24).min()

base["pos_24"] = (
    (c - ll24)
    / (hh24 - ll24).replace(0, np.nan)
)

# ---------------------------------------------------------
# TEMPORAL EXPANSION
# current + lag1..lag4
# ---------------------------------------------------------

temporal = pd.DataFrame(index=df.index)

for col in base.columns:
    temporal[col] = base[col]

    for lag in (1, 2, 3, 4):
        temporal[
            f"{col}_lag{lag}"
        ] = base[col].shift(lag)

# ---------------------------------------------------------
# SIMPLE ACCELERATION FEATURES
# Still causal:
# current - previous.
# ---------------------------------------------------------

for col in (
    "ret1",
    "ret3",
    "e5e20",
    "e5_slope3",
    "e20_slope3",
    "atr14",
    "rv6",
    "vol_z20",
    "imbalance",
):
    temporal[
        f"{col}_delta1"
    ] = (
        base[col]
        - base[col].shift(1)
    )

# ---------------------------------------------------------
# FINAL DATASET
# ---------------------------------------------------------

out = pd.concat(
    [
        df[
            [
                "open_time",
                "close_time",
                "open",
                "high",
                "low",
                "close",
            ]
        ],
        temporal,
    ],
    axis=1,
)

out = out.replace(
    [np.inf, -np.inf],
    np.nan,
)

before = len(out)

out = (
    out.dropna()
    .reset_index(drop=True)
)

dropped = (
    before - len(out)
)

print("===== TEMPORAL FEATURE BUILD =====")
print("SOURCE_ROWS=", before)
print("FINAL_ROWS=", len(out))
print("WARMUP_DROPPED=", dropped)

feature_cols = [
    c
    for c in out.columns
    if c not in (
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
    )
]

print("FEATURES=", len(feature_cols))

print(
    "NAN_TOTAL=",
    int(
        out[feature_cols]
        .isna()
        .sum()
        .sum()
    ),
)

print(
    "DUP_OPEN=",
    int(
        out["open_time"]
        .duplicated()
        .sum()
    ),
)

print(
    "FIRST=",
    pd.to_datetime(
        int(out["open_time"].iloc[0]),
        unit="ms",
        utc=True,
    ),
)

print(
    "LAST=",
    pd.to_datetime(
        int(out["close_time"].iloc[-1]),
        unit="ms",
        utc=True,
    ),
)

print()
print("===== FEATURE SAMPLE =====")

print(
    "\n".join(
        feature_cols[:40]
    )
)

if out[feature_cols].isna().any().any():
    raise SystemExit(
        "TEMPORAL_FEATURE_NAN"
    )

if out["open_time"].duplicated().any():
    raise SystemExit(
        "TEMPORAL_DUPLICATE_TIME"
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
print("OUTPUT=", DST)

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
    "TEMPORAL_15M_FEATURES_COMPLETE"
)
