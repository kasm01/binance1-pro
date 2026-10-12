#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SYMBOLS = [
    "AVAXUSDT",
    "DOGEUSDT",
    "LINKUSDT",
    "SOLUSDT",
]

NEAR = (
    ROOT
    / "data/offline_cache"
    / "NEARUSDT_3m_360d.csv"
)

OUT = (
    ROOT
    / "research/results"
    / "ALT_MARKET_CONTEXT_3M.csv"
)


def prep(path, prefix):
    df = pd.read_csv(path)

    df = (
        df.sort_values("close_time")
        .reset_index(drop=True)
    )

    c = df["close"].astype(float)

    out = pd.DataFrame({
        "close_time":
            df["close_time"].astype("int64"),

        f"{prefix}_ret1":
            c.pct_change(1),

        f"{prefix}_ret2":
            c.pct_change(2),

        f"{prefix}_ret3":
            c.pct_change(3),
    })

    e5 = c.ewm(
        span=5,
        adjust=False,
    ).mean()

    e20 = c.ewm(
        span=20,
        adjust=False,
    ).mean()

    out[
        f"{prefix}_e5e20"
    ] = (
        e5 / e20 - 1.0
    )

    out[
        f"{prefix}_e20s3"
    ] = (
        e20 / e20.shift(3) - 1.0
    )

    return out


near = prep(
    NEAR,
    "near",
)

joined = near.copy()

peer_prefixes = []

for sym in SYMBOLS:

    prefix = (
        sym.replace("USDT", "")
        .lower()
    )

    peer_prefixes.append(prefix)

    path = (
        ROOT
        / "data/offline_cache"
        / f"{sym}_3m_360d.csv"
    )

    if not path.exists():
        raise SystemExit(
            f"MISSING={path}"
        )

    x = prep(
        path,
        prefix,
    )

    joined = pd.merge_asof(
        joined.sort_values("close_time"),
        x.sort_values("close_time"),
        on="close_time",
        direction="backward",
        allow_exact_matches=True,
    )


# ---------------------------------------------------------
# MARKET BREADTH
# ---------------------------------------------------------

for horizon in (1, 2, 3):

    cols = [
        f"{p}_ret{horizon}"
        for p in peer_prefixes
    ]

    joined[
        f"market_ret{horizon}_mean"
    ] = joined[
        cols
    ].mean(axis=1)

    joined[
        f"market_ret{horizon}_median"
    ] = joined[
        cols
    ].median(axis=1)

    joined[
        f"market_ret{horizon}_dispersion"
    ] = joined[
        cols
    ].std(axis=1)

    joined[
        f"market_positive{horizon}_frac"
    ] = (
        joined[cols]
        .gt(0)
        .mean(axis=1)
    )

    joined[
        f"near_rel_ret{horizon}"
    ] = (
        joined[
            f"near_ret{horizon}"
        ]
        - joined[
            f"market_ret{horizon}_mean"
        ]
    )


# ---------------------------------------------------------
# TREND BREADTH
# ---------------------------------------------------------

trend_cols = [
    f"{p}_e5e20"
    for p in peer_prefixes
]

slope_cols = [
    f"{p}_e20s3"
    for p in peer_prefixes
]

joined[
    "market_trend_positive_frac"
] = (
    joined[
        trend_cols
    ]
    .gt(0)
    .mean(axis=1)
)

joined[
    "market_slope_positive_frac"
] = (
    joined[
        slope_cols
    ]
    .gt(0)
    .mean(axis=1)
)

joined[
    "near_rel_e5e20"
] = (
    joined["near_e5e20"]
    - joined[
        trend_cols
    ].mean(axis=1)
)

joined[
    "near_rel_e20s3"
] = (
    joined["near_e20s3"]
    - joined[
        slope_cols
    ].mean(axis=1)
)


# ---------------------------------------------------------
# OUTPUT ONLY CONTEXT FEATURES
# ---------------------------------------------------------

keep = [
    "close_time",

    "market_ret1_mean",
    "market_ret1_median",
    "market_ret1_dispersion",
    "market_positive1_frac",
    "near_rel_ret1",

    "market_ret2_mean",
    "market_ret2_median",
    "market_ret2_dispersion",
    "market_positive2_frac",
    "near_rel_ret2",

    "market_ret3_mean",
    "market_ret3_median",
    "market_ret3_dispersion",
    "market_positive3_frac",
    "near_rel_ret3",

    "market_trend_positive_frac",
    "market_slope_positive_frac",

    "near_rel_e5e20",
    "near_rel_e20s3",
]

out = (
    joined[keep]
    .replace(
        [np.inf, -np.inf],
        np.nan,
    )
    .dropna()
    .reset_index(drop=True)
)

print("===== ALT MARKET CONTEXT =====")

print(
    "ROWS=",
    len(out),
)

print(
    "FEATURES=",
    len(keep) - 1,
)

print(
    "NAN_TOTAL=",
    int(
        out.isna()
        .sum()
        .sum()
    ),
)

print(
    "DUP_TIME=",
    int(
        out["close_time"]
        .duplicated()
        .sum()
    ),
)

print(
    "FIRST=",
    pd.to_datetime(
        int(
            out["close_time"]
            .iloc[0]
        ),
        unit="ms",
        utc=True,
    ),
)

print(
    "LAST=",
    pd.to_datetime(
        int(
            out["close_time"]
            .iloc[-1]
        ),
        unit="ms",
        utc=True,
    ),
)

print()
print("===== RELATIVE STRENGTH =====")

for col in (
    "near_rel_ret1",
    "near_rel_ret2",
    "near_rel_ret3",
):

    print(
        col,
        "mean=",
        round(
            out[col].mean(),
            7,
        ),
        "std=",
        round(
            out[col].std(),
            7,
        ),
    )

if out[
    "close_time"
].duplicated().any():
    raise SystemExit(
        "DUPLICATE_CONTEXT_TIME"
    )

if out.isna().any().any():
    raise SystemExit(
        "CONTEXT_NAN"
    )

OUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

out.to_csv(
    OUT,
    index=False,
)

print()
print(
    "OUTPUT=",
    OUT,
)

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
    "ALT_MARKET_CONTEXT_COMPLETE"
)
