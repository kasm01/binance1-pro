#!/usr/bin/env python3

from pathlib import Path
import io
import zipfile
import requests
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/micro_context"
OUT.mkdir(parents=True, exist_ok=True)

SYMBOL = "NEARUSDT"

DATES = [
    "2026-09-12",
    "2026-09-13",
    "2026-09-14",
]

BASE = (
    "https://data.binance.vision/"
    "data/futures/um/daily/aggTrades/"
    f"{SYMBOL}/"
)


def download_zip(date):
    name = f"{SYMBOL}-aggTrades-{date}.zip"
    url = BASE + name

    r = requests.get(
        url,
        timeout=60,
    )

    if r.status_code != 200:
        raise RuntimeError(
            f"DOWNLOAD_FAIL date={date} "
            f"status={r.status_code} "
            f"body={r.text[:300]!r}"
        )

    return r.content


def normalize_columns(df):
    # Binance archive may contain header names
    # or numeric-position CSV depending on archive vintage.
    expected = [
        "agg_trade_id",
        "price",
        "quantity",
        "first_trade_id",
        "last_trade_id",
        "transact_time",
        "is_buyer_maker",
    ]

    if "agg_trade_id" in df.columns:
        return df

    if "id" in df.columns:
        rename = {
            "id": "agg_trade_id",
            "time": "transact_time",
        }
        return df.rename(columns=rename)

    # Headerless fallback.
    if len(df.columns) >= 7:
        df = df.iloc[:, :7].copy()
        df.columns = expected
        return df

    raise RuntimeError(
        f"UNKNOWN_SCHEMA columns={list(df.columns)}"
    )


def read_archive(raw, date):
    z = zipfile.ZipFile(
        io.BytesIO(raw)
    )

    members = [
        x for x in z.namelist()
        if x.lower().endswith(".csv")
    ]

    if len(members) != 1:
        raise RuntimeError(
            f"ZIP_MEMBER_FAIL {date} {members}"
        )

    member = members[0]

    with z.open(member) as fh:
        first = pd.read_csv(fh)

    # If archive was headerless, pandas consumed first trade
    # as column names. Re-read with header=None.
    known = {
        "agg_trade_id",
        "price",
        "quantity",
        "first_trade_id",
        "last_trade_id",
        "transact_time",
        "is_buyer_maker",
        "id",
        "time",
    }

    if not any(
        str(c) in known
        for c in first.columns
    ):
        with z.open(member) as fh:
            first = pd.read_csv(
                fh,
                header=None,
            )

    return normalize_columns(first)


def minute_features(df):
    df = df.copy()

    for c in (
        "price",
        "quantity",
        "transact_time",
    ):
        df[c] = pd.to_numeric(
            df[c],
            errors="coerce",
        )

    df = df.dropna(
        subset=[
            "price",
            "quantity",
            "transact_time",
        ]
    )

    df["transact_time"] = (
        df["transact_time"]
        .astype("int64")
    )

    maker = (
        df["is_buyer_maker"]
        .astype(str)
        .str.lower()
        .isin(["true", "1"])
    )

    # buyer-maker=True means aggressive SELL.
    df["aggr_buy"] = (~maker).astype(int)

    df["notional"] = (
        df["price"]
        * df["quantity"]
    )

    df["signed_qty"] = np.where(
        df["aggr_buy"].eq(1),
        df["quantity"],
        -df["quantity"],
    )

    df["signed_notional"] = np.where(
        df["aggr_buy"].eq(1),
        df["notional"],
        -df["notional"],
    )

    df["minute"] = (
        df["transact_time"]
        // 60_000
        * 60_000
    )

    rows = []

    for minute, g in df.groupby(
        "minute",
        sort=True,
    ):
        notion = (
            g["notional"]
            .to_numpy(float)
        )

        qty = (
            g["quantity"]
            .to_numpy(float)
        )

        total_notional = notion.sum()
        total_qty = qty.sum()
        n = len(g)

        buy = g["aggr_buy"].eq(1)
        buy_n = int(buy.sum())

        buy_notional = (
            g.loc[buy, "notional"]
            .sum()
        )

        buy_qty = (
            g.loc[buy, "quantity"]
            .sum()
        )

        sorted_notional = np.sort(notion)

        top5_sum = (
            sorted_notional[-5:].sum()
            if n >= 5
            else sorted_notional.sum()
        )

        rows.append({
            "open_time": int(minute),
            "close_time": int(minute + 59_999),

            "aggtrade_count": n,

            "aggr_buy_count_ratio":
                buy_n / n
                if n else np.nan,

            "aggr_buy_qty_ratio":
                buy_qty / total_qty
                if total_qty > 0
                else np.nan,

            "signed_qty_imbalance":
                g["signed_qty"].sum()
                / total_qty
                if total_qty > 0
                else np.nan,

            "aggr_buy_notional_ratio":
                buy_notional / total_notional
                if total_notional > 0
                else np.nan,

            "signed_notional_imbalance":
                g["signed_notional"].sum()
                / total_notional
                if total_notional > 0
                else np.nan,

            "total_notional":
                total_notional,

            "avg_trade_notional":
                notion.mean(),

            "median_trade_notional":
                np.median(notion),

            "p90_trade_notional":
                np.quantile(notion, 0.90),

            "p95_trade_notional":
                np.quantile(notion, 0.95),

            "max_trade_notional":
                notion.max(),

            "max_notional_share":
                notion.max()
                / total_notional
                if total_notional > 0
                else np.nan,

            "top5_notional_share":
                top5_sum
                / total_notional
                if total_notional > 0
                else np.nan,
        })

    return pd.DataFrame(rows)


