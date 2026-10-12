#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import json
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Allow direct execution:
#   python scripts/replay_long_historical.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env", override=False)

from app_paths import MODELS_DIR
from models.model_registry import ModelRegistry
from data.anomaly_detection import AnomalyDetector
from features.schema import normalize_to_schema

from main import (
    build_features,
    compute_atr_from_klines,
    _normalize_kline_df,
)

from core.trade_executor import TradeExecutor


BASE = Path("replay_data/sol_20260912_13")
AGG = BASE / "aggtrades"
OUT = Path("replay_results")
OUT.mkdir(exist_ok=True)

SYMBOL = "SOLUSDT"
INTERVAL = "3m"

TRT = timezone(timedelta(hours=3))

WINDOWS = {
    "A": (
        datetime(2026, 9, 12, 8, 40, tzinfo=TRT),
        datetime(2026, 9, 12, 14, 15, tzinfo=TRT),
    ),
    "B": (
        datetime(2026, 9, 12, 16, 15, tzinfo=TRT),
        datetime(2026, 9, 12, 20, 30, tzinfo=TRT),
    ),
    "C": (
        datetime(2026, 9, 13, 2, 35, tzinfo=TRT),
        datetime(2026, 9, 13, 12, 40, tzinfo=TRT),
    ),
}

KCOLS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_volume", "taker_buy_quote_volume", "ignore",
]

LONG_THRESHOLD = float(os.getenv("LONG_THRESHOLD", "0.525"))
OPEN_MIN_SCORE = float(os.getenv("OPEN_MIN_SCORE", "0.515"))

SNIPER_MIN = float(
    os.getenv("SNIPER_ENTRY_MIN_CANDLE_PROGRESS", "0.08")
)
SNIPER_MAX = float(
    os.getenv("SNIPER_ENTRY_MAX_CANDLE_PROGRESS", "0.52")
)

LEVERAGE = float(os.getenv("DEFAULT_ORDER_LEVERAGE", "3"))

META_PATH = Path(MODELS_DIR) / "model_meta_3m.json"
META = json.loads(META_PATH.read_text(encoding="utf-8"))
SCHEMA = META.get("feature_schema") or []

registry = ModelRegistry(model_dir=MODELS_DIR)
model = registry.get_hybrid(
    INTERVAL,
    model_dir=MODELS_DIR,
    logger=None,
)
anomaly = AnomalyDetector(logger=None)

te = TradeExecutor.__new__(TradeExecutor)
te.logger = None


def to_ms(dt):
    return int(dt.astimezone(timezone.utc).timestamp() * 1000)


def trt_str(ms):
    return datetime.fromtimestamp(
        ms / 1000,
        tz=timezone.utc,
    ).astimezone(TRT).strftime("%Y-%m-%d %H:%M:%S")


def load_klines(window):
    p = BASE / f"SOLUSDT_{window}_3m.json"
    rows = json.loads(p.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows, columns=KCOLS)
    return _normalize_kline_df(df)


def load_trades(window):
    p = AGG / f"SOLUSDT_{window}_aggTrades.json"
    rows = json.loads(p.read_text(encoding="utf-8"))

    out = []

    for x in rows:
        out.append({
            "ts": int(x["T"]),
            "price": float(x["p"]),
            "qty": float(x["q"]),
        })

    return out


