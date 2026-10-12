#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

SYMBOLS = [
    "LINKUSDT",
    "NEARUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "SOLUSDT",
]

CONFIG = {
    "1m": {
        "horizons": [15, 30, 45],
        "tps": [0.0020, 0.0030, 0.0040, 0.0050],
        "sls": [0.0010, 0.0015, 0.0020],
    },
    "3m": {
        "horizons": [5, 10, 15],
        "tps": [0.0020, 0.0030, 0.0040, 0.0050],
        "sls": [0.0010, 0.0015, 0.0020],
    },
}

FEE = 0.0008


def barrier(close, high, low, horizon, tp, sl):
    n = len(close) - horizon
    entry = close[:n]

    hit = np.zeros(n, dtype=np.int8)
    gross = np.zeros(n, dtype=float)

    for k in range(1, horizon + 1):
        active = hit == 0

        if not active.any():
            break

        hr = high[k:k+n] / np.maximum(entry, 1e-12) - 1.0
        lr = low[k:k+n] / np.maximum(entry, 1e-12) - 1.0

        tp_hit = active & (hr >= tp)
        sl_hit = active & (lr <= -sl)

        # Aynı mumda iki bariyer de görülürse konservatif:
        # SL önce olmuş kabul ediyoruz.
        loss = sl_hit
        win = tp_hit & ~sl_hit

        hit[loss] = -1
        gross[loss] = -sl

        hit[win] = 1
        gross[win] = tp

    timeout = hit == 0

    terminal = (
        close[horizon:horizon+n]
        / np.maximum(entry, 1e-12)
        - 1.0
    )

    gross[timeout] = terminal[timeout]

    net = gross - FEE

    return hit, net


rows = []

for symbol in SYMBOLS:
    for interval, cfg in CONFIG.items():

        path = (
            ROOT
            / "data/offline_cache"
            / f"{symbol}_{interval}_360d.csv"
        )

        df = pd.read_csv(
            path,
            usecols=[
                "close",
                "high",
                "low",
            ],
        )

        close = df["close"].astype(float).to_numpy()
        high = df["high"].astype(float).to_numpy()
        low = df["low"].astype(float).to_numpy()

        for horizon in cfg["horizons"]:
            for tp in cfg["tps"]:
                for sl in cfg["sls"]:

                    hit, net = barrier(
                        close,
                        high,
                        low,
                        horizon,
                        tp,
                        sl,
                    )

                    rows.append({
                        "symbol": symbol,
                        "interval": interval,
                        "horizon_bars": horizon,
                        "tp_pct": tp * 100,
                        "sl_pct": sl * 100,
                        "n": len(hit),
                        "tp_first_pct":
                            (hit == 1).mean() * 100,
                        "sl_first_pct":
                            (hit == -1).mean() * 100,
                        "timeout_pct":
                            (hit == 0).mean() * 100,
                        "net_avg_pct":
                            net.mean() * 100,
                        "net_median_pct":
                            np.median(net) * 100,
                        "net_win_pct":
                            (net > 0).mean() * 100,
                        "breakeven_win_pct":
                            (
                                (sl + FEE)
                                /
                                (
                                    (tp - FEE)
                                    + (sl + FEE)
                                )
                                * 100
                            ),
                    })


out = pd.DataFrame(rows)

print("===== BEST RAW OPPORTUNITY CONTRACTS =====")

best = (
    out.sort_values(
        "net_avg_pct",
        ascending=False,
    )
    .groupby(
        ["symbol", "interval"],
        as_index=False,
    )
    .first()
)

print(
    best[
        [
            "symbol",
            "interval",
            "horizon_bars",
            "tp_pct",
            "sl_pct",
            "tp_first_pct",
            "sl_first_pct",
            "timeout_pct",
            "breakeven_win_pct",
            "net_avg_pct",
            "net_median_pct",
            "net_win_pct",
        ]
    ]
    .round(5)
    .to_string(index=False)
)

print()
print("===== AGGREGATE CONTRACTS =====")

agg = (
    out.groupby(
        [
            "interval",
            "horizon_bars",
            "tp_pct",
            "sl_pct",
        ],
        as_index=False,
    )
    .agg(
        mean_tp_first=("tp_first_pct", "mean"),
        mean_sl_first=("sl_first_pct", "mean"),
        mean_timeout=("timeout_pct", "mean"),
        mean_net=("net_avg_pct", "mean"),
        median_net=("net_avg_pct", "median"),
        mean_win=("net_win_pct", "mean"),
    )
    .sort_values(
        "mean_net",
        ascending=False,
    )
)

print(
    agg.head(30)
    .round(5)
    .to_string(index=False)
)

path = (
    ROOT
    / "replay_results"
    / "LONG_OPPORTUNITY_ECONOMICS.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("OPPORTUNITY_ECONOMICS_COMPLETE")