parts = []

for date in DATES:
    print()
    print("=" * 60)
    print("DATE=", date)

    raw = download_zip(date)

    print(
        "ZIP_MB=",
        round(
            len(raw)
            / 1024
            / 1024,
            3,
        ),
    )

    trades = read_archive(
        raw,
        date,
    )

    print(
        "RAW_TRADES=",
        len(trades),
    )

    print(
        "COLUMNS=",
        list(trades.columns),
    )

    mf = minute_features(trades)

    print(
        "MINUTES=",
        len(mf),
    )

    parts.append(mf)

    # Explicitly release raw objects.
    del trades
    del raw


out = (
    pd.concat(
        parts,
        ignore_index=True,
    )
    .sort_values("open_time")
    .drop_duplicates(
        "open_time",
        keep="last",
    )
    .reset_index(drop=True)
)

# -----------------------------
# Past-only rolling derivatives
# -----------------------------
for col in (
    "aggtrade_count",
    "total_notional",
    "avg_trade_notional",
    "p95_trade_notional",
):
    base = (
        out[col]
        .rolling(
            20,
            min_periods=5,
        )
        .mean()
    )

    out[f"{col}_ratio20"] = (
        out[col]
        / base.replace(0, np.nan)
    )

imb = out[
    "signed_notional_imbalance"
]

out["imbalance_mean3"] = (
    imb.rolling(
        3,
        min_periods=1,
    ).mean()
)

out["imbalance_mean5"] = (
    imb.rolling(
        5,
        min_periods=1,
    ).mean()
)

out["imbalance_accel3"] = (
    imb
    - imb.shift(3)
)

out["buy_ratio_mean3"] = (
    out["aggr_buy_notional_ratio"]
    .rolling(
        3,
        min_periods=1,
    )
    .mean()
)

# -----------------------------
# Integrity
# -----------------------------
diffs = (
    out["open_time"]
    .diff()
    .dropna()
)

dup = int(
    out["open_time"]
    .duplicated()
    .sum()
)

bad_gap = int(
    (diffs != 60_000)
    .sum()
)

expected = len(DATES) * 1440

print()
print("===== MICROFLOW INTEGRITY =====")
print("ROWS=", len(out))
print("EXPECTED=", expected)
print("DUP=", dup)
print("BAD_GAP=", bad_gap)

print(
    "FIRST=",
    pd.to_datetime(
        int(out.open_time.iloc[0]),
        unit="ms",
        utc=True,
    ),
)

print(
    "LAST=",
    pd.to_datetime(
        int(out.close_time.iloc[-1]),
        unit="ms",
        utc=True,
    ),
)

path = (
    OUT
    / "NEARUSDT_aggflow_1m_3d.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("FEATURES=", len(out.columns))
print("AGGTRADE_ARCHIVE_MICROFLOW_OK")
