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

SYMBOL = "NEARUSDT"
LEVERAGE = 3.0
FEE = 0.0008
STALL_MS = 1_200_000
MAX_HOLD_MS = 180 * 60_000

BASE_URL = (
    "https://data.binance.vision/"
    "data/futures/um/daily/aggTrades/"
    f"{SYMBOL}/"
)

SCENARIOS = {
    "CURRENT45_08": (0.0045, 0.0008),
    "DIRECT45":     (0.0045, 0.0),
    "DIRECT40":     (0.0040, 0.0),
    "DIRECT35":     (0.0035, 0.0),
    "DIRECT30":     (0.0030, 0.0),
}

# Underlying price stop.
STOPS = [
    0.0100,  # current production-like 1%
    0.0030,
    0.0025,
    0.0020,
    0.0015,
]


def load_day(date):
    name = f"{SYMBOL}-aggTrades-{date}.zip"
    r = requests.get(
        BASE_URL + name,
        timeout=60,
    )
    r.raise_for_status()

    with zipfile.ZipFile(
        io.BytesIO(r.content)
    ) as z:
        member = [
            x for x in z.namelist()
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

    return df[
        ["transact_time", "price"]
    ].sort_values("transact_time")


raw = pd.read_csv(SIGNALS)

signals = (
    raw[
        ["fold", "entry_time"]
    ]
    .drop_duplicates()
    .sort_values("entry_time")
    .reset_index(drop=True)
)

print("SIGNALS=", len(signals))

# Entry price = exact 1m close used by previous replay.
d1 = pd.read_csv(
    ROOT
    / "data/offline_cache"
    / "NEARUSDT_1m_360d.csv",
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
        signals.entry_time,
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
    entry_time = int(s.entry_time)
    fold = int(s.fold)

    entry = float(
        entry_map[entry_time]
    )

    date = pd.to_datetime(
        entry_time,
        unit="ms",
        utc=True,
    ).strftime("%Y-%m-%d")

    ticks = days[date]

    t = ticks["transact_time"].to_numpy()
    p = ticks["price"].to_numpy()

    mask = (
        (t > entry_time)
        & (t <= entry_time + MAX_HOLD_MS)
    )

    tt = t[mask]
    pp = p[mask]

    if len(tt) == 0:
        continue

    for scen, (tp_roi, giveback) in SCENARIOS.items():
        for stop_pct in STOPS:
            best_roi = 0.0
            last_best_ts = entry_time
            reason = "window_end"
            exit_price = float(pp[-1])
            exit_ts = int(tt[-1])

            for ts, px in zip(tt, pp):
                pnl = (
                    float(px) / entry
                    - 1.0
                )

                roi = pnl * LEVERAGE

                # ROI lifecycle hard TP/giveback first.
                if roi > best_roi:
                    best_roi = roi
                    last_best_ts = int(ts)

                if giveback <= 0:
                    if roi >= tp_roi:
                        reason = "direct_tp"
                        exit_price = float(px)
                        exit_ts = int(ts)
                        break

                elif (
                    best_roi >= tp_roi
                    and roi <= best_roi - giveback
                ):
                    reason = "giveback_tp"
                    exit_price = float(px)
                    exit_ts = int(ts)
                    break

                # General lifecycle loss safety.
                if pnl <= -abs(stop_pct):
                    reason = "sl_hit"
                    exit_price = float(px)
                    exit_ts = int(ts)
                    break

                # Stall since last new best.
                if (
                    int(ts) - last_best_ts
                    >= STALL_MS
                ):
                    reason = "stall_exit"
                    exit_price = float(px)
                    exit_ts = int(ts)
                    break

            gross = (
                exit_price / entry
                - 1.0
            )

            net = gross - FEE

            rows.append({
                "fold": fold,
                "scenario": scen,
                "stop_pct": stop_pct * 100,
                "entry_time": entry_time,
                "exit_reason": reason,
                "gross_pct": gross * 100,
                "net_pct": net * 100,
                "hold_min":
                    (exit_ts - entry_time)
                    / 60_000.0,
            })

out = pd.DataFrame(rows)

print()
print("===== TICK LIFECYCLE GRID =====")

summary = (
    out.groupby(
        ["scenario", "stop_pct"]
    )
    .agg(
        trades=("net_pct", "count"),
        net_avg=("net_pct", "mean"),
        net_median=("net_pct", "median"),
        total_net=("net_pct", "sum"),
        win_pct=(
            "net_pct",
            lambda x:
                (x > 0).mean() * 100,
        ),
        avg_hold=("hold_min", "mean"),
    )
)

pf = {}

for key, g in out.groupby(
    ["scenario", "stop_pct"]
):
    wins = g.loc[
        g.net_pct > 0,
        "net_pct",
    ].sum()

    losses = -g.loc[
        g.net_pct < 0,
        "net_pct",
    ].sum()

    pf[key] = (
        wins / losses
        if losses > 0
        else np.inf
    )

summary["profit_factor"] = pd.Series(pf)

print(
    summary
    .round(5)
    .sort_values(
        "net_avg",
        ascending=False,
    )
    .to_string()
)

print()
print("===== TOP 12 =====")

print(
    summary
    .reset_index()
    .sort_values(
        "net_avg",
        ascending=False,
    )
    .head(12)
    .round(5)
    .to_string(index=False)
)

print()
print("===== EXIT REASONS TOP CONFIGS =====")

top = (
    summary
    .reset_index()
    .sort_values(
        "net_avg",
        ascending=False,
    )
    .head(5)
)

for _, r in top.iterrows():
    g = out[
        (out.scenario == r.scenario)
        & (
            np.isclose(
                out.stop_pct,
                r.stop_pct,
            )
        )
    ]

    print()
    print(
        r.scenario,
        "STOP=",
        r.stop_pct,
    )

    print(
        g.exit_reason
        .value_counts()
        .to_string()
    )

path = (
    ROOT
    / "replay_results"
    / "NEAR_TICK_LIFECYCLE_GRID.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("NEAR_TICK_LIFECYCLE_GRID_COMPLETE")
