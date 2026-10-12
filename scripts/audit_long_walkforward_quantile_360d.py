#!/usr/bin/env python3

from pathlib import Path
import sys, json
import numpy as np
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier

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

QUANTILES = [
    0.50,
    0.60,
    0.70,
    0.80,
    0.90,
    0.95,
    0.975,
]

DAY = 86_400_000
COOLDOWN = 9 * 60_000
FEES = [0.0004, 0.0008, 0.0010]

COMMON_START = pd.Timestamp(
    "2025-09-19T20:24:00Z"
).value // 1_000_000

COMMON_END = pd.Timestamp(
    "2026-09-14T19:21:00Z"
).value // 1_000_000

FOLDS = [
    (180, 30, 30),
    (210, 30, 30),
    (240, 30, 30),
    (270, 30, None),
]


def load_data(symbol, interval):
    path = ROOT / "data/offline_cache" / (
        f"{symbol}_{interval}_360d.csv"
    )

    meta = json.loads(
        (
            ROOT / "models"
            / f"model_meta_{symbol}_{interval}.json"
        ).read_text()
    )

    df = pd.read_csv(path)

    schema = list(meta["feature_schema"])
    h = int(meta["label_horizon"])
    thr = float(meta["label_thr"])

    X = make_matrix(df, schema=schema)

    close = pd.to_numeric(
        df["close"],
        errors="coerce",
    ).to_numpy(float)

    ct = pd.to_numeric(
        df["close_time"],
        errors="coerce",
    ).to_numpy(np.int64)

    future = np.roll(close, -h)

    ret = (
        future / np.maximum(close, 1e-12)
        - 1.0
    )

    y = (ret > thr).astype(int)

    step = 60_000 if interval == "1m" else 180_000

    usable = len(df) - h

    df = df.iloc[:usable].copy()
    X = X[:usable]
    y = y[:usable]
    ct = ct[:usable]

    finite = np.isfinite(X).all(axis=1)

    return {
        "df": df.loc[finite].reset_index(drop=True),
        "X": X[finite],
        "y": y[finite],
        "ct": ct[finite],
        "label_end": ct[finite] + h * step,
    }


def model_fit(X, y):
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
            "sgd",
            SGDClassifier(
                loss="log_loss",
                penalty="l2",
                alpha=1e-4,
                max_iter=50,
                tol=0.001,
                shuffle=False,
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ])

    model.fit(
        X,
        y,
        sgd__sample_weight=sw,
    )

    return model


def dedup(df):
    keep = []
    last = None

    for idx, ts in zip(
        df.index,
        df["close_time"],
    ):
        ts = int(ts)

        if last is None or ts - last >= COOLDOWN:
            keep.append(idx)
            last = ts

    return df.loc[keep].copy()


def metrics(df):
    if len(df) == 0:
        return {}

    r9 = df["ret_9m"]

    return {
        "signals": len(df),
        "avg3": df["ret_3m"].mean() * 100,
        "avg9": r9.mean() * 100,
        "med9": r9.median() * 100,
        "win9": (r9 > 0).mean() * 100,
        "avg15": df["ret_15m"].mean() * 100,
        "med15": df["ret_15m"].median() * 100,
        "net4": (r9.mean() - FEES[0]) * 100,
        "net8": (r9.mean() - FEES[1]) * 100,
        "net10": (r9.mean() - FEES[2]) * 100,
    }


rows = []

