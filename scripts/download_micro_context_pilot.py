#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime, timezone, timedelta
import time
import requests
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "micro_context"

SYMBOL = "NEARUSDT"

DAYS = 29
PERIOD_MS = 5 * 60 * 1000
WINDOW_BARS = 480

OI_URL = (
    "https://fapi.binance.com"
    "/futures/data/openInterestHist"
)

FUNDING_URL = (
    "https://fapi.binance.com"
    "/fapi/v1/fundingRate"
)


def get_json(session, url, params):
    last_error = None

    for attempt in range(6):
        try:
            r = session.get(
                url,
                params=params,
                timeout=25,
            )

            if r.status_code in (418, 429):
                wait = min(2 ** attempt, 30)

                print(
                    "RATE_LIMIT",
                    r.status_code,
                    "sleep=",
                    wait,
                )

                time.sleep(wait)
                continue

            r.raise_for_status()
            return r.json()

        except Exception as exc:
            last_error = exc

            wait = min(
                2 ** attempt,
                20,
            )

            print(
                "RETRY",
                attempt + 1,
                "sleep=",
                wait,
                repr(exc),
            )

            time.sleep(wait)

    raise RuntimeError(
        f"FETCH_FAILED {last_error!r}"
    )


def floor_5m(ms):
    return (
        int(ms)
        // PERIOD_MS
        * PERIOD_MS
    )


def fetch_oi(session, start_ms, end_ms):
    rows = []

    cursor = start_ms

    while cursor <= end_ms:

        window_end = min(
            cursor
            + (WINDOW_BARS - 1) * PERIOD_MS,
            end_ms,
        )

        batch = get_json(
            session,
            OI_URL,
            {
                "symbol": SYMBOL,
                "period": "5m",
                "startTime": cursor,
                "endTime": window_end,
                "limit": 500,
            },
        )

        print(
            "OI_WINDOW",
            cursor,
            "->",
            window_end,
            "rows=",
            len(batch),
        )

        rows.extend(batch)

        # API sonucuna göre değil,
        # deterministic zaman penceresine göre ilerle.
        cursor = (
            window_end
            + PERIOD_MS
        )

        time.sleep(0.10)

    return rows


def fetch_funding(session, start_ms, end_ms):
    return get_json(
        session,
        FUNDING_URL,
        {
            "symbol": SYMBOL,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 1000,
        },
    )


def main():
    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    now_ms = int(
        datetime.now(
            timezone.utc
        ).timestamp()
        * 1000
    )

    # Son tamamlanmış 5m bucket.
    end_ms = (
        floor_5m(now_ms)
        - PERIOD_MS
    )

    start_ms = (
        end_ms
        - DAYS * 24 * 60 * 60 * 1000
        + PERIOD_MS
    )

    print(
        "SYMBOL=",
        SYMBOL,
    )

    print(
        "UTC_START=",
        datetime.fromtimestamp(
            start_ms / 1000,
            tz=timezone.utc,
        ).isoformat(),
    )

    print(
        "UTC_END=",
        datetime.fromtimestamp(
            end_ms / 1000,
            tz=timezone.utc,
        ).isoformat(),
    )

    with requests.Session() as session:

        oi = fetch_oi(
            session,
            start_ms,
            end_ms,
        )

        funding = fetch_funding(
            session,
            start_ms,
            end_ms,
        )

    oi_df = pd.DataFrame(oi)

    if oi_df.empty:
        raise RuntimeError(
            "OI_EMPTY"
        )

    oi_df["timestamp"] = pd.to_numeric(
        oi_df["timestamp"],
        errors="raise",
    ).astype("int64")

    oi_df = (
        oi_df
        .sort_values("timestamp")
        .drop_duplicates(
            "timestamp",
            keep="last",
        )
        .reset_index(drop=True)
    )

    diffs = (
        oi_df["timestamp"]
        .diff()
        .dropna()
    )

    dup = int(
        oi_df["timestamp"]
        .duplicated()
        .sum()
    )

    bad_gap = int(
        (diffs != PERIOD_MS)
        .sum()
    )

    expected = (
        DAYS
        * 24
        * 12
    )

    print()
    print("===== OI INTEGRITY =====")

    print(
        "ROWS=",
        len(oi_df),
        "EXPECTED≈",
        expected,
    )

    print(
        "DUP=",
        dup,
        "BAD_GAP=",
        bad_gap,
    )

    print(
        "FIRST_TS=",
        datetime.fromtimestamp(
            int(
                oi_df["timestamp"]
                .iloc[0]
            ) / 1000,
            tz=timezone.utc,
        ).isoformat(),
    )

    print(
        "LAST_TS=",
        datetime.fromtimestamp(
            int(
                oi_df["timestamp"]
                .iloc[-1]
            ) / 1000,
            tz=timezone.utc,
        ).isoformat(),
    )

    funding_df = pd.DataFrame(
        funding
    )

    if not funding_df.empty:

        funding_df["fundingTime"] = (
            pd.to_numeric(
                funding_df[
                    "fundingTime"
                ],
                errors="raise",
            )
            .astype("int64")
        )

        funding_df = (
            funding_df
            .sort_values(
                "fundingTime"
            )
            .drop_duplicates(
                "fundingTime",
                keep="last",
            )
            .reset_index(drop=True)
        )

    oi_path = (
        OUT
        / f"{SYMBOL}_oi_5m_29d.csv"
    )

    funding_path = (
        OUT
        / f"{SYMBOL}_funding_29d.csv"
    )

    oi_df.to_csv(
        oi_path,
        index=False,
    )

    funding_df.to_csv(
        funding_path,
        index=False,
    )

    print()
    print("===== FUNDING =====")

    print(
        "ROWS=",
        len(funding_df),
    )

    print()
    print("===== OUTPUT =====")

    print(
        "OI_FILE=",
        oi_path,
    )

    print(
        "FUNDING_FILE=",
        funding_path,
    )

    if dup != 0:
        raise RuntimeError(
            "OI_DUPLICATE_FAIL"
        )

    print()
    print(
        "MICRO_CONTEXT_PILOT_OK"
    )


if __name__ == "__main__":
    main()
