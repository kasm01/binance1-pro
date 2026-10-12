#!/usr/bin/env python3

from pathlib import Path
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

raw = pd.read_csv(SIGNALS)

signals = (
    raw[
        ["fold", "entry_time", "score"]
    ]
    .drop_duplicates(
        subset=["fold", "entry_time"]
    )
    .sort_values("entry_time")
    .reset_index(drop=True)
)

d1 = pd.read_csv(
    D1,
    usecols=[
        "close_time",
        "close",
        "high",
        "low",
    ],
)

d1["close_time"] = (
    d1["close_time"]
    .astype("int64")
)

time_to_idx = {
    int(t): i
    for i, t
    in enumerate(d1["close_time"])
}

rows = []

for _, s in signals.iterrows():
    t = int(s["entry_time"])

    if t not in time_to_idx:
        continue

    i = time_to_idx[t]

    entry = float(
        d1["close"].iloc[i]
    )

    row = {
        "fold": int(s["fold"]),
        "entry_time": t,
        "score": float(s["score"]),
        "entry_price": entry,
    }

    for horizon in (5, 10, 20):
        end = min(
            i + horizon,
            len(d1) - 1,
        )

        future = d1.iloc[
            i + 1:
            end + 1
        ]

        if len(future) == 0:
            mfe = np.nan
            mae = np.nan
        else:
            mfe = (
                future["high"].max()
                / entry
                - 1.0
            )

            mae = (
                future["low"].min()
                / entry
                - 1.0
            )

        row[
            f"mfe_{horizon}_pct"
        ] = mfe * 100

        row[
            f"mae_{horizon}_pct"
        ] = mae * 100

    rows.append(row)

out = pd.DataFrame(rows)

print("===== SAMPLE =====")
print("TRADES=", len(out))

print()
print("===== MFE / MAE SUMMARY =====")

cols = []

for h in (5, 10, 20):
    cols.extend([
        f"mfe_{h}_pct",
        f"mae_{h}_pct",
    ])

print(
    out[cols]
    .describe(
        percentiles=[
            0.10,
            0.25,
            0.50,
            0.75,
            0.90,
        ]
    )
    .round(5)
    .to_string()
)

print()
print("===== TARGET HIT RATES =====")

for h in (5, 10, 20):
    mfe = out[
        f"mfe_{h}_pct"
    ]

    print()
    print("HORIZON_MIN=", h)

    for target in (
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
        0.40,
        0.50,
    ):
        hit = (
            mfe >= target
        ).mean() * 100

        print(
            f"MFE>={target:.2f}% "
            f"hit={hit:.2f}%"
        )

print()
print("===== ADVERSE RATES =====")

for h in (5, 10, 20):
    mae = out[
        f"mae_{h}_pct"
    ]

    print()
    print("HORIZON_MIN=", h)

    for stop in (
        -0.10,
        -0.15,
        -0.20,
        -0.25,
        -0.30,
        -0.50,
        -1.00,
    ):
        hit = (
            mae <= stop
        ).mean() * 100

        print(
            f"MAE<={stop:.2f}% "
            f"rate={hit:.2f}%"
        )

print()
print("===== SCORE QUARTILES =====")

out["score_q"] = pd.qcut(
    out["score"],
    4,
    labels=[
        "Q1_LOW",
        "Q2",
        "Q3",
        "Q4_HIGH",
    ],
    duplicates="drop",
)

summary = (
    out.groupby(
        "score_q",
        observed=True,
    )
    .agg(
        trades=("score", "count"),
        score_mean=("score", "mean"),
        mfe5=("mfe_5_pct", "mean"),
        mfe10=("mfe_10_pct", "mean"),
        mfe20=("mfe_20_pct", "mean"),
        mae5=("mae_5_pct", "mean"),
        mae10=("mae_10_pct", "mean"),
        mae20=("mae_20_pct", "mean"),
    )
)

print(
    summary
    .round(5)
    .to_string()
)

print()
print("===== HIGH SCORE HIT RATES =====")

high = out[
    out["score_q"]
    == "Q4_HIGH"
]

for h in (5, 10, 20):
    print()
    print("Q4 HORIZON=", h)

    for target in (
        0.15,
        0.20,
        0.30,
        0.40,
    ):
        hit = (
            high[
                f"mfe_{h}_pct"
            ]
            >= target
        ).mean() * 100

        print(
            f"MFE>={target:.2f}% "
            f"hit={hit:.2f}%"
        )

path = (
    ROOT
    / "replay_results"
    / "NEAR_MFE_MAE.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("NEAR_MFE_MAE_COMPLETE")
