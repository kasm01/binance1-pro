#!/usr/bin/env python3

from pathlib import Path
import sys
import json
import numpy as np
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from features.pipeline import make_matrix

SYMBOLS = [
    "DOGEUSDT",
    "SOLUSDT",
    "NEARUSDT",
]

# Ekonomik olarak daha mantıklı tek kontratla başlayalım.
CONFIG = {
    "1m": {
        "horizon": 15,
        "tp": 0.0020,
        "sl": 0.0015,
    },
    "3m": {
        "horizon": 10,
        "tp": 0.0020,
        "sl": 0.0015,
    },
}

FEE = 0.0008


def barrier(close, high, low, horizon, tp, sl):
    n = len(close) - horizon
    entry = close[:n]

    hit = np.zeros(n, dtype=np.int8)
    gross = np.zeros(n, dtype=float)

    for k in range(1, horizon + 1):
        active = hit == 0

        if not active.any():
            break

        hr = (
            high[k:k+n]
            / np.maximum(entry, 1e-12)
            - 1.0
        )

        lr = (
            low[k:k+n]
            / np.maximum(entry, 1e-12)
            - 1.0
        )

        tp_hit = active & (hr >= tp)
        sl_hit = active & (lr <= -sl)

        # Conservative:
        # both in same bar => SL first.
        loss = sl_hit
        win = tp_hit & ~sl_hit

        hit[loss] = -1
        gross[loss] = -sl

        hit[win] = 1
        gross[win] = tp

    timeout = hit == 0

    final_ret = (
        close[horizon:horizon+n]
        / np.maximum(entry, 1e-12)
        - 1.0
    )

    gross[timeout] = final_ret[timeout]

    y = (hit == 1).astype(int)
    net = gross - FEE

    return y, net, hit


def dedup(indices, cooldown):
    keep = []
    last = -10**18

    for i in indices:
        if i - last >= cooldown:
            keep.append(i)
            last = i

    return np.asarray(keep, dtype=int)


def make_sgd(y):
    n0 = max(int((y == 0).sum()), 1)
    n1 = max(int((y == 1).sum()), 1)

    sw = np.where(
        y == 1,
        0.5 / n1,
        0.5 / n0,
    )

    model = Pipeline([
        ("scaler", StandardScaler()),
        (
            "clf",
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

    return model, sw


def make_hgb():
    return HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=150,
        max_leaf_nodes=15,
        min_samples_leaf=100,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=42,
    )


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

        h = cfg["horizon"]

        y, net, hit = barrier(
            close,
            high,
            low,
            h,
            cfg["tp"],
            cfg["sl"],
        )

        X = Xall[:len(y)]

        finite = (
            np.isfinite(X).all(axis=1)
            & np.isfinite(net)
        )

        X = X[finite]
        y = y[finite]
        net = net[finite]
        hit = hit[finite]

        n = len(y)

        train_end = int(n * 0.70)
        val_end = int(n * 0.85)

        # Purge label horizon from train boundary.
        fit_end = max(
            train_end - h,
            1,
        )

        Xtr = X[:fit_end]
        ytr = y[:fit_end]

        Xval = X[train_end:val_end]
        yval = y[train_end:val_end]

        Xtest = X[val_end:]
        ytest = y[val_end:]
        ntest = net[val_end:]
        htest = hit[val_end:]

        models = {}

        sgd, sw = make_sgd(ytr)

        sgd.fit(
            Xtr,
            ytr,
            clf__sample_weight=sw,
        )

        models["SGD"] = sgd

        hgb = make_hgb()

        hgb.fit(
            Xtr,
            ytr,
        )

        models["HGB"] = hgb

        for name, model in models.items():

            val_score = model.predict_proba(
                Xval
            )[:, 1]

            test_score = model.predict_proba(
                Xtest
            )[:, 1]

            val_auc = roc_auc_score(
                yval,
                val_score,
            )

            test_auc = roc_auc_score(
                ytest,
                test_score,
            )

            # Threshold determined ONLY from VAL.
            # Test distribution is not used to choose it.
            cut = float(
                np.quantile(
                    val_score,
                    0.95,
                )
            )

            selected = np.flatnonzero(
                test_score >= cut
            )

            selected = dedup(
                selected,
                h,
            )

            if len(selected):
                sr = ntest[selected]
                sy = ytest[selected]
                sh = htest[selected]

                avg = float(sr.mean() * 100)
                med = float(np.median(sr) * 100)
                win = float((sr > 0).mean() * 100)
                tpfirst = float((sh == 1).mean() * 100)
            else:
                avg = med = win = tpfirst = np.nan

            rows.append({
                "symbol": symbol,
                "interval": interval,
                "model": name,
                "val_auc": val_auc,
                "test_auc": test_auc,
                "val_p95_cut": cut,
                "independent_n": len(selected),
                "tp_first_pct": tpfirst,
                "net_avg_pct": avg,
                "net_median_pct": med,
                "net_win_pct": win,
            })


out = pd.DataFrame(rows)

print("===== NONLINEAR MODEL COMPARISON =====")

print(
    out.sort_values(
        [
            "symbol",
            "interval",
            "model",
        ]
    )
    .round(5)
    .to_string(index=False)
)

print()
print("===== MODEL MEANS =====")

summary = (
    out.groupby("model")
    .agg(
        mean_val_auc=("val_auc", "mean"),
        mean_test_auc=("test_auc", "mean"),
        total_n=("independent_n", "sum"),
        mean_net=("net_avg_pct", "mean"),
        median_net=("net_avg_pct", "median"),
        mean_win=("net_win_pct", "mean"),
        mean_tp_first=("tp_first_pct", "mean"),
    )
)

print(
    summary.round(5)
    .to_string()
)

path = (
    ROOT
    / "replay_results"
    / "NONLINEAR_TRIPLE_BARRIER.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("NONLINEAR_AUDIT_COMPLETE")
