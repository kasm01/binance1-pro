#!/usr/bin/env python3

from pathlib import Path
import io
import zipfile
import requests
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

SIGNALS = (
    ROOT
    / "replay_results"
    / "NEAR_DIRECT_ROI_GRID.csv"
)

D1 = (
    ROOT
    / "data/offline_cache"
    / "NEARUSDT_1m_360d.csv"
)

SYMBOL = "NEARUSDT"
FEE = 0.0008

BASE_URL = (
    "https://data.binance.vision/"
    "data/futures/um/daily/aggTrades/"
    f"{SYMBOL}/"
)

TPS = [
    0.0010,
    0.0015,
    0.0020,
    0.0025,
    0.0030,
    0.0040,
    0.0050,
    0.0060,
]

SLS = [
    0.0015,
    0.0020,
    0.0025,
    0.0030,
    0.0040,
    0.0050,
    0.0075,
    0.0100,
]

HOLDS_MIN = [
    5,
    10,
    20,
]


def load_day(date):
    name = (
        f"{SYMBOL}-aggTrades-{date}.zip"
    )

    r = requests.get(
        BASE_URL + name,
        timeout=60,
    )

    r.raise_for_status()

    with zipfile.ZipFile(
        io.BytesIO(r.content)
    ) as z:
        member = [
            x
            for x in z.namelist()
            if x.endswith(".csv")
        ][0]

        with z.open(member) as fh:
            df = pd.read_csv(fh)

    df["transact_time"] = pd.to_numeric(
        df["transact_time"]
    ).astype("int64")

    df["price"] = pd.to_numeric(
        df["price"]
    ).astype(float)

    return (
        df[
            [
                "transact_time",
                "price",
            ]
        ]
        .sort_values("transact_time")
        .reset_index(drop=True)
    )


raw = pd.read_csv(SIGNALS)

signals = (
    raw[
        [
            "fold",
            "entry_time",
            "score",
        ]
    ]
    .drop_duplicates(
        subset=[
            "fold",
            "entry_time",
        ]
    )
    .sort_values("entry_time")
    .reset_index(drop=True)
)

print("SIGNALS=", len(signals))

d1 = pd.read_csv(
    D1,
    usecols=[
        "close_time",
        "close",
    ],
)

entry_map = dict(
    zip(
        d1["close_time"].astype("int64"),
        d1["close"].astype(float),
    )
)

dates = sorted(
    pd.to_datetime(
        signals["entry_time"],
        unit="ms",
        utc=True,
    )
    .dt.strftime("%Y-%m-%d")
    .unique()
)

days = {}

for date in dates:
    print("LOAD", date)
    days[date] = load_day(date)

rows = []

for _, s in signals.iterrows():

    entry_time = int(
        s["entry_time"]
    )

    fold = int(
        s["fold"]
    )

    score = float(
        s["score"]
    )

    entry = float(
        entry_map[entry_time]
    )

    date = pd.to_datetime(
        entry_time,
        unit="ms",
        utc=True,
    ).strftime("%Y-%m-%d")

    ticks = days[date]

    tt_all = ticks[
        "transact_time"
    ].to_numpy()

    pp_all = ticks[
        "price"
    ].to_numpy()

    for hold_min in HOLDS_MIN:

        end_time = (
            entry_time
            + hold_min * 60_000
        )

        mask = (
            (tt_all > entry_time)
            & (tt_all <= end_time)
        )

        tt = tt_all[mask]
        pp = pp_all[mask]

        if len(tt) == 0:
            continue

        for tp in TPS:
            for sl in SLS:

                reason = "time_exit"
                exit_price = float(
                    pp[-1]
                )
                exit_ts = int(
                    tt[-1]
                )

                for ts, px in zip(
                    tt,
                    pp,
                ):
                    move = (
                        float(px)
                        / entry
                        - 1.0
                    )

                    if move >= tp:
                        reason = "tp_hit"
                        exit_price = float(px)
                        exit_ts = int(ts)
                        break

                    if move <= -sl:
                        reason = "sl_hit"
                        exit_price = float(px)
                        exit_ts = int(ts)
                        break

                gross = (
                    exit_price
                    / entry
                    - 1.0
                )

                net = gross - FEE

                rows.append({
                    "fold": fold,
                    "score": score,
                    "tp_pct": tp * 100,
                    "sl_pct": sl * 100,
                    "hold_min_limit":
                        hold_min,
                    "entry_time":
                        entry_time,
                    "exit_reason":
                        reason,
                    "gross_pct":
                        gross * 100,
                    "net_pct":
                        net * 100,
                    "actual_hold_min":
                        (
                            exit_ts
                            - entry_time
                        )
                        / 60_000.0,
                })


