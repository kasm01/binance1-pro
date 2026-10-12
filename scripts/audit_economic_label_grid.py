#!/usr/bin/env python3

from pathlib import Path
import sys
import json
import numpy as np
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from features.pipeline import make_matrix

SYMBOLS = [
    "LINKUSDT",
    "NEARUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "SOLUSDT",
]

CONFIGS = {
    "1m": {
        "horizons": [3, 5, 9],
        "thresholds": [
            0.0008,
            0.0012,
            0.0015,
        ],
    },
    "3m": {
        "horizons": [2, 3, 5],
        "thresholds": [
            0.0008,
            0.0012,
            0.0015,
        ],
    },
}


def fit_model(X, y):
    n0 = max(int((y == 0).sum()), 1)
    n1 = max(int((y == 1).sum()), 1)

    sw = np.where(
        y == 1,
        0.5 / n1,
        0.5 / n0,
    )

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
                alpha=1e-4,
                max_iter=50,
                tol=0.001,
                shuffle=False,
                random_state=42,
            ),
        ),
    ])

    model.fit(
        X,
        y,
        sgd__sample_weight=sw,
    )

    return model


rows = []

for symbol in SYMBOLS:
    for interval, cfg in CONFIGS.items():

        path = (
            ROOT
            / "data/offline_cache"
            / f"{symbol}_{interval}_360d.csv"
        )

        meta = json.loads(
            (
                ROOT
                / "models"
                / f"model_meta_{symbol}_{interval}.json"
            ).read_text()
        )

        df = pd.read_csv(path)

        Xall = make_matrix(
            df,
            schema=list(meta["feature_schema"]),
        )

        close = pd.to_numeric(
            df["close"],
            errors="coerce",
        ).to_numpy(float)

        for horizon in cfg["horizons"]:
            future = np.roll(
                close,
                -horizon,
            )

            fret = (
                future
                / np.maximum(close, 1e-12)
                - 1.0
            )

            usable = len(df) - horizon

            X = Xall[:usable]
            ret = fret[:usable]

            finite = (
                np.isfinite(X).all(axis=1)
                & np.isfinite(ret)
            )

            X = X[finite]
            ret = ret[finite]

            split = int(
                len(X) * 0.80
            )

            Xtr = X[:split]
            Xte = X[split:]

            rtr = ret[:split]
            rte = ret[split:]

            for threshold in cfg["thresholds"]:

                ytr = (
                    rtr > threshold
                ).astype(int)

                yte = (
                    rte > threshold
                ).astype(int)

                if (
                    len(np.unique(ytr)) < 2
                    or len(np.unique(yte)) < 2
                ):
                    continue

                model = fit_model(
                    Xtr,
                    ytr,
                )

                score = model.predict_proba(
                    Xte
                )[:, 1]

                auc = roc_auc_score(
                    yte,
                    score,
                )

                top_mask = (
                    score
                    >= np.quantile(
                        score,
                        0.95,
                    )
                )

                top_ret = rte[top_mask]

                rows.append({
                    "symbol": symbol,
                    "interval": interval,
                    "horizon_bars": horizon,
                    "threshold_pct":
                        threshold * 100,
                    "positive_rate":
                        yte.mean(),
                    "auc": auc,
                    "score_std":
                        score.std(),
                    "top5_n":
                        len(top_ret),
                    "top5_avg_ret_pct":
                        top_ret.mean() * 100,
                    "top5_median_ret_pct":
                        np.median(top_ret) * 100,
                    "top5_win_pct":
                        (top_ret > 0).mean() * 100,
                    "top5_net8bps_pct":
                        (
                            top_ret.mean()
                            - 0.0008
                        ) * 100,
                })


out = pd.DataFrame(rows)

print(
    "===== BEST ECONOMIC LABEL PER SYMBOL / INTERVAL ====="
)

best = (
    out.sort_values(
        [
            "top5_net8bps_pct",
            "auc",
        ],
        ascending=False,
    )
    .groupby(
        [
            "symbol",
            "interval",
        ],
        as_index=False,
    )
    .first()
)

print(
    best[
        [
            "symbol",
            "interval",
            "horizon_bars",
            "threshold_pct",
            "positive_rate",
            "auc",
            "top5_n",
            "top5_avg_ret_pct",
            "top5_median_ret_pct",
            "top5_net8bps_pct",
        ]
    ]
    .round(5)
    .to_string(index=False)
)

print()
print(
    "===== AGGREGATE BY LABEL ====="
)

agg = (
    out.groupby(
        [
            "interval",
            "horizon_bars",
            "threshold_pct",
        ],
        as_index=False,
    )
    .agg(
        mean_auc=("auc", "mean"),
        mean_net8=(
            "top5_net8bps_pct",
            "mean",
        ),
        median_net8=(
            "top5_net8bps_pct",
            "median",
        ),
        mean_positive_rate=(
            "positive_rate",
            "mean",
        ),
    )
    .sort_values(
        [
            "mean_net8",
            "mean_auc",
        ],
        ascending=False,
    )
)

print(
    agg.round(5)
    .to_string(index=False)
)

path = (
    ROOT
    / "replay_results"
    / "ECONOMIC_LABEL_GRID.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("ECONOMIC_LABEL_GRID_COMPLETE")
