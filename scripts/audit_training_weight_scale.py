#!/usr/bin/env python3

from pathlib import Path
import sys
import json
import numpy as np
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.pipeline import make_matrix

SYMBOLS = [
    "SOLUSDT",
    "XRPUSDT",
    "NEARUSDT",
    "SUIUSDT",
    "DOGEUSDT",
]

INTERVALS = ["1m", "3m"]

MODES = [
    "current_tiny",
    "balanced_mean1",
    "unweighted",
]


def load_xy(symbol, interval):
    meta_path = (
        ROOT / "models"
        / f"model_meta_{symbol}_{interval}.json"
    )

    data_path = (
        ROOT / "data/offline_cache"
        / f"{symbol}_{interval}_6m.csv"
    )

    meta = json.loads(meta_path.read_text())
    df = pd.read_csv(data_path)

    schema = list(meta["feature_schema"])
    horizon = int(meta["label_horizon"])
    thr = float(meta["label_thr"])

    X = make_matrix(
        df,
        schema=schema,
    )

    close = pd.to_numeric(
        df["close"],
        errors="coerce",
    ).to_numpy(dtype=float)

    future = np.roll(close, -horizon)

    ret = (
        future
        / np.maximum(close, 1e-12)
        - 1.0
    )

    y = (ret > thr).astype(int)

    if horizon > 0:
        X = X[:-horizon]
        y = y[:-horizon]

    finite = np.isfinite(X).all(axis=1)

    return X[finite], y[finite]


def make_model():
    return Pipeline([
        (
            "scaler",
            StandardScaler(),
        ),
        (
            "sgd",
            SGDClassifier(
                loss="log_loss",
                penalty="l2",
                alpha=0.0001,
                max_iter=50,
                tol=0.001,
                shuffle=False,
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ])


rows = []

for symbol in SYMBOLS:
    for interval in INTERVALS:

        X, y = load_xy(
            symbol,
            interval,
        )

        split = int(
            len(y) * 0.8
        )

        Xtr = X[:split]
        ytr = y[:split]

        Xva = X[split:]
        yva = y[split:]

        n = len(ytr)

        n0 = max(
            int((ytr == 0).sum()),
            1,
        )

        n1 = max(
            int((ytr == 1).sum()),
            1,
        )

        for mode in MODES:
            model = make_model()

            if mode == "current_tiny":
                w0 = 0.5 / n0
                w1 = 0.5 / n1

                sw = np.where(
                    ytr == 1,
                    w1,
                    w0,
                )

            elif mode == "balanced_mean1":
                w0 = n / (2.0 * n0)
                w1 = n / (2.0 * n1)

                sw = np.where(
                    ytr == 1,
                    w1,
                    w0,
                )

            else:
                w0 = np.nan
                w1 = np.nan
                sw = None

            if sw is None:
                model.fit(
                    Xtr,
                    ytr,
                )
            else:
                model.fit(
                    Xtr,
                    ytr,
                    sgd__sample_weight=sw,
                )

            score = model.predict_proba(
                Xva
            )[:, 1]

            auc = roc_auc_score(
                yva,
                score,
            )

            brier = brier_score_loss(
                yva,
                score,
            )

            rows.append({
                "symbol": symbol,
                "interval": interval,
                "mode": mode,
                "auc": auc,
                "brier": brier,
                "positive_rate": float(
                    yva.mean()
                ),
                "score_mean": float(
                    score.mean()
                ),
                "score_std": float(
                    score.std()
                ),
                "score_p05": float(
                    np.quantile(score, 0.05)
                ),
                "score_p50": float(
                    np.quantile(score, 0.50)
                ),
                "score_p95": float(
                    np.quantile(score, 0.95)
                ),
                "score_min": float(
                    score.min()
                ),
                "score_max": float(
                    score.max()
                ),
                "train_weight_mean": (
                    float(sw.mean())
                    if sw is not None
                    else 1.0
                ),
                "w0": w0,
                "w1": w1,
            })


out = pd.DataFrame(rows)

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    300,
)

print("===== WEIGHT SCALE A/B/C =====")

for symbol in SYMBOLS:
    print()
    print("=====", symbol, "=====")

    z = out[
        out["symbol"] == symbol
    ]

    print(
        z[
            [
                "interval",
                "mode",
                "auc",
                "brier",
                "score_mean",
                "score_std",
                "score_p05",
                "score_p50",
                "score_p95",
                "score_min",
                "score_max",
                "train_weight_mean",
            ]
        ]
        .round(6)
        .to_string(index=False)
    )

print()
print("===== MODE MEANS =====")

print(
    out.groupby("mode")[
        [
            "auc",
            "brier",
            "score_std",
        ]
    ]
    .mean()
    .round(6)
    .to_string()
)

path = (
    ROOT
    / "replay_results"
    / "TRAINING_WEIGHT_SCALE_AUDIT.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("WEIGHT_SCALE_AUDIT_COMPLETE")