out = pd.DataFrame(rows)

print()
print(
    "===== GRID ROWS ====="
)
print("ROWS=", len(out))

summary = (
    out.groupby(
        [
            "tp_pct",
            "sl_pct",
            "hold_min_limit",
        ]
    )
    .agg(
        trades=(
            "net_pct",
            "count",
        ),
        net_avg=(
            "net_pct",
            "mean",
        ),
        net_median=(
            "net_pct",
            "median",
        ),
        total_net=(
            "net_pct",
            "sum",
        ),
        win_pct=(
            "net_pct",
            lambda x:
                (x > 0).mean()
                * 100,
        ),
        avg_hold=(
            "actual_hold_min",
            "mean",
        ),
    )
    .reset_index()
)

pf = []

for _, r in summary.iterrows():

    g = out[
        np.isclose(
            out["tp_pct"],
            r["tp_pct"],
        )
        & np.isclose(
            out["sl_pct"],
            r["sl_pct"],
        )
        & (
            out["hold_min_limit"]
            == r["hold_min_limit"]
        )
    ]

    wins = g.loc[
        g["net_pct"] > 0,
        "net_pct",
    ].sum()

    losses = -g.loc[
        g["net_pct"] < 0,
        "net_pct",
    ].sum()

    pf.append(
        wins / losses
        if losses > 0
        else np.inf
    )

summary[
    "profit_factor"
] = pf


# -----------------------------------------
# Per-fold robustness
# -----------------------------------------

fold_net = (
    out.groupby(
        [
            "tp_pct",
            "sl_pct",
            "hold_min_limit",
            "fold",
        ]
    )["net_pct"]
    .mean()
    .unstack("fold")
    .reset_index()
)

fold_cols = [
    c
    for c in fold_net.columns
    if isinstance(c, (int, np.integer))
]

if not fold_cols:
    fold_cols = [
        1,
        2,
        3,
    ]

fold_net[
    "positive_folds"
] = (
    fold_net[
        fold_cols
    ]
    > 0
).sum(axis=1)

fold_net[
    "worst_fold"
] = (
    fold_net[
        fold_cols
    ]
    .min(axis=1)
)

summary = summary.merge(
    fold_net,
    on=[
        "tp_pct",
        "sl_pct",
        "hold_min_limit",
    ],
    how="left",
)

summary = summary.sort_values(
    [
        "positive_folds",
        "net_avg",
    ],
    ascending=[
        False,
        False,
    ],
)

print()
print(
    "===== TOP ROBUST CONFIGS ====="
)

print(
    summary
    .head(25)
    .round(5)
    .to_string(
        index=False
    )
)

print()
print(
    "===== POSITIVE ALL 3 FOLDS ====="
)

all3 = summary[
    summary[
        "positive_folds"
    ]
    == 3
]

if len(all3):
    print(
        all3
        .head(30)
        .round(5)
        .to_string(
            index=False
        )
    )
else:
    print(
        "NONE"
    )

print()
print(
    "===== BEST BY HOLD ====="
)

for h in HOLDS_MIN:

    g = summary[
        summary[
            "hold_min_limit"
        ]
        == h
    ]

    print()
    print(
        "HOLD=",
        h,
    )

    print(
        g.head(10)
        .round(5)
        .to_string(
            index=False
        )
    )


path = (
    ROOT
    / "replay_results"
    / "NEAR_FIRST_HIT_GRID.csv"
)

summary.to_csv(
    path,
    index=False,
)

detail_path = (
    ROOT
    / "replay_results"
    / "NEAR_FIRST_HIT_GRID_DETAIL.csv"
)

out.to_csv(
    detail_path,
    index=False,
)

print()
print("OUTPUT=", path)
print(
    "DETAIL=",
    detail_path,
)
print(
    "NEAR_FIRST_HIT_GRID_COMPLETE"
)