def floor_ms(ts, period_ms):
    return (int(ts) // period_ms) * period_ms


def ceil_ms(ts, period_ms):
    return (
        (int(ts) + period_ms - 1)
        // period_ms
    ) * period_ms


def partial_bar(trades, start_ms, now_ms):
    xs = [
        x for x in trades
        if start_ms <= x["ts"] <= now_ms
    ]

    if not xs:
        return None

    prices = [x["price"] for x in xs]
    qtys = [x["qty"] for x in xs]

    return {
        "open_time": start_ms,
        "open": prices[0],
        "high": max(prices),
        "low": min(prices),
        "close": prices[-1],
        "volume": sum(qtys),
        "close_time": now_ms,
        "quote_asset_volume": sum(
            x["price"] * x["qty"]
            for x in xs
        ),
        "number_of_trades": len(xs),
        "taker_buy_base_volume": 0.0,
        "taker_buy_quote_volume": 0.0,
        "ignore": 0,
    }


def model_score_at(base_df, trades, now_ms):
    candle3 = floor_ms(now_ms, 180_000)

    closed = base_df[
        base_df["close_time"] < candle3
    ].copy()

    pb = partial_bar(
        trades,
        candle3,
        now_ms,
    )

    if pb is None:
        return None

    current = pd.DataFrame([pb])
    raw = pd.concat(
        [closed, current],
        ignore_index=True,
    )

    raw = _normalize_kline_df(raw)

    if len(raw) < 30:
        return None

    feat = build_features(raw)

    if SCHEMA:
        feat = normalize_to_schema(
            feat,
            SCHEMA,
            log_missing=None,
        )

    feat = anomaly.filter_anomalies(
        feat,
        schema=SCHEMA or None,
        context="historical_replay",
    )

    if feat is None or len(feat) == 0:
        return None

    X = feat.tail(500)

    probs, _debug = model.predict_proba(X)

    p = float(probs[-1])

    if not math.isfinite(p):
        return None

    atr = compute_atr_from_klines(raw)

    return {
        "model_score": p,
        "atr": float(atr),
        "price": float(pb["close"]),
    }


def confirmation_at(trades, now_ms, score, atr):
    candle1 = floor_ms(now_ms, 60_000)

    pb = partial_bar(
        trades,
        candle1,
        now_ms,
    )

    if pb is None:
        return None

    px = float(pb["close"])

    ctx = {
        "px_now": px,
        "candle_open": float(pb["open"]),
        "candle_high": float(pb["high"]),
        "candle_low": float(pb["low"]),
        "atr_val": float(atr),
        "entry_candle_interval": "1m",
        "entry_context_source": "historical_aggTrades",
    }

    result = te._evaluate_long_entry_confirmation(
        side="long",
        signal_score=float(score),
        open_min_score=float(OPEN_MIN_SCORE),
        market_context=ctx,
    )

    return result


def future_excursion(trades, entry_ts, entry_px, end_ms):
    future = [
        x for x in trades
        if entry_ts < x["ts"] <= end_ms
    ]

    if not future:
        return {
            "mfe_pct": None,
            "mae_pct": None,
        }

    prices = [x["price"] for x in future]

    hi = max(prices)
    lo = min(prices)

    mfe = (hi / entry_px) - 1.0
    mae = (lo / entry_px) - 1.0

    return {
        "mfe_pct": mfe,
        "mae_pct": mae,
        "mfe_roi_3x": mfe * LEVERAGE,
        "mae_roi_3x": mae * LEVERAGE,
    }


def run_window(name, start_dt, end_dt):
    print()
    print(f"===== WINDOW {name} =====")

    base_df = load_klines(name)
    trades = load_trades(name)

    start_ms = to_ms(start_dt)
    end_ms = to_ms(end_dt)

    # Skip incomplete first 3m candle.
    sim_start = ceil_ms(start_ms, 180_000)

    # Deterministic 3-second replay.
    # Jitter sensitivity comes in phase 2.
    step_ms = 3000

    rows = []

    for now_ms in range(
        sim_start + 5000,
        end_ms,
        step_ms,
    ):
        m = model_score_at(
            base_df,
            trades,
            now_ms,
        )

        if not m:
            continue

        score = float(m["model_score"])

        if score < LONG_THRESHOLD:
            continue

        progress = (
            (now_ms % 60_000)
            / 60_000.0
        )

        if progress < SNIPER_MIN:
            sniper = "PENDING_EARLY"
        elif progress > SNIPER_MAX:
            sniper = "PENDING_LATE"
        else:
            sniper = "PASS"

        confirm = None

        if sniper == "PASS":
            confirm = confirmation_at(
                trades,
                now_ms,
                score,
                m["atr"],
            )

        proposed = None
        reason = None
        quality = None
        retrace = None

        if isinstance(confirm, dict):
            details = confirm.get("details") or {}

            proposed = details.get(
                "proposed_action"
            )

            reason = confirm.get("reason")

            quality = details.get(
                "entry_quality"
            )

            retrace = details.get(
                "retrace_ratio"
            )

        entry_px = float(m["price"])

        exc = (
            future_excursion(
                trades,
                now_ms,
                entry_px,
                end_ms,
            )
            if sniper == "PASS"
            else {}
        )

        rows.append({
            "window": name,
            "time_trt": trt_str(now_ms),
            "timestamp_ms": now_ms,
            "model_score": score,
            "open_min_score": OPEN_MIN_SCORE,
            "price": entry_px,
            "sniper_progress": progress,
            "sniper": sniper,
            "confirm_runtime_reason": reason,
            "confirm_proposed": proposed,
            "entry_quality": quality,
            "retrace_ratio": retrace,
            **exc,
        })

    df = pd.DataFrame(rows)

    out = OUT / f"SOLUSDT_{name}_replay.csv"
    df.to_csv(out, index=False)

    print("rows=", len(df))
    print("output=", out)

    if len(df):
        print()
        print("SNIPER:")
        print(
            df["sniper"]
            .value_counts()
            .to_string()
        )

        valid = df[
            df["sniper"] == "PASS"
        ]

        print()
        print("CONFIRM PROPOSED:")

        if len(valid):
            print(
                valid["confirm_proposed"]
                .fillna("none")
                .value_counts()
                .to_string()
            )

            cols = [
                "time_trt",
                "model_score",
                "price",
                "sniper_progress",
                "confirm_proposed",
                "entry_quality",
                "retrace_ratio",
                "mfe_roi_3x",
                "mae_roi_3x",
            ]

            print()
            print(
                valid[cols]
                .head(20)
                .to_string(index=False)
            )


def main():
    print("===== LONG HISTORICAL REPLAY =====")
    print("symbol=", SYMBOL)
    print("interval=", INTERVAL)
    print("long_threshold=", LONG_THRESHOLD)
    print("open_min_score=", OPEN_MIN_SCORE)
    print("sniper=", SNIPER_MIN, SNIPER_MAX)
    print("leverage=", LEVERAGE)
    print("entry_confirm_shadow=",
          os.getenv("ENTRY_CONFIRM_SHADOW"))

    for name, (start, end) in WINDOWS.items():
        run_window(
            name,
            start,
            end,
        )

    print()
    print("REPLAY_COMPLETE")


if __name__ == "__main__":
    main()
