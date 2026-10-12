#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

DATA = (
    ROOT / "research/results"
    / "NEAR_STRONG_SIGNAL_DATASET.csv.gz"
)

D1 = (
    ROOT / "data/offline_cache"
    / "NEARUSDT_1m_360d.csv"
)

OUT = (
    ROOT / "research/results"
    / "NEAR_LIFECYCLE_GRID.csv"
)

FEE = 0.0008
MAX_PATH = 10

ds = pd.read_csv(DATA)
d1 = pd.read_csv(D1)

ot = d1["open_time"].to_numpy(dtype=np.int64)
o = d1["open"].astype(float).to_numpy()
h = d1["high"].astype(float).to_numpy()
l = d1["low"].astype(float).to_numpy()
c = d1["close"].astype(float).to_numpy()


# ---------------------------------------------------------
# Fixed, predeclared rule set.
# No optimization inside the backtest.
# ---------------------------------------------------------

variants = []


def add(
    name,
    family,
    fixed_tp=None,
    hard_stop=0.0050,
    max_hold=10,
    early_window=None,
    early_mfe=None,
    early_mae=None,
    arm=None,
    giveback=None,
):
    variants.append({
        "name": name,
        "family": family,
        "fixed_tp": fixed_tp,
        "hard_stop": hard_stop,
        "max_hold": max_hold,
        "early_window": early_window,
        "early_mfe": early_mfe,
        "early_mae": early_mae,
        "arm": arm,
        "giveback": giveback,
    })


# =========================================================
# BASE
# =========================================================

add(
    "BASE_TP25_SL50_10M",
    "BASE",
    fixed_tp=0.0025,
    hard_stop=0.0050,
    max_hold=10,
)


# =========================================================
# EARLY ADVERSE + DIRECT TP
# =========================================================

for ew, mfe, mae in [
    (2, 0.0005, 0.0015),
    (2, 0.0005, 0.0020),
    (3, 0.0005, 0.0015),
    (3, 0.0005, 0.0020),
    (3, 0.0010, 0.0020),
    (3, 0.0010, 0.0025),
    (5, 0.0010, 0.0020),
    (5, 0.0010, 0.0025),
]:
    add(
        (
            f"EARLY_{ew}M_"
            f"MFE{mfe*100:.2f}_"
            f"MAE{mae*100:.2f}"
        ),
        "EARLY",
        fixed_tp=0.0025,
        hard_stop=0.0050,
        max_hold=10,
        early_window=ew,
        early_mfe=mfe,
        early_mae=mae,
    )


# =========================================================
# RUNNER / PROFIT PROTECTION
# =========================================================

for arm, gb, hs, mh in [
    (0.0010, 0.0005, 0.0050, 10),
    (0.0010, 0.0008, 0.0050, 10),
    (0.0015, 0.0005, 0.0050, 10),
    (0.0015, 0.0008, 0.0050, 10),
    (0.0015, 0.0010, 0.0050, 10),
    (0.0020, 0.0008, 0.0050, 10),
    (0.0020, 0.0010, 0.0050, 10),
]:
    add(
        (
            f"RUN_ARM{arm*100:.2f}_"
            f"GB{gb*100:.2f}_"
            f"SL{hs*100:.2f}_"
            f"{mh}M"
        ),
        "RUNNER",
        fixed_tp=None,
        hard_stop=hs,
        max_hold=mh,
        arm=arm,
        giveback=gb,
    )


# =========================================================
# EARLY + RUNNER
# =========================================================

for ew, mfe, mae, arm, gb, hs in [
    (2, .0005, .0015, .0010, .0005, .0040),
    (2, .0005, .0020, .0015, .0005, .0040),
    (3, .0005, .0015, .0010, .0005, .0040),
    (3, .0005, .0020, .0015, .0005, .0040),
    (3, .0010, .0020, .0015, .0008, .0040),
    (3, .0010, .0025, .0015, .0008, .0050),
    (5, .0010, .0020, .0015, .0008, .0040),
    (5, .0010, .0025, .0020, .0008, .0050),
]:
    add(
        (
            f"COMBO_{ew}M_"
            f"MFE{mfe*100:.2f}_"
            f"MAE{mae*100:.2f}_"
            f"ARM{arm*100:.2f}_"
            f"GB{gb*100:.2f}_"
            f"SL{hs*100:.2f}"
        ),
        "EARLY_RUNNER",
        fixed_tp=None,
        hard_stop=hs,
        max_hold=10,
        early_window=ew,
        early_mfe=mfe,
        early_mae=mae,
        arm=arm,
        giveback=gb,
    )


print("===== INPUT =====")
print("TRADES=", len(ds))
print("VARIANTS=", len(variants))
print("FEE_PCT=", FEE * 100)


# ---------------------------------------------------------
# Pre-map each trade to its 1m entry index.
# ---------------------------------------------------------