for symbol in SYMBOLS:
    print("\n" + "=" * 70)
    print(symbol)
    print("=" * 70)

    d1 = load_data(symbol, "1m")
    d3 = load_data(symbol, "3m")

    for fold_no, (train_days, val_days, test_days) in enumerate(
        FOLDS,
        start=1,
    ):
        train_end = COMMON_START + train_days * DAY
        val_end = train_end + val_days * DAY

        if test_days is None:
            test_end = COMMON_END
        else:
            test_end = min(
                val_end + test_days * DAY,
                COMMON_END,
            )

        models = {}

        for name, d in (("1m", d1), ("3m", d3)):
            train_mask = (
                (d["ct"] >= COMMON_START)
                & (d["label_end"] < train_end)
            )

            models[name] = model_fit(
                d["X"][train_mask],
                d["y"][train_mask],
            )

        def scored(d, model):
            s = model.predict_proba(d["X"])[:, 1]

            out = pd.DataFrame({
                "close_time": d["ct"],
                "close": pd.to_numeric(
                    d["df"]["close"],
                    errors="coerce",
                ).to_numpy(float),
                "score": s,
                "label_end": d["label_end"],
            })

            return out.sort_values("close_time")

        s1 = scored(d1, models["1m"])
        s3 = scored(d3, models["3m"])

        for mins in (3, 9, 15):
            s1[f"ret_{mins}m"] = (
                s1["close"].shift(-mins)
                / s1["close"]
                - 1.0
            )

        s3 = s3.rename(
            columns={"score": "score_3m"}
        )

        joined = pd.merge_asof(
            s1,
            s3[["close_time", "score_3m"]],
            on="close_time",
            direction="backward",
        )

        val = joined[
            (joined["close_time"] >= train_end)
            & (joined["label_end"] < val_end)
        ].dropna()

        test = joined[
            (joined["close_time"] >= val_end)
            & (joined["close_time"] < test_end - 15 * 60_000)
        ].dropna()

        choices = []

        for q3 in QUANTILES:
            t3 = float(
                val["score_3m"].quantile(q3)
            )

            for q1 in QUANTILES:
                t1 = float(
                    val["score"].quantile(q1)
                )

                z = val[
                    (val["score_3m"] >= t3)
                    & (val["score"] >= t1)
                ]

                z = dedup(z)

                if len(z) < 30:
                    continue

                m = metrics(z)

                if m["med9"] <= 0:
                    continue

                choices.append(
                    (
                        m["net8"],
                        m["med9"],
                        m["signals"],
                        q3,
                        q1,
                        t3,
                        t1,
                    )
                )

        if not choices:
            print(
                f"FOLD={fold_no} NO_VALID_THRESHOLD"
            )
            continue

        choices.sort(reverse=True)

        (
            _,
            _,
            _,
            q3,
            q1,
            t3,
            t1,
        ) = choices[0]

        zt = test[
            (test["score_3m"] >= t3)
            & (test["score"] >= t1)
        ]

        raw_n = len(zt)
        zt = dedup(zt)
        m = metrics(zt)

        row = {
            "symbol": symbol,
            "fold": fold_no,
            "train_days": train_days,
            "q_3m": q3,
            "q_1m": q1,
            "thr_3m": t3,
            "thr_1m": t1,
            "raw_test": raw_n,
            **m,
        }

        rows.append(row)

        print(
            f"FOLD={fold_no} "
            f"q3={q3:.3f} "
            f"q1={q1:.3f} "
            f"thr3={t3:.6f} "
            f"thr1={t1:.6f} "
            f"ind={m.get('signals', 0)} "
            f"net8={m.get('net8', np.nan):+.4f}% "
            f"med9={m.get('med9', np.nan):+.4f}% "
            f"avg15={m.get('avg15', np.nan):+.4f}%"
        )


out = pd.DataFrame(rows)

path = (
    ROOT
    / "replay_results"
    / "LONG_360D_WALKFORWARD_QUANTILE.csv"
)

out.to_csv(path, index=False)

print("\n===== WALK-FORWARD SUMMARY =====")

summary = (
    out.groupby("symbol")
    .agg(
        folds=("fold", "count"),
        signals=("signals", "sum"),
        positive_folds=("net8", lambda x: int((x > 0).sum())),
        mean_net8=("net8", "mean"),
        median_net8=("net8", "median"),
        mean_med9=("med9", "mean"),
        mean_avg15=("avg15", "mean"),
    )
    .sort_values(
        ["positive_folds", "mean_net8"],
        ascending=False,
    )
)

print(summary.round(5).to_string())

print()
print("OUTPUT=", path)
print("WALKFORWARD_COMPLETE")
