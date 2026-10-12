#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime, timezone
import json
import sys
import os
import requests
import numpy as np
import pandas as pd
from joblib import load
from sklearn.metrics import roc_auc_score, brier_score_loss

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

from features.pipeline import make_matrix

MODEL_PATH = ROOT / "models/online_model_3m_best.joblib"
META_PATH = ROOT / "models/model_meta_3m.json"
OUT_DIR = ROOT / "replay_results"

SYMBOLS = [
    "BTCUSDT",
    "SOLUSDT",
    "NEARUSDT",
    "SUIUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "XRPUSDT",
]

INTERVAL = "3m"

WINDOWS = {
    "A": (
        "2026-09-12T05:40:00+00:00",
        "2026-09-12T11:15:00+00:00",
    ),
    "B": (
        "2026-09-12T13:15:00+00:00",
        "2026-09-12T17:30:00+00:00",
    ),
    "C": (
        "2026-09-12T23:35:00+00:00",
        "2026-09-13T09:40:00+00:00",
    ),
}

# 6h feature warmup + 30m forward-label margin.
FETCH_START = "2026-09-11T23:35:00+00:00"
FETCH_END = "2026-09-13T10:15:00+00:00"

KLINE_COLS = [
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


def ms(s):
    return int(
        datetime.fromisoformat(s)
        .astimezone(timezone.utc)
        .timestamp() * 1000
    )


def fetch_3m(symbol):
    url = "https://fapi.binance.com/fapi/v1/klines"

    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "startTime": ms(FETCH_START),
        "endTime": ms(FETCH_END),
        "limit": 1500,
    }

    r = requests.get(
        url,
        params=params,
        timeout=20,
    )
    r.raise_for_status()

    raw = r.json()

    if not raw:
        raise RuntimeError(
            f"{symbol}: no data"
        )

    df = pd.DataFrame(
        raw,
        columns=KLINE_COLS,
    )

    for c in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]:
        df[c] = pd.to_numeric(
            df[c],
            errors="coerce",
        )

    for c in [
        "open_time",
        "close_time",
        "number_of_trades",
        "ignore",
    ]:
        df[c] = pd.to_numeric(
            df[c],
            errors="coerce",
        )

    df = (
        df.sort_values("open_time")
        .drop_duplicates("open_time")
        .reset_index(drop=True)
    )

    return df


meta = json.loads(
    META_PATH.read_text()
)

schema = list(
    meta["feature_schema"]
)

horizon = int(
    meta.get(
        "label_horizon",
        3,
    )
)

label_thr = float(
    meta.get(
        "label_thr",
        0.0005,
    )
)

model = load(MODEL_PATH)

print("===== CLOSED-BAR DOMAIN TEST =====")
print("trained_symbol=", meta.get("symbol"))
print("interval=", meta.get("interval"))
print("horizon=", horizon)
print("label_thr=", label_thr)
print("schema_len=", len(schema))
print("model_classes=", getattr(model, "classes_", None))
print()

summary_rows = []
raw_rows = []

