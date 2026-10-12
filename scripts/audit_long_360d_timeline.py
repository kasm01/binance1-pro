#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "offline_cache"

SYMBOLS = [
    "LINKUSDT",
    "NEARUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "SOLUSDT",
]

INTERVALS = {
    "1m": 60_000,
    "3m": 180_000,
}


def utc(ms):
    return datetime.fromtimestamp(
        int(ms) / 1000,
        tz=timezone.utc,
    ).isoformat()


rows = []

for sym in SYMBOLS:
    for interval, step_ms in INTERVALS.items():

        path = (
            DATA
            / f"{sym}_{interval}_360d.csv"
        )

        df = pd.read_csv(
            path,
            usecols=[
                "open_time",
                "close_time",
            ],
        )

        ot = pd.to_numeric(
            df["open_time"],
            errors="raise",
        ).astype("int64")

        ct = pd.to_numeric(
            df["close_time"],
            errors="raise",
        ).astype("int64")

        diffs = ot.diff().dropna()

        rows.append({
            "symbol": sym,
            "interval": interval,
            "rows": len(df),
            "start_ms": int(ot.iloc[0]),
            "end_ms": int(ot.iloc[-1]),
            "start_utc": utc(ot.iloc[0]),
            "end_utc": utc(ot.iloc[-1]),
            "last_close_utc": utc(ct.iloc[-1]),
            "duplicates": int(
                ot.duplicated().sum()
            ),
            "bad_gaps": int(
                (diffs != step_ms).sum()
            ),
        })


out = pd.DataFrame(rows)

print("===== PER FILE TIMELINE =====")
print(
    out[
        [
            "symbol",
            "interval",
            "rows",
            "start_utc",
            "end_utc",
            "duplicates",
            "bad_gaps",
        ]
    ].to_string(index=False)
)

print()
print("===== COMMON RANGE BY INTERVAL =====")

for interval in INTERVALS:

    z = out[
        out["interval"] == interval
    ]

    common_start = int(
        z["start_ms"].max()
    )

    common_end = int(
        z["end_ms"].min()
    )

    duration_days = (
        common_end
        - common_start
    ) / 86_400_000

    print(
        interval,
        "COMMON_START=",
        utc(common_start),
        "COMMON_END=",
        utc(common_end),
        "DAYS=",
        round(duration_days, 4),
    )

print()
print("===== GLOBAL COMMON RANGE =====")

common_start = int(
    out["start_ms"].max()
)

common_end = int(
    out["end_ms"].min()
)

print(
    "START=",
    utc(common_start),
)

print(
    "END=",
    utc(common_end),
)

print(
    "DAYS=",
    round(
        (
            common_end
            - common_start
        )
        / 86_400_000,
        4,
    ),
)

if (
    out["duplicates"].sum() != 0
    or out["bad_gaps"].sum() != 0
):
    raise SystemExit(
        "TIMELINE_INTEGRITY_FAIL"
    )

print()
print("TIMELINE_AUDIT_OK")
