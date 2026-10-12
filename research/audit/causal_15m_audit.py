#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

DATA = (
    ROOT
    / "data/offline_cache"
    / "NEARUSDT_15m_360d.csv"
)

BAR_MS = 15 * 60_000

df = pd.read_csv(DATA)

df = (
    df.sort_values("open_time")
    .reset_index(drop=True)
)

print("===== BASIC =====")
print("ROWS=", len(df))
print(
    "DUP_OPEN=",
    int(df["open_time"].duplicated().sum()),
)

gaps = (
    df["open_time"]
    .diff()
    .dropna()
)

print(
    "BAD_GAPS=",
    int((gaps != BAR_MS).sum()),
)

duration = (
    df["close_time"]
    - df["open_time"]
)

print(
    "BAD_DURATION=",
    int(
        (
            duration != BAR_MS - 1
        ).sum()
    ),
)

# ---------------------------------------------------------
# CAUSAL FEATURE CONSTRUCTION
# Every feature at row t uses data <= t only.
# ---------------------------------------------------------

c = df["close"].astype(float)
o = df["open"].astype(float)
h = df["high"].astype(float)
l = df["low"].astype(float)
v = df["volume"].astype(float)

tb = (
    df["taker_buy_base_volume"]
    .astype(float)
)

features = pd.DataFrame(
    index=df.index
)

features["ret1"] = c.pct_change(1)
features["ret2"] = c.pct_change(2)
features["ret3"] = c.pct_change(3)
features["ret6"] = c.pct_change(6)

features["body"] = (
    (c - o)
    / o.replace(0, np.nan)
)

features["range"] = (
    (h - l)
    / c.replace(0, np.nan)
)

features["upper"] = (
    h
    - pd.concat([o, c], axis=1)
      .max(axis=1)
) / c.replace(0, np.nan)

features["lower"] = (
    pd.concat([o, c], axis=1)
    .min(axis=1)
    - l
) / c.replace(0, np.nan)

features["close_loc"] = (
    (c - l)
    / (h - l).replace(0, np.nan)
)

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

features["de5"] = c / e5 - 1
features["de10"] = c / e10 - 1
features["de20"] = c / e20 - 1
features["e5e20"] = e5 / e20 - 1

features["e5_slope3"] = (
    e5 / e5.shift(3) - 1
)

features["e20_slope3"] = (
    e20 / e20.shift(3) - 1
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

features["atr14"] = (
    tr.rolling(14).mean()
    / c.replace(0, np.nan)
)

ret = c.pct_change()

features["rv6"] = ret.rolling(6).std()
features["rv12"] = ret.rolling(12).std()
features["rv24"] = ret.rolling(24).std()

vmean = v.rolling(20).mean()
vstd = v.rolling(20).std()

features["vol_z20"] = (
    (v - vmean)
    / vstd.replace(0, np.nan)
)

features["buy_ratio"] = (
    tb / v.replace(0, np.nan)
)

features["imbalance"] = (
    2.0 * features["buy_ratio"] - 1.0
)

# ---------------------------------------------------------
# FUTURE MUTATION TEST
#
# Change only data AFTER cutoff.
# Features at/before cutoff must remain identical.
# ---------------------------------------------------------

cut = int(len(df) * 0.70)

mut = df.copy()

future_idx = np.arange(
    cut + 1,
    len(mut),
)

mut.loc[
    future_idx,
    "close"
] *= 1.50

mut.loc[
    future_idx,
    "high"
] *= 1.50

mut.loc[
    future_idx,
    "low"
] *= 1.50

def calc_probe(x):
    c2 = x["close"].astype(float)

    out = pd.DataFrame(
        index=x.index
    )

    out["ret3"] = c2.pct_change(3)

    e = c2.ewm(
        span=20,
        adjust=False,
    ).mean()

    out["ema20"] = e

    out["slope3"] = (
        e / e.shift(3) - 1
    )

    return out

a = calc_probe(df)
b = calc_probe(mut)

pre = slice(
    0,
    cut + 1,
)

delta = (
    a.iloc[pre]
    - b.iloc[pre]
).abs()

max_delta = float(
    np.nanmax(
        delta.to_numpy()
    )
)

print()
print("===== FUTURE MUTATION TEST =====")
print("CUTOFF=", cut)
print(
    "MAX_PRE_CUTOFF_DELTA=",
    max_delta,
)

if max_delta > 1e-12:
    raise SystemExit(
        "CAUSALITY_FAILURE"
    )

# ---------------------------------------------------------
# SHIFT TEST
# t-k must always reference earlier rows.
# ---------------------------------------------------------

temp = features.copy()

for lag in (1, 2, 3, 4):
    temp[
        f"ret1_lag{lag}"
    ] = features["ret1"].shift(lag)

sample = (
    temp[
        [
            "ret1",
            "ret1_lag1",
            "ret1_lag2",
            "ret1_lag3",
            "ret1_lag4",
        ]
    ]
    .dropna()
    .head(5)
)

print()
print("===== SHIFT SAMPLE =====")
print(
    sample.to_string()
)

# Direct equality check:
for lag in (1, 2, 3, 4):
    lhs = temp[
        f"ret1_lag{lag}"
    ]

    rhs = features[
        "ret1"
    ].shift(lag)

    mask = (
        lhs.notna()
        & rhs.notna()
    )

    maxdiff = (
        lhs[mask]
        - rhs[mask]
    ).abs().max()

    if float(maxdiff) > 1e-12:
        raise SystemExit(
            f"SHIFT_FAILURE_LAG={lag}"
        )

print()
print("CAUSAL_15M_AUDIT_PASS")
