#!/usr/bin/env python3

from pathlib import Path
import sys
import json

import numpy as np
import pandas as pd
from joblib import load
from sklearn.metrics import (
    roc_auc_score,
    brier_score_loss,
)

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.pipeline import make_matrix

SYMBOLS = [
    "SOLUSDT",
    "XRPUSDT",
    "NEARUSDT",
]

INTERVALS = [
    "1m",
    "3m",
]

THRESHOLDS = [
    0.50,
    0.525,
    0.55,
    0.575,
    0.60,
    0.625,
    0.65,
]


def labels_from_close(close, horizon, thr):
    close = np.asarray(close, dtype=float)

    future = np.roll(
        close,
        -horizon,
    )

    ret = (
        future
        / np.maximum(close, 1e-12)
        - 1.0
    )

    y = (
        ret > thr
    ).astype(int)

    return y, ret


summary_rows = []
threshold_rows = []

for symbol in SYMBOLS:
    for interval in INTERVALS:

        meta_path = (
            ROOT
            / "models"
            / f"model_meta_{symbol}_{interval}.json"
        )

        model_path = (
            ROOT
            / "models"
            / f"online_model_{symbol}_{interval}_best.joblib"
        )

        data_path = (
            ROOT
            / "data"
            / "offline_cache"
            / f"{symbol}_{interval}_6m.csv"
        )

        meta = json.loads(
            meta_path.read_text()
        )

        schema = list(
            meta["feature_schema"]
        )

        horizon = int(
            meta["label_horizon"]
        )

        label_thr = float(
            meta["label_thr"]
        )

        df = pd.read_csv(
            data_path
        )

        X = make_matrix(
            df,
            schema=schema,
        )

        close = pd.to_numeric(
            df["close"],
            errors="coerce",
        ).to_numpy(dtype=float)

        y, future_ret = labels_from_close(
            close,
            horizon,
            label_thr,
        )

        # Match trainer contract:
        # future-less last H rows removed.
        if horizon > 0:
            X = X[:-horizon]
            y = y[:-horizon]
            future_ret = future_ret[:-horizon]

        finite = (
            np.isfinite(X).all(axis=1)
            & np.isfinite(future_ret)
        )

        X = X[finite]
        y = y[finite]
        future_ret = future_ret[finite]

        n = len(y)
        split = int(
            n * 0.8
        )

        X_val = X[split:]
        y_val = y[split:]
        ret_val = future_ret[split:]

        model = load(
            model_path
        )

        score = np.asarray(
            model.predict_proba(X_val),
            dtype=float,
        )[:, 1]

        auc = (
            roc_auc_score(
                y_val,
                score,
            )
            if len(np.unique(y_val)) > 1
            else np.nan
        )

        brier = brier_score_loss(
            y_val,
            score,
        )

        pearson = pd.Series(
            score
        ).corr(
            pd.Series(ret_val)
        )

        spearman = pd.Series(
            score
        ).corr(
            pd.Series(ret_val),
            method="spearman",
        )

        summary_rows.append({
            "symbol": symbol,
            "interval": interval,
            "n_val": len(y_val),
            "positive_rate": float(np.mean(y_val)),
            "score_mean": float(np.mean(score)),
            "score_std": float(np.std(score)),
            "score_min": float(np.min(score)),
            "score_p05": float(np.quantile(score, 0.05)),
            "score_p50": float(np.quantile(score, 0.50)),
            "score_p95": float(np.quantile(score, 0.95)),
            "score_max": float(np.max(score)),
            "auc": float(auc),
            "brier": float(brier),
            "pearson_return": float(pearson),
            "spearman_return": float(spearman),
        })

        for threshold in THRESHOLDS:
            mask = (
                score >= threshold
            )

            count = int(
                mask.sum()
            )

            if count:
                precision = float(
                    np.mean(y_val[mask])
                )

                avg_ret = float(
                    np.mean(ret_val[mask])
                )

                med_ret = float(
                    np.median(ret_val[mask])
                )
            else:
                precision = np.nan
                avg_ret = np.nan
                med_ret = np.nan

            threshold_rows.append({
                "symbol": symbol,
                "interval": interval,
                "threshold": threshold,
                "signals": count,
                "signal_pct": (
                    100.0 * count / len(score)
                ),
                "precision": precision,
                "baseline_positive_rate": float(
                    np.mean(y_val)
                ),
                "avg_forward_ret_pct": (
                    avg_ret * 100
                    if np.isfinite(avg_ret)
                    else np.nan
                ),
                "median_forward_ret_pct": (
                    med_ret * 100
                    if np.isfinite(med_ret)
                    else np.nan
                ),
            })


summary = pd.DataFrame(
    summary_rows
)

thresholds = pd.DataFrame(
    threshold_rows
)

out_dir = (
    ROOT
    / "replay_results"
)

out_dir.mkdir(
    exist_ok=True
)

summary.to_csv(
    out_dir
    / "SYMBOL_MODEL_OOS_SUMMARY.csv",
    index=False,
)

thresholds.to_csv(
    out_dir
    / "SYMBOL_MODEL_OOS_THRESHOLDS.csv",
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

print("===== OOS MODEL SUMMARY =====")

print(
    summary.round(6)
    .to_string(index=False)
)

print()
print("===== THRESHOLD ANALYSIS =====")

print(
    thresholds.round(6)
    .to_string(index=False)
)

print()
print("SYMBOL_MODEL_OOS_AUDIT_COMPLETE")
