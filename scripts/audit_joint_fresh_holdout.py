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

SYMBOLS = [
    "SOLUSDT",
    "XRPUSDT",
    "NEARUSDT",
    "SUIUSDT",
    "DOGEUSDT",
    "LINKUSDT",
    "AVAXUSDT",
]
INTERVALS = ["1m", "3m"]

THR_1M = [0.50, 0.525, 0.55, 0.575, 0.60]
THR_3M = [0.50, 0.525, 0.55, 0.575, 0.60]

MIN_VAL_SIGNALS = 30

# fee sensitivity, underlying return basis
FEE_RT = [
    0.0004,  # optimistic total round trip
    0.0008,  # 0.04% each side
    0.0010,  # higher-fee/slippage proxy
]


def build_dataset(symbol, interval):
    meta_path = (
        ROOT / "models"
        / f"model_meta_{symbol}_{interval}.json"
    )

    data_path = (
        ROOT / "data/offline_cache"
        / f"{symbol}_{interval}_6m.csv"
    )

    meta = json.loads(meta_path.read_text())
    schema = list(meta["feature_schema"])

    horizon = int(meta["label_horizon"])
    label_thr = float(meta["label_thr"])

    df = pd.read_csv(data_path)

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

    ret = future / np.maximum(
        close,
        1e-12,
    ) - 1.0

    y = (
        ret > label_thr
    ).astype(int)

    if horizon > 0:
        X = X[:-horizon]
        y = y[:-horizon]
        ret = ret[:-horizon]
        df = df.iloc[:-horizon].copy()

    finite = (
        np.isfinite(X).all(axis=1)
        & np.isfinite(ret)
    )

    X = X[finite]
    y = y[finite]

    df = (
        df.loc[finite]
        .reset_index(drop=True)
    )

    return df, X, y


def fit_research_model(X, y, train_end):
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

    w0 = 0.5 / n0
    w1 = 0.5 / n1

    sw = np.where(
        ytr == 1,
        w1,
        w0,
    )

    model = Pipeline([
        (
            "scaler",
            StandardScaler(
                with_mean=True,
                with_std=True,
            ),
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

    return model


def scored_frame(symbol, interval):
    df, X, y = build_dataset(
        symbol,
        interval,
    )

    n = len(df)

    train_end = int(
        n * 0.70
    )

    val_end = int(
        n * 0.85
    )

    model = fit_research_model(
        X,
        y,
        train_end,
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


def align_symbol(symbol):
    d1 = scored_frame(
        symbol,
        "1m",
    ).sort_values("close_time")

    d3 = scored_frame(
        symbol,
        "3m",
    ).sort_values("close_time")

    for mins in (3, 9, 15):
        d1[f"ret_{mins}m"] = (
            d1["close"].shift(-mins)
            / d1["close"]
            - 1.0
        )

    d3 = d3.rename(columns={
        "score": "score_3m",
        "segment": "segment_3m",
    })

    m = pd.merge_asof(
        d1.sort_values("close_time"),
        d3[
            [
                "close_time",
                "score_3m",
                "segment_3m",
            ]
        ].sort_values("close_time"),
        on="close_time",
        direction="backward",
        allow_exact_matches=True,
    )

    m = m.rename(columns={
        "score": "score_1m",
        "segment": "segment_1m",
    })

    return m.dropna(
        subset=[
            "score_1m",
            "score_3m",
            "ret_3m",
            "ret_9m",
            "ret_15m",
        ]
    )


def metrics(df):
    n = len(df)

    if n == 0:
        return None

    out = {
        "signals": n,
    }

    for mins in (3, 9, 15):
        r = df[f"ret_{mins}m"]

        out[f"avg_{mins}m_pct"] = (
            float(r.mean()) * 100
        )

        out[f"median_{mins}m_pct"] = (
            float(r.median()) * 100
        )

        out[f"win_{mins}m_pct"] = (
            float((r > 0).mean()) * 100
        )

    for fee in FEE_RT:
        key = str(
            int(round(fee * 10000))
        ) + "bps"

        out[
            f"net9m_{key}_pct"
        ] = (
            float(
                (
                    df["ret_9m"]
                    - fee
                ).mean()
            )
            * 100
        )

    return out


all_results = []

for symbol in SYMBOLS:
    m = align_symbol(symbol)

    val = m[
        (m["segment_1m"] == "VAL")
        & (
            m["segment_3m"]
            .isin(["TRAIN", "VAL"])
        )
    ].copy()

    test = m[
        (m["segment_1m"] == "TEST")
        & (m["segment_3m"] == "TEST")
    ].copy()

    candidates = []

    for t3 in THR_3M:
        for t1 in THR_1M:
            x = val[
                (val["score_3m"] >= t3)
                & (val["score_1m"] >= t1)
            ]

            mt = metrics(x)

            if (
                mt is None
                or mt["signals"]
                < MIN_VAL_SIGNALS
            ):
                continue

            candidates.append({
                "thr_3m": t3,
                "thr_1m": t1,
                **mt,
            })

    cdf = pd.DataFrame(candidates)

    if cdf.empty:
        print(
            symbol,
            "NO_VALID_THRESHOLD"
        )
        continue

    # Select using validation only.
    # Primary objective:
    # 8 bps fee-adjusted 9m average.
    best = (
        cdf.sort_values(
            [
                "net9m_8bps_pct",
                "signals",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .iloc[0]
    )

    t3 = float(best["thr_3m"])
    t1 = float(best["thr_1m"])

    xtest = test[
        (test["score_3m"] >= t3)
        & (test["score_1m"] >= t1)
    ]

    test_mt = metrics(
        xtest
    )

    print()
    print(
        "========================================"
    )
    print(symbol)
    print(
        "========================================"
    )

    print(
        "SELECTED_ON_VAL:",
        "3m>=",
        t3,
        "1m>=",
        t1,
    )

    print(
        "VAL:",
        {
            k: round(float(v), 5)
            for k, v in best.to_dict().items()
        },
    )

    print(
        "FINAL_TEST:",
        None
        if test_mt is None
        else {
            k: round(float(v), 5)
            for k, v in test_mt.items()
        },
    )

    if test_mt is not None:
        all_results.append({
            "symbol": symbol,
            "thr_3m": t3,
            "thr_1m": t1,
            **{
                f"test_{k}": v
                for k, v
                in test_mt.items()
            },
        })

out = pd.DataFrame(
    all_results
)

path = (
    ROOT
    / "replay_results"
    / "JOINT_FRESH_HOLDOUT.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("===== FINAL FRESH HOLDOUT =====")

if not out.empty:
    print(
        out.round(5)
        .to_string(index=False)
    )

print()
print("OUTPUT=", path)
print("FRESH_HOLDOUT_COMPLETE")
