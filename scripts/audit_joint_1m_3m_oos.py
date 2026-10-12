#!/usr/bin/env python3

from pathlib import Path
import sys, json
import numpy as np
import pandas as pd
from joblib import load

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.pipeline import make_matrix

SYMBOLS = ["SOLUSDT", "XRPUSDT"]

THR_1M = [0.50, 0.525, 0.55, 0.575, 0.60]
THR_3M = [0.50, 0.525, 0.55, 0.575, 0.60]

def load_scored(symbol, interval):
    meta_path = ROOT / "models" / f"model_meta_{symbol}_{interval}.json"
    model_path = ROOT / "models" / f"online_model_{symbol}_{interval}_best.joblib"
    data_path = ROOT / "data/offline_cache" / f"{symbol}_{interval}_6m.csv"

    meta = json.loads(meta_path.read_text())
    df = pd.read_csv(data_path)

    schema = list(meta["feature_schema"])
    horizon = int(meta["label_horizon"])

    X = make_matrix(df, schema=schema)

    if horizon > 0:
        df = df.iloc[:-horizon].copy()
        X = X[:-horizon]

    finite = np.isfinite(X).all(axis=1)
    df = df.loc[finite].reset_index(drop=True)
    X = X[finite]

    split = int(len(df) * 0.8)

    df = df.iloc[split:].copy()
    X = X[split:]

    model = load(model_path)
    df["score"] = model.predict_proba(X)[:, 1]

    df["close_time"] = pd.to_numeric(
        df["close_time"],
        errors="coerce"
    ).astype("int64")

    df["close"] = pd.to_numeric(
        df["close"],
        errors="coerce"
    ).astype(float)

    return df[["close_time", "close", "score"]].copy()


def add_future_returns(df):
    # 1m data: 3, 9, 15 minute horizons
    for mins in (3, 9, 15):
        df[f"ret_{mins}m"] = (
            df["close"].shift(-mins) / df["close"] - 1.0
        )
    return df


rows = []

for symbol in SYMBOLS:
    d1 = load_scored(symbol, "1m").sort_values("close_time")
    d3 = load_scored(symbol, "3m").sort_values("close_time")

    d1 = add_future_returns(d1)

    merged = pd.merge_asof(
        d1.sort_values("close_time"),
        d3[["close_time", "score"]]
          .rename(columns={"score": "score_3m"})
          .sort_values("close_time"),
        on="close_time",
        direction="backward",
        allow_exact_matches=True,
    )

    merged = merged.rename(
        columns={"score": "score_1m"}
    )

    merged = merged.dropna(
        subset=["score_1m", "score_3m", "ret_3m", "ret_9m", "ret_15m"]
    )

    print()
    print("=====", symbol, "=====")
    print("OOS_ALIGNED_ROWS=", len(merged))

    for t3 in THR_3M:
        for t1 in THR_1M:
            m = (
                (merged["score_3m"] >= t3)
                & (merged["score_1m"] >= t1)
            )

            x = merged[m]
            n = len(x)

            if n == 0:
                continue

            row = {
                "symbol": symbol,
                "thr_3m": t3,
                "thr_1m": t1,
                "signals": n,
                "signal_pct": 100.0 * n / len(merged),
            }

            for mins in (3, 9, 15):
                r = x[f"ret_{mins}m"]

                row[f"avg_{mins}m_pct"] = float(r.mean() * 100)
                row[f"median_{mins}m_pct"] = float(r.median() * 100)
                row[f"win_{mins}m_pct"] = float((r > 0).mean() * 100)
                row[f"label005_{mins}m_pct"] = float(
                    (r > 0.0005).mean() * 100
                )

            rows.append(row)

out = pd.DataFrame(rows)

# Minimum sample count filter prevents tiny-sample "perfect" results.
usable = out[out["signals"] >= 30].copy()

for symbol in SYMBOLS:
    z = usable[usable["symbol"] == symbol].copy()

    print()
    print("===== BEST", symbol, "BY 9m AVG, n>=30 =====")

    cols = [
        "thr_3m",
        "thr_1m",
        "signals",
        "signal_pct",
        "avg_3m_pct",
        "avg_9m_pct",
        "median_9m_pct",
        "win_9m_pct",
        "label005_9m_pct",
        "avg_15m_pct",
    ]

    print(
        z.sort_values(
            ["avg_9m_pct", "signals"],
            ascending=[False, False],
        )[cols]
        .head(12)
        .round(5)
        .to_string(index=False)
    )

out_dir = ROOT / "replay_results"
out_dir.mkdir(exist_ok=True)

out.to_csv(
    out_dir / "JOINT_1M_3M_OOS_GRID.csv",
    index=False,
)

print()
print("OUTPUT=", out_dir / "JOINT_1M_3M_OOS_GRID.csv")
print("JOINT_OOS_COMPLETE")
