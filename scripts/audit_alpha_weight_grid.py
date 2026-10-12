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
    "DOGEUSDT",
]

INTERVALS = ["1m", "3m"]

MODES = [
    "current_tiny",
    "balanced_mean1",
    "unweighted",
]

ALPHAS = [
    1e-6,
    1e-5,
    1e-4,
    1e-3,
    1e-2,
    1e-1,
    1.0,
    10.0,
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

    X = make_matrix(
        df,
        schema=list(meta["feature_schema"]),
    )

    close = pd.to_numeric(
        df["close"],
        errors="coerce",
    ).to_numpy(dtype=float)

    h = int(meta["label_horizon"])
    thr = float(meta["label_thr"])

    future = np.roll(close, -h)

    ret = (
        future
        / np.maximum(close, 1e-12)
        - 1.0
    )

    y = (ret > thr).astype(int)

    if h > 0:
        X = X[:-h]
        y = y[:-h]

    finite = np.isfinite(X).all(axis=1)

    return X[finite], y[finite]


def fit_eval(X, y, mode, alpha):
    split = int(len(y) * 0.8)

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
        sw = None

    model = Pipeline([
        (
            "scaler",
            StandardScaler(),
        ),
        (
            "sgd",
            SGDClassifier(
                loss="log_loss",
                penalty="l2",
                alpha=float(alpha),
                max_iter=50,
                tol=0.001,
                shuffle=False,
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ])

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

    return {
        "auc": float(auc),
        "brier": float(brier),
        "score_mean": float(score.mean()),
        "score_std": float(score.std()),
        "score_p05": float(
            np.quantile(score, 0.05)
        ),
        "score_p50": float(
            np.quantile(score, 0.50)
        ),
        "score_p95": float(
            np.quantile(score, 0.95)
        ),
    }


rows = []

for symbol in SYMBOLS:
    for interval in INTERVALS:
        X, y = load_xy(
            symbol,
            interval,
        )

        for mode in MODES:
            for alpha in ALPHAS:
                try:
                    r = fit_eval(
                        X,
                        y,
                        mode,
                        alpha,
                    )

                    rows.append({
                        "symbol": symbol,
                        "interval": interval,
                        "mode": mode,
                        "alpha": alpha,
                        **r,
                    })

                except Exception as e:
                    print(
                        "FAILED",
                        symbol,
                        interval,
                        mode,
                        alpha,
                        repr(e),
                    )


out = pd.DataFrame(rows)

print("===== BEST AUC PER SYMBOL / INTERVAL =====")

best = (
    out.sort_values(
        "auc",
        ascending=False,
    )
    .groupby(
        ["symbol", "interval"],
        as_index=False,
    )
    .first()
)

print(
    best[
        [
            "symbol",
            "interval",
            "mode",
            "alpha",
            "auc",
            "brier",
            "score_mean",
            "score_std",
            "score_p05",
            "score_p50",
            "score_p95",
        ]
    ]
    .round(6)
    .to_string(index=False)
)

print()
print("===== CURRENT BASELINE =====")

base = out[
    (out["mode"] == "current_tiny")
    & (out["alpha"] == 1e-4)
]

print(
    base[
        [
            "symbol",
            "interval",
            "auc",
            "brier",
            "score_mean",
            "score_std",
        ]
    ]
    .round(6)
    .to_string(index=False)
)

print()
print("===== MEAN BY MODE / ALPHA =====")

means = (
    out.groupby(
        ["mode", "alpha"],
        as_index=False,
    )[
        [
            "auc",
            "brier",
            "score_std",
        ]
    ]
    .mean()
    .sort_values(
        "auc",
        ascending=False,
    )
)

print(
    means.round(6)
    .to_string(index=False)
)

path = (
    ROOT
    / "replay_results"
    / "ALPHA_WEIGHT_GRID.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("ALPHA_WEIGHT_GRID_COMPLETE")
