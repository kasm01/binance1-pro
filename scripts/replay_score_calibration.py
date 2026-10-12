#!/usr/bin/env python3

from pathlib import Path
from bisect import bisect_right
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

RESULTS = ROOT / "replay_results"
DATA = (
    ROOT
    / "replay_data"
    / "sol_20260912_13"
    / "aggtrades"
)

WINDOWS = ("A", "B", "C")
LEV = 3.0

HORIZONS_MIN = [
    5,
    10,
    20,
    30,
]

BINS = [
    0.525,
    0.600,
    0.625,
    0.650,
    0.675,
    0.700,
    1.001,
]

LABELS = [
    "0.525-0.600",
    "0.600-0.625",
    "0.625-0.650",
    "0.650-0.675",
    "0.675-0.700",
    "0.700+",
]


def load_agg(window):
    p = DATA / f"SOLUSDT_{window}_aggTrades.json"

    raw = json.loads(
        p.read_text(encoding="utf-8")
    )

    ts = [
        int(x["T"])
        for x in raw
    ]

    px = [
        float(x["p"])
        for x in raw
    ]

    return ts, px


def price_at(ts, px, target):
    i = bisect_right(
        ts,
        int(target),
    ) - 1

    if i < 0:
        return None

    return float(px[i])


rows = []

for window in WINDOWS:
    df = pd.read_csv(
        RESULTS
        / f"SOLUSDT_{window}_replay.csv"
    )

    df = df[
        df["sniper"] == "PASS"
    ].copy()

    # 3m production decision candle identity.
    df["decision_3m"] = (
        df["timestamp_ms"]
        // 180000
    )

    # Aynı 3m candle'dan yalnız ilk sniper PASS.
    df = (
        df.sort_values("timestamp_ms")
        .drop_duplicates(
            subset=["decision_3m"],
            keep="first",
        )
    )

    ts, px = load_agg(window)

    if not ts:
        continue

    last_ts = ts[-1]

    for _, r in df.iterrows():
        entry_ts = int(
            r["timestamp_ms"]
        )

        entry_px = float(
            r["price"]
        )

        row = {
            "window": window,
            "time_trt": r["time_trt"],
            "entry_ts": entry_ts,
            "price": entry_px,
            "model_score": float(
                r["model_score"]
            ),
            "confirm": str(
                r.get(
                    "confirm_proposed",
                    "",
                )
            ),
        }

        for minutes in HORIZONS_MIN:
            target = (
                entry_ts
                + minutes
                * 60
                * 1000
            )

            if target > last_ts:
                row[
                    f"roi_{minutes}m"
                ] = None
                continue

            future_px = price_at(
                ts,
                px,
                target,
            )

            if future_px is None:
                row[
                    f"roi_{minutes}m"
                ] = None
                continue

            gross_roi = (
                (
                    future_px
                    / entry_px
                )
                - 1.0
            ) * LEV

            row[
                f"roi_{minutes}m"
            ] = gross_roi

        rows.append(row)


df = pd.DataFrame(rows)

df["score_bin"] = pd.cut(
    df["model_score"],
    bins=BINS,
    labels=LABELS,
    right=False,
)

out_raw = (
    RESULTS
    / "SOLUSDT_score_calibration_raw.csv"
)

df.to_csv(
    out_raw,
    index=False,
)

summary_rows = []

for score_bin, g in df.groupby(
    "score_bin",
    observed=True,
):
    base = {
        "score_bin": str(score_bin),
        "count": len(g),
        "avg_score": (
            g["model_score"].mean()
        ),
    }

    for minutes in HORIZONS_MIN:
        col = f"roi_{minutes}m"

        x = (
            g[col]
            .dropna()
        )

        base[
            f"n_{minutes}m"
        ] = len(x)

        if len(x):
            base[
                f"avg_roi_{minutes}m_pct"
            ] = x.mean() * 100

            base[
                f"median_roi_{minutes}m_pct"
            ] = x.median() * 100

            base[
                f"win_rate_{minutes}m_pct"
            ] = (
                (x > 0).mean()
                * 100
            )

    summary_rows.append(base)


summary = pd.DataFrame(
    summary_rows
)

out_summary = (
    RESULTS
    / "SOLUSDT_score_calibration_summary.csv"
)

summary.to_csv(
    out_summary,
    index=False,
)

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    260,
)

print(
    "===== SCORE CALIBRATION ====="
)

print(
    "unique_3m_candidates=",
    len(df),
)

print()

print(
    summary.round(4)
    .to_string(index=False)
)

print()
print("===== SCORE CORRELATIONS =====")

for minutes in HORIZONS_MIN:
    col = f"roi_{minutes}m"

    q = df[
        ["model_score", col]
    ].dropna()

    if len(q) > 2:
        pearson = (
            q["model_score"]
            .corr(q[col])
        )

        spearman = (
            q["model_score"]
            .corr(
                q[col],
                method="spearman",
            )
        )

        print(
            f"{minutes}m:",
            "pearson=",
            round(
                pearson,
                4,
            ),
            "spearman=",
            round(
                spearman,
                4,
            ),
        )

print()
print("RAW=", out_raw)
print("SUMMARY=", out_summary)
print("SCORE_CALIBRATION_COMPLETE")