entry_idx = np.searchsorted(
    ot,
    ds["entry_open_time"].to_numpy(dtype=np.int64),
    side="left",
)

valid = (
    (entry_idx >= 0)
    & (entry_idx + MAX_PATH <= len(d1))
)

ds = ds.loc[valid].reset_index(drop=True)
entry_idx = entry_idx[valid]

print("VALID_TRADES=", len(ds))


def threshold_down_exit(open_ret, low_ret, threshold):
    """
    threshold is negative or positive trailing floor.

    If candle opens below threshold, real execution cannot
    assume threshold price; use candle open instead.

    Otherwise, if low touches threshold, threshold is used.
    """
    if open_ret <= threshold:
        return open_ret

    if low_ret <= threshold:
        return threshold

    return None


def threshold_up_exit(open_ret, high_ret, threshold):
    """
    Same logic for an upside fixed TP.
    """
    if open_ret >= threshold:
        return open_ret

    if high_ret >= threshold:
        return threshold

    return None


def simulate(idx, cfg):

    entry = float(o[idx])

    max_seen = -np.inf
    min_seen = np.inf

    armed = False

    # IMPORTANT:
    # trailing floor is derived ONLY from information
    # known before current candle.
    prior_trail = None

    max_hold = int(cfg["max_hold"])

    for k in range(max_hold):

        j = idx + k

        open_ret = o[j] / entry - 1.0
        high_ret = h[j] / entry - 1.0
        low_ret = l[j] / entry - 1.0
        close_ret = c[j] / entry - 1.0

        # ---------------------------------------------
        # 1. Previously active trailing protection.
        # It existed before this candle opened.
        # ---------------------------------------------

        if prior_trail is not None:

            trail_exit = threshold_down_exit(
                open_ret,
                low_ret,
                prior_trail,
            )

            if trail_exit is not None:
                return (
                    trail_exit - FEE,
                    k + 1,
                    "GIVEBACK",
                )

        # ---------------------------------------------
        # 2. Hard stop.
        # ---------------------------------------------

        stop_level = -float(cfg["hard_stop"])

        stop_exit = threshold_down_exit(
            open_ret,
            low_ret,
            stop_level,
        )

        if stop_exit is not None:
            return (
                stop_exit - FEE,
                k + 1,
                "HARD_STOP",
            )

        # ---------------------------------------------
        # 3. Fixed TP, if this is a direct-TP variant.
        #
        # Conservative ambiguity rule:
        # stop was evaluated before TP.
        # ---------------------------------------------

        if cfg["fixed_tp"] is not None:

            tp_exit = threshold_up_exit(
                open_ret,
                high_ret,
                float(cfg["fixed_tp"]),
            )

            if tp_exit is not None:
                return (
                    tp_exit - FEE,
                    k + 1,
                    "FIXED_TP",
                )

        # ---------------------------------------------
        # Update path diagnostics AFTER active exits.
        # ---------------------------------------------

        max_seen = max(max_seen, high_ret)
        min_seen = min(min_seen, low_ret)

        # ---------------------------------------------
        # 4. Early adverse / failed follow-through.
        #
        # Evaluated only at close of requested window.
        # Therefore no future information is used.
        # ---------------------------------------------

        if (
            cfg["early_window"] is not None
            and (k + 1) == int(cfg["early_window"])
            and max_seen < float(cfg["early_mfe"])
            and min_seen <= -float(cfg["early_mae"])
        ):
            return (
                close_ret - FEE,
                k + 1,
                "EARLY_EXIT",
            )

        # ---------------------------------------------
        # 5. Runner arm.
        #
        # If arm is first reached inside THIS candle,
        # no giveback is allowed in the same candle.
        # That avoids unknowable OHLC ordering.
        # ---------------------------------------------

        if cfg["arm"] is not None:

            if max_seen >= float(cfg["arm"]):
                armed = True

            if armed:
                prior_trail = (
                    max_seen
                    - float(cfg["giveback"])
                )

    # Timeout at completed candle close.
    final_ret = (
        c[idx + max_hold - 1]
        / entry - 1.0
    )

    return (
        final_ret - FEE,
        max_hold,
        "TIME_EXIT",
    )


all_rows = []

