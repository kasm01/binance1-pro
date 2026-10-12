#!/usr/bin/env python3

from pathlib import Path
import sys
import json
import numpy as np
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.pipeline import make_matrix

CONFIG = {
    "SOLUSDT":  {"thr_3m": 0.500, "thr_1m": 0.550},
    "XRPUSDT":  {"thr_3m": 0.525, "thr_1m": 0.525},
    "NEARUSDT": {"thr_3m": 0.525, "thr_1m": 0.500},
    "SUIUSDT":  {"thr_3m": 0.575, "thr_1m": 0.550},
    "DOGEUSDT": {"thr_3m": 0.575, "thr_1m": 0.550},
    "LINKUSDT": {"thr_3m": 0.525, "thr_1m": 0.575},
    "AVAXUSDT": {"thr_3m": 0.500, "thr_1m": 0.550},
}

FEES = [
    0.0004,
    0.0008,
    0.0010,
]

COOLDOWN_MS = 9 * 60 * 1000


def load_dataset(symbol, interval):
    meta_path = (
        ROOT / "models"
        / f"model_meta_{symbol}_{interval}.json"
    )

    data_path = (
        ROOT / "data/offline_cache"
        / f"{symbol}_{interval}_6m.csv"
    )

    meta = json.loads(
        meta_path.read_text()
    )

    df = pd.read_csv(
        data_path
    )

    schema = list(
        meta["feature_schema"]
    )

    horizon = int(
        meta["label_horizon"]
    )

    thr = float(
        meta["label_thr"]
    )

    X = make_matrix(
        df,
        schema=schema,
    )

    close = pd.to_numeric(
        df["close"],
        errors="coerce",
    ).to_numpy(dtype=float)

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

    if horizon > 0:
        X = X[:-horizon]
        y = y[:-horizon]
        df = df.iloc[:-horizon].copy()

    finite = np.isfinite(X).all(axis=1)

    return (
        df.loc[finite].reset_index(drop=True),
        X[finite],
        y[finite],
    )


def score_frame(symbol, interval):
    df, X, y = load_dataset(
        symbol,
        interval,
    )

    n = len(df)

    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    Xtr = X[:train_end]
    ytr = y[:train_end]

    n0 = max(
        int((ytr == 0).sum()),
        1,
    )

    n1 = max(
        int((ytr == 1).sum()),
        1,
    )

    sw = np.where(
        ytr == 1,
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
                alpha=0.0001,
                max_iter=50,
                tol=0.001,
                shuffle=False,
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ])

    model.fit(
        Xtr,
        ytr,
        sgd__sample_weight=sw,
    )

    score = model.predict_proba(X)[:, 1]

    out = pd.DataFrame({
        "close_time": pd.to_numeric(
            df["close_time"],
            errors="coerce",
        ).astype("int64"),
        "close": pd.to_numeric(
            df["close"],
            errors="coerce",
        ).astype(float),
        "score": score,
    })

    out["segment"] = "TRAIN"

    out.loc[
        train_end:val_end - 1,
        "segment",
    ] = "VAL"

    out.loc[
        val_end:,
        "segment",
    ] = "TEST"

    return out


def cooldown_filter(df):
    keep = []
    last_ts = None

    for idx, row in df.iterrows():
        ts = int(row["close_time"])

        if (
            last_ts is None
            or ts - last_ts >= COOLDOWN_MS
        ):
            keep.append(idx)
            last_ts = ts

    return df.loc[keep].copy()


rows = []

for symbol, cfg in CONFIG.items():
    d1 = (
        score_frame(symbol, "1m")
        .sort_values("close_time")
    )

    d3 = (
        score_frame(symbol, "3m")
        .sort_values("close_time")
    )

    for mins in (3, 9, 15):
        d1[f"ret_{mins}m"] = (
            d1["close"].shift(-mins)
            / d1["close"]
            - 1.0
        )

    d3 = d3.rename(
        columns={
            "score": "score_3m",
            "segment": "segment_3m",
        }
    )

    m = pd.merge_asof(
        d1,
        d3[
            [
                "close_time",
                "score_3m",
                "segment_3m",
            ]
        ],
        on="close_time",
        direction="backward",
        allow_exact_matches=True,
    )

    m = m.rename(
        columns={
            "score": "score_1m",
            "segment": "segment_1m",
        }
    )

    test = m[
        (m["segment_1m"] == "TEST")
        & (m["segment_3m"] == "TEST")
        & (m["score_1m"] >= cfg["thr_1m"])
        & (m["score_3m"] >= cfg["thr_3m"])
    ].dropna(
        subset=[
            "ret_3m",
            "ret_9m",
            "ret_15m",
        ]
    )

    raw_n = len(test)

    independent = cooldown_filter(
        test
    )

    n = len(independent)

    row = {
        "symbol": symbol,
        "raw_signals": raw_n,
        "independent_signals": n,
        "retention_pct": (
            100 * n / raw_n
            if raw_n
            else np.nan
        ),
    }

    for mins in (3, 9, 15):
        r = independent[
            f"ret_{mins}m"
        ]

        row[f"avg_{mins}m_pct"] = (
            float(r.mean() * 100)
            if n
            else np.nan
        )

        row[f"median_{mins}m_pct"] = (
            float(r.median() * 100)
            if n
            else np.nan
        )

        row[f"win_{mins}m_pct"] = (
            float((r > 0).mean() * 100)
            if n
            else np.nan
        )

    for fee in FEES:
        bps = int(
            round(fee * 10000)
        )

        row[
            f"net9m_{bps}bps_pct"
        ] = (
            float(
                (
                    independent["ret_9m"]
                    - fee
                ).mean()
                * 100
            )
            if n
            else np.nan
        )

    rows.append(row)


out = pd.DataFrame(
    rows
).sort_values(
    "net9m_8bps_pct",
    ascending=False,
)

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    260,
)

print(
    "===== NON-OVERLAPPING FINAL TEST ====="
)

print(
    out.round(5)
    .to_string(index=False)
)

path = (
    ROOT
    / "replay_results"
    / "FRESH_HOLDOUT_DEDUP_9M.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("DEDUP_TEST_COMPLETE")
