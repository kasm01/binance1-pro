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
    exit_ret = None

    max_fav = -999.0
    min_adv = 999.0

    first_negative_minute = None
    first_positive_minute = None

    max_before_exit = -999.0

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

        if (
            first_positive_minute is None
            and high_ret > 0
        ):
            first_positive_minute = k + 1

        if (
            first_negative_minute is None
            and low_ret < 0
        ):
            first_negative_minute = k + 1

        # Conservative:
        # if SL and TP appear in same 1m candle,
        # SL is counted first.
        if low_ret <= -SL:
            result = "SL"
            exit_minute = k + 1
            exit_ret = -SL - FEE
            max_before_exit = max_fav
            break

        if high_ret >= TP:
            result = "TP"
            exit_minute = k + 1
            exit_ret = TP - FEE
            max_before_exit = max_fav
            break

    if result == "HOLD":

        final_ret = (
            c[idx + HORIZON - 1]
            / entry - 1.0
        )

        exit_ret = (
            final_ret - FEE
        )

        max_before_exit = max_fav

        if exit_ret > 0:
            result = "TIME_PROFIT"
        else:
            result = "TIME_LOSS"

    rows.append({
        "result":
            result,

        "exit_minute":
            exit_minute,

        "exit_net_pct":
            exit_ret * 100.0,

        "max_fav_pct":
            max_before_exit * 100.0,

        "min_adv_pct":
            min_adv * 100.0,

        "first_positive_minute":
            first_positive_minute,

        "first_negative_minute":
            first_negative_minute,
    })


x = pd.DataFrame(rows)

loss = x[
    x["exit_net_pct"] < 0
].copy()

print("===== OVERALL =====")
print("TOTAL=", len(x))
print("LOSSES=", len(loss))
print(
    "LOSS_RATE=",
    round(
        len(loss) / len(x),
        5,
    ),
)

print()
print("===== LOSS EXIT REASON =====")

reason = (
    loss["result"]
    .value_counts()
    .rename("n")
    .to_frame()
)

reason["pct_of_losses"] = (
    reason["n"]
    / len(loss)
    * 100.0
)

print(
    reason.round(3)
    .to_string()
)

print()
print("===== MAX FAVORABLE BEFORE LOSS =====")

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
    loss["mfe_band"]
    .value_counts(sort=False)
    .rename("n")
    .to_frame()
)

mfe["pct_of_losses"] = (
    mfe["n"]
    / len(loss)
    * 100.0
)

print(
    mfe.round(3)
    .to_string()
)

print()
print("===== FIRST NEGATIVE MINUTE =====")

neg = (
    loss["first_negative_minute"]
    .value_counts()
    .sort_index()
    .rename("n")
    .to_frame()
)

neg["pct_of_losses"] = (
    neg["n"]
    / len(loss)
    * 100.0
)

print(
    neg.round(3)
    .to_string()
)

print()
print("===== SL LOSS BY MINUTE =====")

sl = loss[
    loss["result"] == "SL"
]

sl_by_min = (
    sl["exit_minute"]
    .value_counts()
    .sort_index()
    .rename("n")
    .to_frame()
)

if len(sl):
    sl_by_min["pct_of_sl"] = (
        sl_by_min["n"]
        / len(sl)
        * 100.0
    )

print(
    sl_by_min.round(3)
    .to_string()
)

print()
print("===== NEAR-TP REVERSALS =====")

for threshold in (
    0.10,
    0.15,
    0.20,
):

    n = int(
        (
            loss["max_fav_pct"]
            >= threshold
        ).sum()
    )

    print(
        f"LOSS_AFTER_MFE_GE_{threshold:.2f}%=",
        n,
        "rate=",
        round(
            n / len(loss),
            5,
        ),
    )

print()
print("LOSS_PATH_STAGE_AUDIT_COMPLETE")
