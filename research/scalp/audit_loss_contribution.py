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

TP = 0.0025
SL = 0.0050
FEE = 0.0008
HORIZON = 10

ds = pd.read_csv(DATA)
d1 = pd.read_csv(D1)

ot = d1["open_time"].to_numpy(dtype=np.int64)
o = d1["open"].astype(float).to_numpy()
h = d1["high"].astype(float).to_numpy()
l = d1["low"].astype(float).to_numpy()
c = d1["close"].astype(float).to_numpy()

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

    if idx + HORIZON > len(d1):
        continue

    entry = float(o[idx])

    if entry <= 0:
        continue

    result = "HOLD"
    exit_minute = HORIZON
    exit_net = None
    max_fav = -999.0
    min_adv = 999.0

    for k in range(HORIZON):

        j = idx + k

        high_ret = (
            h[j] / entry - 1.0
        )

        low_ret = (
            l[j] / entry - 1.0
        )

        max_fav = max(
            max_fav,
            high_ret,
        )

        min_adv = min(
            min_adv,
            low_ret,
        )

        # Conservative same-minute ordering:
        # SL first if both touched in same 1m candle.
        if low_ret <= -SL:
            result = "SL"
            exit_minute = k + 1
            exit_net = -SL - FEE
            break

        if high_ret >= TP:
            result = "TP"
            exit_minute = k + 1
            exit_net = TP - FEE
            break

    if result == "HOLD":

        final_ret = (
            c[idx + HORIZON - 1]
            / entry - 1.0
        )

        exit_net = (
            final_ret - FEE
        )

        if exit_net > 0:
            result = "TIME_PROFIT"
        else:
            result = "TIME_LOSS"

    rows.append({
        "result":
            result,

        "exit_minute":
            exit_minute,

        "exit_net_pct":
            exit_net * 100.0,

        "max_fav_pct":
            max_fav * 100.0,

        "min_adv_pct":
            min_adv * 100.0,
    })


x = pd.DataFrame(rows)

loss = x[
    x["exit_net_pct"] < 0
].copy()

loss["loss_abs_pct"] = (
    -loss["exit_net_pct"]
)

total_loss = (
    loss["loss_abs_pct"].sum()
)

print("===== LOSS CONTRIBUTION =====")
print("TOTAL_TRADES=", len(x))
print("LOSS_TRADES=", len(loss))
print(
    "TOTAL_LOSS_PCT_SUM=",
    round(total_loss, 5),
)

print()
print("===== LOSS BY EXIT REASON =====")

grp = (
    loss
    .groupby("result")
    .agg(
        n=("exit_net_pct", "size"),
        avg_loss_pct=(
            "exit_net_pct",
            "mean",
        ),
        median_loss_pct=(
            "exit_net_pct",
            "median",
        ),
        total_loss_pct=(
            "loss_abs_pct",
            "sum",
        ),
    )
)

grp["pct_of_loss_trades"] = (
    grp["n"]
    / len(loss)
    * 100.0
)

grp["pct_of_total_loss"] = (
    grp["total_loss_pct"]
    / total_loss
    * 100.0
)

print(
    grp.round(5)
    .to_string()
)

print()
print("===== LOSS BY MAX FAVORABLE BAND =====")

bins = [
    -np.inf,
    0.05,
    0.10,
    0.15,
    0.20,
    0.25,
    np.inf,
]

labels = [
    "< +0.05%",
    "+0.05 to +0.10",
    "+0.10 to +0.15",
    "+0.15 to +0.20",
    "+0.20 to +0.25",
    ">= +0.25",
]

loss["mfe_band"] = pd.cut(
    loss["max_fav_pct"],
    bins=bins,
    labels=labels,
    right=False,
)

mfe = (
    loss
    .groupby(
        "mfe_band",
        observed=False,
    )
    .agg(
        n=("exit_net_pct", "size"),
        avg_loss_pct=(
            "exit_net_pct",
            "mean",
        ),
        total_loss_pct=(
            "loss_abs_pct",
            "sum",
        ),
    )
)

mfe["pct_of_loss_trades"] = (
    mfe["n"]
    / len(loss)
    * 100.0
)

mfe["pct_of_total_loss"] = (
    mfe["total_loss_pct"]
    / total_loss
    * 100.0
)

print(
    mfe.round(5)
    .to_string()
)

print()
print("===== SL LOSS CONTRIBUTION BY EXIT MINUTE =====")

sl = loss[
    loss["result"] == "SL"
].copy()

if len(sl):

    sl_total = (
        sl["loss_abs_pct"].sum()
    )

    slm = (
        sl
        .groupby("exit_minute")
        .agg(
            n=("exit_net_pct", "size"),
            total_loss_pct=(
                "loss_abs_pct",
                "sum",
            ),
        )
    )

    slm["pct_of_sl_trades"] = (
        slm["n"]
        / len(sl)
        * 100.0
    )

    slm["pct_of_sl_loss"] = (
        slm["total_loss_pct"]
        / sl_total
        * 100.0
    )

    print(
        slm.round(5)
        .to_string()
    )

print()
print("===== NEAR-TP REVERSAL LOSS CONTRIBUTION =====")

for threshold in (
    0.10,
    0.15,
    0.20,
):

    sub = loss[
        loss["max_fav_pct"]
        >= threshold
    ]

    contrib = (
        sub["loss_abs_pct"].sum()
    )

    print(
        f"MFE_GE_{threshold:.2f}%"
        f" n={len(sub)}"
        f" pct_loss_trades={len(sub)/len(loss)*100:.3f}"
        f" pct_total_loss={contrib/total_loss*100:.3f}"
        f" avg_loss_pct={sub['exit_net_pct'].mean():.5f}"
    )

print()
print("===== EARLY SL CUMULATIVE =====")

if len(sl):

    for minute in (
        1,
        2,
        3,
        5,
        7,
        10,
    ):

        sub = sl[
            sl["exit_minute"]
            <= minute
        ]

        print(
            f"SL_BY_{minute}M"
            f" n={len(sub)}"
            f" rate={len(sub)/len(sl):.5f}"
        )

print()
print("LOSS_CONTRIBUTION_AUDIT_COMPLETE")
