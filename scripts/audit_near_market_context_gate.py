#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

SIGNALS = (
    ROOT
    / "replay_results"
    / "NEAR_FIRST_HIT_GRID_DETAIL.csv"
)

D1 = (
    ROOT
    / "data/offline_cache"
    / "NEARUSDT_1m_360d.csv"
)

D3 = (
    ROOT
    / "data/offline_cache"
    / "NEARUSDT_3m_360d.csv"
)

# Best exit geometry found by the prior independent grid.
TP = 0.40
SL = 1.00
HOLD = 10


def prep(df, prefix):
    df = df.copy()

    c = df["close"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    v = df["volume"].astype(float)

    e5 = c.ewm(
        span=5,
        adjust=False,
    ).mean()

    e20 = c.ewm(
        span=20,
        adjust=False,
    ).mean()

    pc = c.shift(1)

    tr = pd.concat(
        [
            h - l,
            (h - pc).abs(),
            (l - pc).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = (
        tr.rolling(14).mean()
        / c.replace(0, np.nan)
    )

    vm = v.rolling(20).mean()
    vs = v.rolling(20).std()

    out = pd.DataFrame({
        "close_time":
            df["close_time"].astype("int64"),

        f"{prefix}_above_e20":
            (c > e20).astype(float),

        f"{prefix}_e5e20":
            e5 / e20 - 1.0,

        f"{prefix}_e20s3":
            e20 / e20.shift(3) - 1.0,

        f"{prefix}_ret3":
            c.pct_change(3),

        f"{prefix}_ret5":
            c.pct_change(5),

        f"{prefix}_atr":
            atr,

        f"{prefix}_vz":
            (
                (v - vm)
                / vs.replace(0, np.nan)
            ),
    })

    if (
        "taker_buy_base_volume"
        in df.columns
    ):
        tb = df[
            "taker_buy_base_volume"
        ].astype(float)

        out[
            f"{prefix}_buy_ratio"
        ] = (
            tb
            / v.replace(0, np.nan)
        )

    return out.replace(
        [np.inf, -np.inf],
        np.nan,
    )


# ============================================================
# Signals and realized economics
# ============================================================

detail = pd.read_csv(SIGNALS)

base = detail[
    np.isclose(
        detail["tp_pct"],
        TP,
    )
    & np.isclose(
        detail["sl_pct"],
        SL,
    )
    & (
        detail["hold_min_limit"]
        == HOLD
    )
].copy()

base = (
    base[
        [
            "fold",
            "entry_time",
            "score",
            "net_pct",
            "exit_reason",
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

print("===== BASE =====")
print("TRADES=", len(base))

# ============================================================
# Context
# ============================================================

d1 = pd.read_csv(D1)
d3 = pd.read_csv(D3)

f1 = prep(d1, "m1")
f3 = prep(d3, "m3")

ctx = pd.merge_asof(
    f1.sort_values("close_time"),
    f3.sort_values("close_time"),
    on="close_time",
    direction="backward",
    allow_exact_matches=True,
)

base = pd.merge_asof(
    base.sort_values("entry_time"),
    ctx.sort_values("close_time"),
    left_on="entry_time",
    right_on="close_time",
    direction="backward",
    allow_exact_matches=True,
)

# ============================================================
# PREDEFINED gates only.
# No fitted thresholds here.
# ============================================================

gates = {
    "NONE":
        np.ones(
            len(base),
            dtype=bool,
        ),

    "M3_TREND":
        (
            base["m3_e5e20"] > 0
        )
        &
        (
            base["m3_e20s3"] > 0
        ),

    "M1_M3_TREND":
        (
            base["m1_e5e20"] > 0
        )
        &
        (
            base["m1_e20s3"] > 0
        )
        &
        (
            base["m3_e5e20"] > 0
        )
        &
        (
            base["m3_e20s3"] > 0
        ),

    "M3_MOM":
        (
            base["m3_ret3"] > 0
        ),

    "M1_M3_MOM":
        (
            base["m1_ret3"] > 0
        )
        &
        (
            base["m3_ret3"] > 0
        ),

    "M3_BUY":
        (
            base["m3_buy_ratio"] > 0.50
        ),

    "M3_TREND_BUY":
        (
            base["m3_e5e20"] > 0
        )
        &
        (
            base["m3_e20s3"] > 0
        )
        &
        (
            base["m3_buy_ratio"] > 0.50
        ),

    "M1_M3_TREND_BUY":
        (
            base["m1_e5e20"] > 0
        )
        &
        (
            base["m3_e5e20"] > 0
        )
        &
        (
            base["m3_e20s3"] > 0
        )
        &
        (
            base["m3_buy_ratio"] > 0.50
        ),
}

rows = []

for name, mask in gates.items():

    for fold in (1, 2, 3):

        g = base[
            mask
            & (
                base["fold"]
                == fold
            )
        ]

        if len(g) == 0:
            net = np.nan
            win = np.nan
        else:
            net = float(
                g["net_pct"].mean()
            )

            win = float(
                (
                    g["net_pct"]
                    > 0
                ).mean()
                * 100
            )

        rows.append({
            "gate": name,
            "fold": fold,
            "trades": len(g),
            "net_avg": net,
            "win_pct": win,
        })

res = pd.DataFrame(rows)

print()
print("===== GATE / FOLD =====")

print(
    res.round(5)
    .to_string(index=False)
)

summary = (
    res.groupby("gate")
    .agg(
        total_trades=(
            "trades",
            "sum",
        ),
        mean_fold_net=(
            "net_avg",
            "mean",
        ),
        worst_fold=(
            "net_avg",
            "min",
        ),
        positive_folds=(
            "net_avg",
            lambda x:
                int((x > 0).sum()),
        ),
        mean_win=(
            "win_pct",
            "mean",
        ),
    )
    .sort_values(
        [
            "positive_folds",
            "mean_fold_net",
        ],
        ascending=[
            False,
            False,
        ],
    )
)

print()
print("===== CONTEXT SUMMARY =====")

print(
    summary.round(5)
    .to_string()
)

print()
print("===== FOLD CONTEXT DISTRIBUTION =====")

cols = [
    "m1_e5e20",
    "m1_e20s3",
    "m1_ret3",
    "m1_atr",
    "m1_vz",
    "m1_buy_ratio",
    "m3_e5e20",
    "m3_e20s3",
    "m3_ret3",
    "m3_atr",
    "m3_vz",
    "m3_buy_ratio",
]

print(
    base.groupby("fold")[
        cols
    ]
    .mean()
    .round(6)
    .to_string()
)

path = (
    ROOT
    / "replay_results"
    / "NEAR_MARKET_CONTEXT_GATE.csv"
)

res.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print(
    "NEAR_MARKET_CONTEXT_GATE_COMPLETE"
)
