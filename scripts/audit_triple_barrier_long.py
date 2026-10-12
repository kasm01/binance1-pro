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

CONFIG = {
    "1m": {
        "horizons": [9, 15],
        "tps": [0.0015, 0.0020],
        "sls": [0.0010, 0.0015],
        "step_ms": 60_000,
    },
    "3m": {
        "horizons": [5, 10],
        "tps": [0.0015, 0.0020],
        "sls": [0.0010, 0.0015],
        "step_ms": 180_000,
    },
}

FEE = 0.0008


def make_model():
    return Pipeline([
        ("scaler", StandardScaler()),
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


def barrier_outcome(close, high, low, horizon, tp, sl):
    n = len(close) - horizon

    entry = close[:n]

    hit = np.zeros(n, dtype=np.int8)
    exit_ret = np.zeros(n, dtype=float)

    for k in range(1, horizon + 1):
        active = hit == 0

        if not active.any():
            break

        hret = (
            high[k:k+n]
            / np.maximum(entry, 1e-12)
            - 1.0
        )

        lret = (
            low[k:k+n]
            / np.maximum(entry, 1e-12)
            - 1.0
        )

        tp_hit = active & (hret >= tp)
        sl_hit = active & (lret <= -sl)

        both = tp_hit & sl_hit

        # Conservative ambiguity handling:
        # same bar TP + SL => SL first.
        loss = sl_hit
        win = tp_hit & ~sl_hit

        hit[loss] = -1
        exit_ret[loss] = -sl

        hit[win] = 1
        exit_ret[win] = tp

    timeout = hit == 0

    final_ret = (
        close[horizon:horizon+n]
        / np.maximum(entry, 1e-12)
        - 1.0
    )

    exit_ret[timeout] = final_ret[timeout]

    y = (hit == 1).astype(int)

    net_ret = exit_ret - FEE

    return y, net_ret, hit


def dedup(idx, cooldown_bars):
    keep = []

    last = -10**18

    for i in idx:
        if i - last >= cooldown_bars:
            keep.append(i)
            last = i

    return np.asarray(keep, dtype=int)


rows = []

for symbol in SYMBOLS:
    for interval, cfg in CONFIG.items():

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

        high = pd.to_numeric(
            df["high"],
            errors="coerce",
        ).to_numpy(float)

        low = pd.to_numeric(
            df["low"],
            errors="coerce",
        ).to_numpy(float)

        for horizon in cfg["horizons"]:
            usable = len(df) - horizon

            X = Xall[:usable]

            finite = np.isfinite(X).all(axis=1)

            for tp in cfg["tps"]:
                for sl in cfg["sls"]:

                    y, net_ret, hit = barrier_outcome(
                        close,
                        high,
                        low,
                        horizon,
                        tp,
                        sl,
                    )

                    valid = (
                        finite
                        & np.isfinite(net_ret)
                    )

                    Xv = X[valid]
                    yv = y[valid]
                    rv = net_ret[valid]
                    hv = hit[valid]

                    n = len(yv)

                    train_end = int(n * 0.70)
                    val_end = int(n * 0.85)

                    # purge horizon rows before boundaries
                    fit_end = max(
                        train_end - horizon,
                        1,
                    )

                    Xtr = Xv[:fit_end]
                    ytr = yv[:fit_end]

                    if len(np.unique(ytr)) < 2:
                        continue

                    n0 = max(int((ytr == 0).sum()), 1)
                    n1 = max(int((ytr == 1).sum()), 1)

                    sw = np.where(
                        ytr == 1,
                        0.5 / n1,
                        0.5 / n0,
                    )

                    model = make_model()

                    model.fit(
                        Xtr,
                        ytr,
                        sgd__sample_weight=sw,
                    )

                    score = model.predict_proba(
                        Xv
                    )[:, 1]

                    test_start = val_end
                    test_score = score[test_start:]
                    test_y = yv[test_start:]
                    test_ret = rv[test_start:]
                    test_hit = hv[test_start:]

                    if len(np.unique(test_y)) < 2:
                        continue

                    auc = roc_auc_score(
                        test_y,
                        test_score,
                    )

                    # fixed top 5% ranking screen
                    cut = np.quantile(
                        test_score,
                        0.95,
                    )

                    selected = np.flatnonzero(
                        test_score >= cut
                    )

                    selected = dedup(
                        selected,
                        horizon,
                    )

                    sr = test_ret[selected]
                    sy = test_y[selected]
                    sh = test_hit[selected]

                    rows.append({
                        "symbol": symbol,
                        "interval": interval,
                        "horizon_bars": horizon,
                        "tp_pct": tp * 100,
                        "sl_pct": sl * 100,
                        "test_positive_rate":
                            float(test_y.mean()),
                        "auc": float(auc),
                        "independent_n":
                            int(len(selected)),
                        "tp_first_pct":
                            float((sh == 1).mean() * 100),
                        "sl_first_pct":
                            float((sh == -1).mean() * 100),
                        "timeout_pct":
                            float((sh == 0).mean() * 100),
                        "net_avg_pct":
                            float(sr.mean() * 100),
                        "net_median_pct":
                            float(np.median(sr) * 100),
                        "net_win_pct":
                            float((sr > 0).mean() * 100),
                    })


out = pd.DataFrame(rows)

print("===== BEST TRIPLE-BARRIER CONFIG =====")

best = (
    out.sort_values(
        [
            "net_avg_pct",
            "auc",
        ],
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
            "horizon_bars",
            "tp_pct",
            "sl_pct",
            "auc",
            "independent_n",
            "tp_first_pct",
            "sl_first_pct",
            "timeout_pct",
            "net_avg_pct",
            "net_median_pct",
            "net_win_pct",
        ]
    ]
    .round(5)
    .to_string(index=False)
)

print()
print("===== AGGREGATE CONFIG =====")

agg = (
    out.groupby(
        [
            "interval",
            "horizon_bars",
            "tp_pct",
            "sl_pct",
        ],
        as_index=False,
    )
    .agg(
        mean_auc=("auc", "mean"),
        total_n=("independent_n", "sum"),
        mean_net=("net_avg_pct", "mean"),
        median_net=("net_avg_pct", "median"),
        mean_win=("net_win_pct", "mean"),
    )
    .sort_values(
        ["mean_net", "mean_auc"],
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
    / "TRIPLE_BARRIER_LONG_AUDIT.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("TRIPLE_BARRIER_AUDIT_COMPLETE")