for vi, cfg in enumerate(variants, start=1):

    rets = np.empty(len(entry_idx), dtype=float)
    durations = np.empty(len(entry_idx), dtype=int)
    reasons = []

    for i, idx in enumerate(entry_idx):

        r, d, reason = simulate(
            int(idx),
            cfg,
        )

        rets[i] = r
        durations[i] = d
        reasons.append(reason)

    positive = rets[rets > 0]
    negative = rets[rets < 0]

    gross_profit = positive.sum()
    gross_loss = -negative.sum()

    pf = (
        gross_profit / gross_loss
        if gross_loss > 0
        else np.inf
    )

    # Four chronological blocks.
    fold_edges = np.linspace(
        0,
        len(rets),
        5,
        dtype=int,
    )

    fold_means = []

    for f in range(4):

        a = fold_edges[f]
        b = fold_edges[f + 1]

        fold_means.append(
            float(
                rets[a:b].mean()
            )
        )

    reasons_s = pd.Series(reasons)

    row = {
        "name":
            cfg["name"],

        "family":
            cfg["family"],

        "n":
            len(rets),

        "net_mean_pct":
            rets.mean() * 100,

        "net_median_pct":
            np.median(rets) * 100,

        "win_pct":
            (rets > 0).mean() * 100,

        "profit_factor":
            pf,

        "avg_win_pct":
            (
                positive.mean() * 100
                if len(positive)
                else np.nan
            ),

        "avg_loss_pct":
            (
                negative.mean() * 100
                if len(negative)
                else np.nan
            ),

        "avg_duration_min":
            durations.mean(),

        "tail_le_m030_pct":
            (rets <= -0.0030).mean() * 100,

        "tail_le_m050_pct":
            (rets <= -0.0050).mean() * 100,

        "positive_folds":
            int(
                sum(
                    x > 0
                    for x in fold_means
                )
            ),

        "fold1_pct":
            fold_means[0] * 100,

        "fold2_pct":
            fold_means[1] * 100,

        "fold3_pct":
            fold_means[2] * 100,

        "fold4_pct":
            fold_means[3] * 100,

        "hard_stop_pct":
            (
                reasons_s.eq("HARD_STOP")
                .mean()
                * 100
            ),

        "early_exit_pct":
            (
                reasons_s.eq("EARLY_EXIT")
                .mean()
                * 100
            ),

        "giveback_exit_pct":
            (
                reasons_s.eq("GIVEBACK")
                .mean()
                * 100
            ),

        "fixed_tp_pct":
            (
                reasons_s.eq("FIXED_TP")
                .mean()
                * 100
            ),

        "time_exit_pct":
            (
                reasons_s.eq("TIME_EXIT")
                .mean()
                * 100
            ),
    }

    all_rows.append(row)

    print(
        f"[{vi:02d}/{len(variants):02d}]"
        f" {cfg['name']}"
        f" net={row['net_mean_pct']:.5f}%"
        f" PF={row['profit_factor']:.4f}"
        f" folds={row['positive_folds']}/4"
    )


res = pd.DataFrame(all_rows)

base_net = float(
    res.loc[
        res["name"] == "BASE_TP25_SL50_10M",
        "net_mean_pct",
    ].iloc[0]
)

res["delta_vs_base_pct"] = (
    res["net_mean_pct"]
    - base_net
)

res = (
    res.sort_values(
        [
            "net_mean_pct",
            "positive_folds",
            "profit_factor",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    )
    .reset_index(drop=True)
)

print()
print("===== TOP 15 LIFECYCLE VARIANTS =====")

show = [
    "name",
    "family",
    "net_mean_pct",
    "delta_vs_base_pct",
    "profit_factor",
    "win_pct",
    "avg_win_pct",
    "avg_loss_pct",
    "avg_duration_min",
    "tail_le_m030_pct",
    "tail_le_m050_pct",
    "positive_folds",
]

print(
    res[show]
    .head(15)
    .round(5)
    .to_string(index=False)
)

print()
print("===== BASE =====")

print(
    res.loc[
        res["name"] == "BASE_TP25_SL50_10M",
        show,
    ]
    .round(5)
    .to_string(index=False)
)

print()
print("===== BEST BY FAMILY =====")

best_family = (
    res.sort_values(
        "net_mean_pct",
        ascending=False,
    )
    .groupby(
        "family",
        as_index=False,
    )
    .first()
)

print(
    best_family[
        [
            "family",
            "name",
            "net_mean_pct",
            "delta_vs_base_pct",
            "profit_factor",
            "positive_folds",
            "tail_le_m030_pct",
            "tail_le_m050_pct",
        ]
    ]
    .round(5)
    .to_string(index=False)
)

print()
print("===== ROBUSTNESS =====")

print(
    "POSITIVE_EXPECTANCY_VARIANTS=",
    int(
        (
            res["net_mean_pct"] > 0
        ).sum()
    ),
    "/",
    len(res),
)

print(
    "PF_GT1_VARIANTS=",
    int(
        (
            res["profit_factor"] > 1
        ).sum()
    ),
    "/",
    len(res),
)

print(
    "POSITIVE_3PLUS_FOLDS=",
    int(
        (
            res["positive_folds"] >= 3
        ).sum()
    ),
    "/",
    len(res),
)

res.to_csv(
    OUT,
    index=False,
)

print()
print("OUTPUT=", OUT)
print("LIFECYCLE_GRID_COMPLETE")
