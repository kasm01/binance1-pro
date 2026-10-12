#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]

SYMBOLS = [
    "DOGEUSDT",
    "SOLUSDT",
    "NEARUSDT",
]

HORIZON = 15
TP = 0.0020
SL = 0.0015
FEE = 0.0008

QUANTILES = [
    0.80,
    0.90,
    0.95,
    0.975,
]


def zscore(s, n):
    m = s.rolling(n).mean()
    sd = s.rolling(n).std()

    return (
        (s - m)
        / sd.replace(0, np.nan)
    )


def normalized_features(df, prefix):
    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)

    v = df["volume"].astype(float)
    qv = df["quote_asset_volume"].astype(float)
    nt = df["number_of_trades"].astype(float)

    tb = df["taker_buy_base_volume"].astype(float)
    tq = df["taker_buy_quote_volume"].astype(float)

    eps = 1e-12

    x = pd.DataFrame(index=df.index)

    for n in (1, 3, 5, 10, 20):
        x[f"{prefix}_ret{n}"] = c.pct_change(n)

    candle_range = (
        (h - l)
        / c.clip(lower=eps)
    )

    x[f"{prefix}_body"] = (
        (c - o)
        / o.clip(lower=eps)
    )

    x[f"{prefix}_range"] = candle_range

    x[f"{prefix}_upper"] = (
        h - pd.concat([o, c], axis=1).max(axis=1)
    ) / c.clip(lower=eps)

    x[f"{prefix}_lower"] = (
        pd.concat([o, c], axis=1).min(axis=1) - l
    ) / c.clip(lower=eps)

    x[f"{prefix}_close_loc"] = (
        (c - l)
        / (h - l).replace(0, np.nan)
    )

    ema5 = c.ewm(
        span=5,
        adjust=False,
    ).mean()

    ema10 = c.ewm(
        span=10,
        adjust=False,
    ).mean()

    ema20 = c.ewm(
        span=20,
        adjust=False,
    ).mean()

    x[f"{prefix}_dist_e5"] = c / ema5 - 1
    x[f"{prefix}_dist_e10"] = c / ema10 - 1
    x[f"{prefix}_dist_e20"] = c / ema20 - 1

    x[f"{prefix}_e5e20"] = (
        ema5 / ema20 - 1
    )

    x[f"{prefix}_e5_slope3"] = (
        ema5 / ema5.shift(3) - 1
    )

    x[f"{prefix}_e20_slope5"] = (
        ema20 / ema20.shift(5) - 1
    )

    prev_c = c.shift(1)

    tr = pd.concat(
        [
            h - l,
            (h - prev_c).abs(),
            (l - prev_c).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr14 = tr.rolling(14).mean()

    x[f"{prefix}_atr"] = (
        atr14 / c.clip(lower=eps)
    )

    r1 = c.pct_change()

    for n in (5, 10, 20):
        x[f"{prefix}_rv{n}"] = (
            r1.rolling(n).std()
        )

    x[f"{prefix}_range_exp"] = (
        candle_range
        / candle_range.rolling(20).mean()
    )

    x[f"{prefix}_vol_z"] = zscore(v, 20)
    x[f"{prefix}_qvol_z"] = zscore(qv, 20)
    x[f"{prefix}_trades_z"] = zscore(nt, 20)

    buy_ratio = (
        tb / v.replace(0, np.nan)
    )

    x[f"{prefix}_buy_ratio"] = buy_ratio

    x[f"{prefix}_buy_quote_ratio"] = (
        tq / qv.replace(0, np.nan)
    )

    x[f"{prefix}_imbalance"] = (
        2.0 * buy_ratio - 1.0
    )

    return x.replace(
        [np.inf, -np.inf],
        np.nan,
    )


def barrier(df):
    c = df["close"].astype(float).to_numpy()
    h = df["high"].astype(float).to_numpy()
    l = df["low"].astype(float).to_numpy()

    n = len(df) - HORIZON
    entry = c[:n]

    hit = np.zeros(
        n,
        dtype=np.int8,
    )

    gross = np.zeros(
        n,
        dtype=float,
    )

    for k in range(1, HORIZON + 1):
        active = hit == 0

        hr = (
            h[k:k+n]
            / np.maximum(entry, 1e-12)
            - 1.0
        )

        lr = (
            l[k:k+n]
            / np.maximum(entry, 1e-12)
            - 1.0
        )

        sl_hit = (
            active
            & (lr <= -SL)
        )

        tp_hit = (
            active
            & (hr >= TP)
        )

        # Conservative same-bar ambiguity.
        win = (
            tp_hit
            & ~sl_hit
        )

        hit[sl_hit] = -1
        gross[sl_hit] = -SL

        hit[win] = 1
        gross[win] = TP

    timeout = hit == 0

    terminal = (
        c[HORIZON:HORIZON+n]
        / np.maximum(entry, 1e-12)
        - 1.0
    )

    gross[timeout] = terminal[timeout]

    return (
        (hit == 1).astype(int),
        gross - FEE,
        hit,
    )


def dedup(indices):
    keep = []
    last = -10**18

    for i in indices:
        if i - last >= HORIZON:
            keep.append(i)
            last = i

    return np.asarray(
        keep,
        dtype=int,
    )


rows = []

for symbol in SYMBOLS:

    p1 = (
        ROOT
        / "data/offline_cache"
        / f"{symbol}_1m_360d.csv"
    )

    p3 = (
        ROOT
        / "data/offline_cache"
        / f"{symbol}_3m_360d.csv"
    )

    d1 = pd.read_csv(p1)
    d3 = pd.read_csv(p3)

    f1 = normalized_features(
        d1,
        "m1",
    )

    f3 = normalized_features(
        d3,
        "m3",
    )

    a = pd.concat(
        [
            d1[["close_time"]].copy(),
            f1,
        ],
        axis=1,
    ).sort_values("close_time")

    b = pd.concat(
        [
            d3[["close_time"]].copy(),
            f3,
        ],
        axis=1,
    ).sort_values("close_time")

    # Only last CLOSED 3m candle is visible.
    joint = pd.merge_asof(
        a,
        b,
        on="close_time",
        direction="backward",
        allow_exact_matches=True,
    )

    y, net, hit = barrier(d1)

    joint = joint.iloc[:len(y)].copy()

    valid = (
        joint.drop(
            columns=["close_time"]
        )
        .notna()
        .all(axis=1)
        .to_numpy()
    )

    X = (
        joint.drop(
            columns=["close_time"]
        )
        .to_numpy(dtype=float)
    )[valid]

    y = y[valid]
    net = net[valid]
    hit = hit[valid]

    n = len(y)

    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    fit_end = max(
        train_end - HORIZON,
        1,
    )

    Xtr = X[:fit_end]
    ytr = y[:fit_end]

    Xval = X[train_end:val_end]
    yval = y[train_end:val_end]

    Xtest = X[val_end:]
    ytest = y[val_end:]

    rval = net[train_end:val_end]
    rtest = net[val_end:]
    htest = hit[val_end:]

    model = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=250,
        max_leaf_nodes=31,
        min_samples_leaf=150,
        l2_regularization=2.0,
        early_stopping=False,
        random_state=42,
    )

    model.fit(
        Xtr,
        ytr,
    )

    sval = model.predict_proba(
        Xval
    )[:, 1]

    stest = model.predict_proba(
        Xtest
    )[:, 1]

    val_auc = roc_auc_score(
        yval,
        sval,
    )

    test_auc = roc_auc_score(
        ytest,
        stest,
    )

    choices = []

    for q in QUANTILES:
        cut = float(
            np.quantile(
                sval,
                q,
            )
        )

        idx = np.flatnonzero(
            sval >= cut
        )

        idx = dedup(idx)

        if len(idx) < 30:
            continue

        rv = rval[idx]

        choices.append(
            (
                float(rv.mean()),
                float(np.median(rv)),
                len(idx),
                q,
                cut,
            )
        )

    if not choices:
        continue

    choices.sort(
        reverse=True
    )

    (
        _,
        _,
        _,
        q,
        cut,
    ) = choices[0]

    idx = np.flatnonzero(
        stest >= cut
    )

    idx = dedup(idx)

    rt = rtest[idx]
    ht = htest[idx]

    rows.append({
        "symbol": symbol,
        "val_auc": val_auc,
        "test_auc": test_auc,
        "q": q,
        "cut": cut,
        "independent_n": len(idx),
        "tp_first_pct":
            (ht == 1).mean() * 100,
        "net_avg_pct":
            rt.mean() * 100,
        "net_median_pct":
            np.median(rt) * 100,
        "net_win_pct":
            (rt > 0).mean() * 100,
    })


out = pd.DataFrame(rows)

print(
    "===== JOINT 1m + CLOSED 3m HGB ====="
)

print(
    out.round(5)
    .to_string(index=False)
)

print()
print("===== SUMMARY =====")

print(
    out.agg(
        {
            "test_auc": "mean",
            "independent_n": "sum",
            "tp_first_pct": "mean",
            "net_avg_pct": "mean",
            "net_median_pct": "median",
            "net_win_pct": "mean",
        }
    )
    .round(5)
    .to_string()
)

path = (
    ROOT
    / "replay_results"
    / "JOINT_NORMALIZED_HGB.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("JOINT_NORMALIZED_AUDIT_COMPLETE")