for symbol in SYMBOLS:
    df = fetch_3m(symbol)

    X = make_matrix(
        df,
        schema=schema,
    )

    p = np.asarray(
        model.predict_proba(X),
        dtype=float,
    )[:, 1]

    df["model_score"] = p

    df["future_close"] = (
        df["close"]
        .shift(-horizon)
    )

    df["future_ret"] = (
        df["future_close"]
        / df["close"]
        - 1.0
    )

    df["label"] = (
        df["future_ret"]
        > label_thr
    ).astype(float)

    df.loc[
        df["future_close"].isna(),
        "label",
    ] = np.nan

    for window, (start_s, end_s) in WINDOWS.items():
        start_ms = ms(start_s)
        end_ms = ms(end_s)

        # Candle must be fully closed inside window.
        x = df[
            (df["close_time"] >= start_ms)
            & (df["close_time"] < end_ms)
        ].copy()

        x = x.dropna(
            subset=[
                "model_score",
                "future_ret",
                "label",
            ]
        )

        if x.empty:
            continue

        y = x["label"].astype(int)
        score = x["model_score"].astype(float)
        ret = x["future_ret"].astype(float)

        auc = (
            roc_auc_score(y, score)
            if y.nunique() > 1
            else np.nan
        )

        brier = brier_score_loss(
            y,
            score,
        )

        pearson = score.corr(ret)

        spearman = score.corr(
            ret,
            method="spearman",
        )

        long_mask = (
            score >= 0.525
        )

        long_n = int(
            long_mask.sum()
        )

        if long_n:
            long_precision = float(
                y[long_mask].mean()
            )

            long_avg_ret = float(
                ret[long_mask].mean()
            )
        else:
            long_precision = np.nan
            long_avg_ret = np.nan

        summary_rows.append({
            "symbol": symbol,
            "window": window,
            "n": len(x),
            "positive_rate": float(y.mean()),
            "score_mean": float(score.mean()),
            "score_std": float(score.std()),
            "auc": auc,
            "brier": brier,
            "pearson_return": pearson,
            "spearman_return": spearman,
            "long_n_ge_0525": long_n,
            "long_precision": long_precision,
            "long_avg_9m_ret_pct": (
                long_avg_ret * 100
                if pd.notna(long_avg_ret)
                else np.nan
            ),
        })

        for _, row in x.iterrows():
            raw_rows.append({
                "symbol": symbol,
                "window": window,
                "open_time": int(row["open_time"]),
                "close_time": int(row["close_time"]),
                "close": float(row["close"]),
                "model_score": float(row["model_score"]),
                "future_ret": float(row["future_ret"]),
                "label": int(row["label"]),
            })


summary = pd.DataFrame(
    summary_rows
)

raw_out = pd.DataFrame(
    raw_rows
)

# pooled per symbol
pooled_rows = []

for symbol, g in raw_out.groupby("symbol"):
    y = g["label"].astype(int)
    score = g["model_score"].astype(float)
    ret = g["future_ret"].astype(float)

    auc = (
        roc_auc_score(y, score)
        if y.nunique() > 1
        else np.nan
    )

    brier = brier_score_loss(
        y,
        score,
    )

    mask = score >= 0.525

    pooled_rows.append({
        "symbol": symbol,
        "n": len(g),
        "positive_rate": float(y.mean()),
        "score_mean": float(score.mean()),
        "score_std": float(score.std()),
        "auc": auc,
        "brier": brier,
        "pearson_return": score.corr(ret),
        "spearman_return": score.corr(
            ret,
            method="spearman",
        ),
        "long_n_ge_0525": int(mask.sum()),
        "long_precision": (
            float(y[mask].mean())
            if mask.any()
            else np.nan
        ),
        "long_avg_9m_ret_pct": (
            float(ret[mask].mean() * 100)
            if mask.any()
            else np.nan
        ),
    })


pooled = pd.DataFrame(
    pooled_rows
).sort_values(
    "auc",
    ascending=False,
)

OUT_DIR.mkdir(
    exist_ok=True,
)

summary_path = (
    OUT_DIR
    / "MODEL_DOMAIN_CLOSED_BY_WINDOW.csv"
)

pooled_path = (
    OUT_DIR
    / "MODEL_DOMAIN_CLOSED_POOLED.csv"
)

raw_path = (
    OUT_DIR
    / "MODEL_DOMAIN_CLOSED_RAW.csv"
)

summary.to_csv(
    summary_path,
    index=False,
)

pooled.to_csv(
    pooled_path,
    index=False,
)

raw_out.to_csv(
    raw_path,
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

print("===== POOLED BY SYMBOL =====")
print(
    pooled.round(5)
    .to_string(index=False)
)

print()
print("===== BTC vs LIVE UNIVERSE =====")

btc = pooled[
    pooled["symbol"] == "BTCUSDT"
]

alts = pooled[
    pooled["symbol"] != "BTCUSDT"
]

if len(btc):
    b = btc.iloc[0]
    print(
        "BTC AUC=",
        round(float(b["auc"]), 5),
        "Spearman=",
        round(float(b["spearman_return"]), 5),
        "LONG_precision=",
        round(float(b["long_precision"]), 5),
    )

print(
    "ALT mean AUC=",
    round(
        float(alts["auc"].mean()),
        5,
    ),
)

print(
    "ALT mean Spearman=",
    round(
        float(
            alts[
                "spearman_return"
            ].mean()
        ),
        5,
    ),
)

print()
print("SUMMARY=", summary_path)
print("POOLED=", pooled_path)
print("RAW=", raw_path)
print("MODEL_DOMAIN_CLOSED_COMPLETE")
