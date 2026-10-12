#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime, timezone, timedelta
import time
import requests
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/micro_context"
OUT.mkdir(parents=True, exist_ok=True)

SYMBOL = "NEARUSDT"
DAYS = 3

URL = "https://fapi.binance.com/fapi/v1/aggTrades"

session = requests.Session()


def fetch(params):
    last = None

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
            last = exc
            wait = min(2 ** attempt, 20)
            print(
                "RETRY",
                attempt + 1,
                repr(exc),
                "sleep=",
                wait,
            )
            time.sleep(wait)

    raise RuntimeError(
        f"FETCH_FAILED {last!r}"
    )


now = datetime.now(timezone.utc)

end = now.replace(
    second=0,
    microsecond=0,
) - timedelta(minutes=1)

start = end - timedelta(days=DAYS)

start_ms = int(start.timestamp() * 1000)
end_ms = int(end.timestamp() * 1000) - 1

print("SYMBOL=", SYMBOL)
print("START=", start.isoformat())
print("END=", end.isoformat())

# İlk aggTrade ID'yi zaman sorgusuyla bul.
first_batch = fetch({
    "symbol": SYMBOL,
    "startTime": start_ms,
    "endTime": min(
        start_ms + 3_599_000,
        end_ms,
    ),
    "limit": 1000,
})

if not first_batch:
    raise RuntimeError("NO_INITIAL_AGGTRADES")

cursor = int(first_batch[0]["a"])

print("FIRST_AGG_ID=", cursor)

minute_rows = {}

total = 0
pages = 0
last_id = None


def consume(batch):
    global total, last_id

    for x in batch:
        ts = int(x["T"])

        if ts < start_ms:
            continue

        if ts > end_ms:
            return False

        price = float(x["p"])
        qty = float(x["q"])
        notional = price * qty

        # buyer maker=True:
        # aggressive side = SELL
        aggressive_buy = not bool(x["m"])

        minute = (
            ts // 60_000
        ) * 60_000

        r = minute_rows.setdefault(
            minute,
            {
                "trade_count": 0,
                "buy_count": 0,
                "sell_count": 0,
                "qty": 0.0,
                "buy_qty": 0.0,
                "sell_qty": 0.0,
                "notional": 0.0,
                "buy_notional": 0.0,
                "sell_notional": 0.0,
                "max_notional": 0.0,
            }
        )

        r["trade_count"] += 1
        r["qty"] += qty
        r["notional"] += notional
        r["max_notional"] = max(
            r["max_notional"],
            notional,
        )

        if aggressive_buy:
            r["buy_count"] += 1
            r["buy_qty"] += qty
            r["buy_notional"] += notional
        else:
            r["sell_count"] += 1
            r["sell_qty"] += qty
            r["sell_notional"] += notional

        total += 1
        last_id = int(x["a"])

    return True


# İlk batch'i işle.
consume(first_batch)

cursor = int(first_batch[-1]["a"]) + 1

while True:
    batch = fetch({
        "symbol": SYMBOL,
        "fromId": cursor,
        "limit": 1000,
    })

    if not batch:
        break

    pages += 1

    keep_going = consume(batch)

    if pages % 250 == 0:
        print(
            "PAGES=",
            pages,
            "TRADES=",
            total,
            "LAST_ID=",
            last_id,
        )

    if not keep_going:
        break

    nxt = int(batch[-1]["a"]) + 1

    if nxt <= cursor:
        raise RuntimeError(
            "AGG_CURSOR_STUCK"
        )

    cursor = nxt

    time.sleep(0.02)


rows = []

for minute in sorted(minute_rows):
    r = minute_rows[minute]

    tc = r["trade_count"]
    qty = r["qty"]
    notion = r["notional"]

    rows.append({
        "open_time": minute,
        "trade_count": tc,
        "buy_count": r["buy_count"],
        "sell_count": r["sell_count"],

        "buy_count_ratio":
            r["buy_count"] / tc
            if tc else np.nan,

        "buy_qty_ratio":
            r["buy_qty"] / qty
            if qty else np.nan,

        "signed_qty_imbalance":
            (
                r["buy_qty"]
                - r["sell_qty"]
            ) / qty
            if qty else np.nan,

        "buy_notional_ratio":
            r["buy_notional"] / notion
            if notion else np.nan,

        "signed_notional_imbalance":
            (
                r["buy_notional"]
                - r["sell_notional"]
            ) / notion
            if notion else np.nan,

        "total_qty": qty,
        "total_notional": notion,

        "avg_trade_notional":
            notion / tc
            if tc else np.nan,

        "max_trade_notional":
            r["max_notional"],
    })


df = pd.DataFrame(rows)

if df.empty:
    raise RuntimeError("MICROFLOW_EMPTY")

df = df.sort_values(
    "open_time"
).reset_index(drop=True)

# Derived rolling features.
df["trade_intensity_ratio"] = (
    df["trade_count"]
    / df["trade_count"]
      .rolling(20, min_periods=5)
      .mean()
)

df["notional_intensity_ratio"] = (
    df["total_notional"]
    / df["total_notional"]
      .rolling(20, min_periods=5)
      .mean()
)

df["flow_accel_3"] = (
    df["signed_notional_imbalance"]
    - df["signed_notional_imbalance"]
      .rolling(3, min_periods=1)
      .mean()
)

diffs = (
    df["open_time"]
    .diff()
    .dropna()
)

bad_gap = int(
    (diffs != 60_000).sum()
)

dup = int(
    df["open_time"]
    .duplicated()
    .sum()
)

expected = DAYS * 24 * 60

print()
print("===== MICROFLOW INTEGRITY =====")
print("RAW_TRADES=", total)
print("ROWS=", len(df))
print("EXPECTED≈", expected)
print("DUP=", dup)
print("BAD_GAP=", bad_gap)

print(
    "FIRST=",
    pd.to_datetime(
        df.open_time.iloc[0],
        unit="ms",
        utc=True,
    ),
)

print(
    "LAST=",
    pd.to_datetime(
        df.open_time.iloc[-1],
        unit="ms",
        utc=True,
    ),
)

path = (
    OUT
    / "NEARUSDT_aggflow_1m_3d.csv"
)

df.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("AGGTRADE_MICROFLOW_OK")
