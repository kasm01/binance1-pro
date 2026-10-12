#!/usr/bin/env python3

from pathlib import Path
from datetime import timedelta
import time
import requests
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

BACKFILL_DAYS = 240
URL = "https://fapi.binance.com/fapi/v1/klines"

COLS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]


def get_batch(session, params):
    last_error = None

    for attempt in range(6):
        try:
            r = session.get(
                URL,
                params=params,
                timeout=25,
            )

            if r.status_code in (418, 429):
                wait = min(2 ** attempt, 30)
                print(
                    f"RATE_LIMIT status={r.status_code}"
                    f" sleep={wait}s"
                )
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r.json()

        except Exception as exc:
            last_error = exc
            wait = min(2 ** attempt, 20)
            print(
                f"RETRY attempt={attempt + 1}"
                f" sleep={wait}s"
                f" error={exc!r}"
            )
            time.sleep(wait)

    raise RuntimeError(
        f"FETCH_FAILED {last_error!r}"
    )


def fetch_range(
    session,
    symbol,
    interval,
    step_ms,
    start_ms,
    end_ms,
):
    rows = []
    cursor = start_ms

    while cursor <= end_ms:
        batch = get_batch(
            session,
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1500,
            },
        )

        if not batch:
            break

        rows.extend(batch)

        last_open = int(batch[-1][0])
        nxt = last_open + step_ms

        if nxt <= cursor:
            raise RuntimeError(
                f"CURSOR_STUCK "
                f"{symbol} {interval} "
                f"{cursor} {last_open}"
            )

        cursor = nxt

        if len(batch) < 1500:
            break

        time.sleep(0.08)

    return rows


def validate(df, step_ms):
    ot = pd.to_numeric(
        df["open_time"],
        errors="raise",
    ).astype("int64")

    dup = int(ot.duplicated().sum())

    diff = ot.diff().dropna()

    bad_gap = int(
        (diff != step_ms).sum()
    )

    missing = 0

    if len(ot) >= 2:
        expected = (
            (int(ot.iloc[-1]) - int(ot.iloc[0]))
            // step_ms
            + 1
        )

        missing = int(
            expected - len(df)
        )

    return dup, bad_gap, missing


def main():
    with requests.Session() as session:

        for symbol in SYMBOLS:
            for interval, step_ms in INTERVALS.items():

                current_path = (
                    DATA
                    / f"{symbol}_{interval}_6m.csv"
                )

                if not current_path.exists():
                    raise SystemExit(
                        f"MISSING_CURRENT={current_path}"
                    )

                current = pd.read_csv(
                    current_path
                )

                if list(current.columns) != COLS:
                    raise RuntimeError(
                        f"SCHEMA_MISMATCH "
                        f"{symbol} {interval}"
                    )

                current = (
                    current
                    .sort_values("open_time")
                    .drop_duplicates("open_time")
                    .reset_index(drop=True)
                )

                first_open = int(
                    current["open_time"].iloc[0]
                )

                backfill_ms = int(
                    timedelta(
                        days=BACKFILL_DAYS
                    ).total_seconds()
                    * 1000
                )

                old_start = (
                    first_open
                    - backfill_ms
                )

                old_end = (
                    first_open
                    - step_ms
                )

                print()
                print(
                    "=" * 64
                )
                print(
                    symbol,
                    interval,
                )
                print(
                    "CURRENT_ROWS=",
                    len(current),
                )
                print(
                    "BACKFILL_START_MS=",
                    old_start,
                )
                print(
                    "BACKFILL_END_MS=",
                    old_end,
                )

                rows = fetch_range(
                    session,
                    symbol,
                    interval,
                    step_ms,
                    old_start,
                    old_end,
                )

                older = pd.DataFrame(
                    rows,
                    columns=COLS,
                )

                older = (
                    older
                    .sort_values("open_time")
                    .drop_duplicates("open_time")
                    .reset_index(drop=True)
                )

                merged = pd.concat(
                    [
                        older,
                        current,
                    ],
                    ignore_index=True,
                )

                merged = (
                    merged
                    .sort_values("open_time")
                    .drop_duplicates(
                        "open_time",
                        keep="last",
                    )
                    .reset_index(drop=True)
                )

                dup, bad_gap, missing = (
                    validate(
                        merged,
                        step_ms,
                    )
                )

                out = (
                    DATA
                    / f"{symbol}_{interval}_360d.csv"
                )

                merged.to_csv(
                    out,
                    index=False,
                )

                expected = (
                    360
                    * 24
                    * 60
                    // (
                        1
                        if interval == "1m"
                        else 3
                    )
                )

                print(
                    "BACKFILL_ROWS=",
                    len(older),
                )
                print(
                    "MERGED_ROWS=",
                    len(merged),
                    "EXPECTED≈",
                    expected,
                )
                print(
                    "DUP=",
                    dup,
                    "BAD_GAP=",
                    bad_gap,
                    "MISSING=",
                    missing,
                )
                print(
                    "OUTPUT=",
                    out,
                )

                if (
                    dup != 0
                    or bad_gap != 0
                    or missing != 0
                ):
                    raise RuntimeError(
                        f"INTEGRITY_FAIL "
                        f"{symbol} {interval}"
                    )


if __name__ == "__main__":
    main()
