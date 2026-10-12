#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime, timezone, timedelta
import time
import requests
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "offline_cache"

SYMBOLS = [
    "LINKUSDT",
    "AVAXUSDT",
]

INTERVALS = {
    "1m": 60_000,
    "3m": 180_000,
}

DAYS = 120

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

URL = "https://fapi.binance.com/fapi/v1/klines"


def fetch_all(symbol, interval, step_ms, start_ms, end_ms):
    rows = []
    cursor = start_ms

    with requests.Session() as session:
        while cursor < end_ms:
            r = session.get(
                URL,
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": 1500,
                },
                timeout=20,
            )
            r.raise_for_status()

            batch = r.json()

            if not batch:
                break

            rows.extend(batch)

            last_open = int(batch[-1][0])
            nxt = last_open + step_ms

            if nxt <= cursor:
                raise RuntimeError(
                    f"cursor_stuck {symbol} {interval}"
                )

            cursor = nxt

            if len(batch) < 1500:
                break

            time.sleep(0.08)

    return rows


def main():
    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    end = datetime.now(timezone.utc) - timedelta(minutes=5)
    start = end - timedelta(days=DAYS)

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    print(
        "UTC_RANGE=",
        start.isoformat(),
        "->",
        end.isoformat(),
    )

    for symbol in SYMBOLS:
        for interval, step_ms in INTERVALS.items():
            print()
            print("FETCH", symbol, interval)

            rows = fetch_all(
                symbol,
                interval,
                step_ms,
                start_ms,
                end_ms,
            )

            if not rows:
                raise RuntimeError(
                    f"NO_DATA {symbol} {interval}"
                )

            df = pd.DataFrame(
                rows,
                columns=COLS,
            )

            df = (
                df.sort_values("open_time")
                .drop_duplicates("open_time")
                .reset_index(drop=True)
            )

            path = OUT / f"{symbol}_{interval}_6m.csv"

            df.to_csv(
                path,
                index=False,
            )

            expected = (
                DAYS * 24 * 60
                // (
                    1
                    if interval == "1m"
                    else 3
                )
            )

            print(
                "ROWS=",
                len(df),
                "EXPECTED≈",
                expected,
                "FILE=",
                path,
            )


if __name__ == "__main__":
    main()
