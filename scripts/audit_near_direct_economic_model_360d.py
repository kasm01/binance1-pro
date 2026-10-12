#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[1]

D1 = ROOT / "data/offline_cache/NEARUSDT_1m_360d.csv"
D3 = ROOT / "data/offline_cache/NEARUSDT_3m_360d.csv"

FEE = 0.0008
TP = 0.0040
SL = 0.0100
HOLD = 10
Q = 0.95
LABEL_H = 15
LABEL_TP = 0.0020
LABEL_SL = 0.0015


def zscore(s, n):
    m = s.rolling(n).mean()
    sd = s.rolling(n).std()
    return (s - m) / sd.replace(0, np.nan)


def features(df, prefix):
    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)

    v = df["volume"].astype(float)
    qv = df["quote_asset_volume"].astype(float)
    nt = df["number_of_trades"].astype(float)

    tb = df["taker_buy_base_volume"].astype(float)
    tq = df["taker_buy_quote_volume"].astype(float)

    x = pd.DataFrame(index=df.index)

    for n in (1, 3, 5, 10, 20):
        x[f"{prefix}_ret{n}"] = c.pct_change(n)

    rng = (h - l) / c.replace(0, np.nan)

    x[f"{prefix}_body"] = (
        (c - o) / o.replace(0, np.nan)
    )

    x[f"{prefix}_range"] = rng

    x[f"{prefix}_upper"] = (
        h
        - pd.concat([o, c], axis=1).max(axis=1)
    ) / c.replace(0, np.nan)

    x[f"{prefix}_lower"] = (
        pd.concat([o, c], axis=1).min(axis=1)
        - l
    ) / c.replace(0, np.nan)

    x[f"{prefix}_close_loc"] = (
        (c - l)
        / (h - l).replace(0, np.nan)
    )

    e5 = c.ewm(span=5, adjust=False).mean()
    e10 = c.ewm(span=10, adjust=False).mean()
    e20 = c.ewm(span=20, adjust=False).mean()

    x[f"{prefix}_de5"] = c / e5 - 1
    x[f"{prefix}_de10"] = c / e10 - 1
    x[f"{prefix}_de20"] = c / e20 - 1
    x[f"{prefix}_e5e20"] = e5 / e20 - 1
    x[f"{prefix}_e5s3"] = e5 / e5.shift(3) - 1
    x[f"{prefix}_e20s5"] = e20 / e20.shift(5) - 1

    pc = c.shift(1)

    tr = pd.concat(
        [
            h - l,
            (h - pc).abs(),
            (l - pc).abs(),
        ],
        axis=1,
    ).max(axis=1)

    x[f"{prefix}_atr"] = (
        tr.rolling(14).mean()
        / c.replace(0, np.nan)
    )

    r = c.pct_change()

    for n in (5, 10, 20):
        x[f"{prefix}_rv{n}"] = r.rolling(n).std()

    x[f"{prefix}_rexp"] = (
        rng / rng.rolling(20).mean()
    )

    x[f"{prefix}_vz"] = zscore(v, 20)
    x[f"{prefix}_qvz"] = zscore(qv, 20)
    x[f"{prefix}_ntz"] = zscore(nt, 20)

    br = tb / v.replace(0, np.nan)

    x[f"{prefix}_buy"] = br
    x[f"{prefix}_qbuy"] = (
        tq / qv.replace(0, np.nan)
    )
    x[f"{prefix}_imb"] = 2.0 * br - 1.0

    return x.replace(
        [np.inf, -np.inf],
        np.nan,
    )


def build_labels(df):
    c = df["close"].astype(float).to_numpy()
    h = df["high"].astype(float).to_numpy()
    l = df["low"].astype(float).to_numpy()

    y = np.zeros(len(df), dtype=int)

    for i in range(len(df) - LABEL_H):
        e = c[i]

        for k in range(1, LABEL_H + 1):
            loss = (
                l[i + k] / e - 1.0
                <= -LABEL_SL
            )

            win = (
                h[i + k] / e - 1.0
                >= LABEL_TP
            )

            if loss:
                y[i] = 0
                break

            if win:
                y[i] = 1
                break

    return y


def replay(df, idx):
    entry = float(df["close"].iloc[idx])

    end = min(
        idx + HOLD,
        len(df) - 1,
    )

    for j in range(idx + 1, end + 1):
        high = float(df["high"].iloc[j])
        low = float(df["low"].iloc[j])

        # conservative same-bar ordering
        if low / entry - 1.0 <= -SL:
            return -SL - FEE

        if high / entry - 1.0 >= TP:
            return TP - FEE

    close = float(df["close"].iloc[end])

    return (
        close / entry - 1.0
        - FEE
    )



# ============================================================
# DIRECT ECONOMIC MODEL — ALL ELIGIBLE TIMESTAMPS
# ============================================================

d1 = pd.read_csv(D1)
d3 = pd.read_csv(D3)

f1 = features(d1, "m1")
f3 = features(d3, "m3")

joint = pd.concat(
    [
        d1[["close_time"]],
        f1,
    ],
    axis=1,
).sort_values("close_time")

ctx3 = pd.concat(
    [
        d3[["close_time"]],
        f3,
    ],
    axis=1,
).sort_values("close_time")

joint = pd.merge_asof(
    joint,
    ctx3,
    on="close_time",
    direction="backward",
    allow_exact_matches=True,
)

feature_cols = [
    c
    for c in joint.columns
    if c != "close_time"
]

valid = (
    joint[feature_cols]
    .notna()
    .all(axis=1)
    .to_numpy()
)

idx_map = np.flatnonzero(valid)

X = (
    joint[feature_cols]
    .to_numpy(float)
)[valid]

times = (
    joint["close_time"]
    .to_numpy(dtype=np.int64)
)[valid]

# ------------------------------------------------------------
# Economic target for EVERY eligible timestamp.
#
# Conservative 1m OHLC ordering:
# SL checked before TP within a bar.
# ------------------------------------------------------------

economic = np.full(
    len(d1),
    np.nan,
    dtype=float,
)

for i in range(
    0,
    len(d1) - HOLD,
):
    economic[i] = replay(
        d1,
        i,
    )

y = economic[
    idx_map
]

target_ok = np.isfinite(y)

X = X[target_ok]
y = y[target_ok]
times = times[target_ok]
idx_map = idx_map[target_ok]

n = len(X)

print("===== DIRECT EV SAMPLE =====")
print("ROWS=", n)
print("FEATURES=", len(feature_cols))
print(
    "TARGET_MEAN_PCT=",
    round(
        y.mean() * 100,
        5,
    ),
)
print(
    "TARGET_POS_RATE=",
    round(
        (y > 0).mean(),
        6,
    ),
)

# Expanding chronological folds.
FOLDS = [
    (0.50, 0.5833, 0.6666),
    (0.5833, 0.6666, 0.7499),
    (0.6666, 0.7499, 0.8332),
    (0.7499, 0.8332, 0.9165),
]

QUANTILES = [
    0.90,
    0.95,
    0.975,
    0.99,
]

rows = []

for fold_no, (
    train_frac,
    val_frac,
    test_frac,
) in enumerate(
    FOLDS,
    start=1,
):
    train_end = int(
        n * train_frac
    )

    val_end = int(
        n * val_frac
    )

    test_end = int(
        n * test_frac
    )

    # Purge future economic horizon.
    fit_end = max(
        train_end - HOLD,
        1,
    )

    val_eval_end = max(
        val_end - HOLD,
        train_end + 1,
    )

    model = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_iter=250,
        max_leaf_nodes=31,
        min_samples_leaf=150,
        l2_regularization=5.0,
        loss="squared_error",
        early_stopping=False,
        random_state=42,
    )

    model.fit(
        X[:fit_end],
        y[:fit_end],
    )

    pval = model.predict(
        X[
            train_end:
            val_eval_end
        ]
    )

    ptest = model.predict(
        X[
            val_end:
            test_end
        ]
    )

    yval = y[
        train_end:
        val_eval_end
    ]

    ytest = y[
        val_end:
        test_end
    ]

    best = None

    for q in QUANTILES:
        cut = float(
            np.quantile(
                pval,
                q,
            )
        )

        idx = np.flatnonzero(
            pval >= cut
        )

        # Independent 15m spacing.
        dedup = []
        last = -10**18

        for x in idx:
            if x - last >= 15:
                dedup.append(
                    int(x)
                )
                last = int(x)

        if not dedup:
            continue

        r = yval[
            dedup
        ]

        candidate = {
            "q": q,
            "cut": cut,
            "n": len(r),
            "net": float(
                r.mean() * 100
            ),
        }

        if (
            best is None
            or candidate["net"]
            > best["net"]
        ):
            best = candidate

    if best is None:
        raise SystemExit(
            f"NO_VALID_GATE_FOLD={fold_no}"
        )

    idx = np.flatnonzero(
        ptest >= best["cut"]
    )

    dedup = []
    last = -10**18

    for x in idx:
        if x - last >= 15:
            dedup.append(
                int(x)
            )
            last = int(x)

    r = ytest[
        dedup
    ]

    if len(r):
        wins = r[
            r > 0
        ].sum()

        losses = -r[
            r < 0
        ].sum()

        pf = (
            wins / losses
            if losses > 0
            else np.inf
        )

        net = float(
            r.mean() * 100
        )

        med = float(
            np.median(r) * 100
        )

        win = float(
            (r > 0).mean()
            * 100
        )
    else:
        pf = np.nan
        net = np.nan
        med = np.nan
        win = np.nan

    corr = np.corrcoef(
        ptest,
        ytest,
    )[0, 1]

    rows.append({
        "fold": fold_no,
        "selected_q":
            best["q"],
        "cut":
            best["cut"],
        "val_n":
            best["n"],
        "val_net_pct":
            best["net"],
        "test_n":
            len(r),
        "test_net_pct":
            net,
        "test_median_pct":
            med,
        "win_pct":
            win,
        "profit_factor":
            pf,
        "test_corr":
            corr,
    })


res = pd.DataFrame(rows)

print()
print("===== DIRECT EV WALK FORWARD =====")

print(
    res.round(5)
    .to_string(index=False)
)

print()
print("===== SUMMARY =====")

print(
    "POSITIVE_FOLDS=",
    int(
        (
            res["test_net_pct"]
            > 0
        ).sum()
    ),
    "/",
    len(res),
)

print(
    "MEAN_NET_PCT=",
    round(
        res["test_net_pct"]
        .mean(),
        5,
    ),
)

print(
    "MEDIAN_NET_PCT=",
    round(
        res["test_net_pct"]
        .median(),
        5,
    ),
)

print(
    "WORST_FOLD=",
    round(
        res["test_net_pct"]
        .min(),
        5,
    ),
)

weighted = (
    (
        res["test_net_pct"]
        * res["test_n"]
    ).sum()
    / res["test_n"].sum()
)

print(
    "WEIGHTED_NET_PCT=",
    round(
        weighted,
        5,
    ),
)

print(
    "TOTAL_TEST_TRADES=",
    int(
        res["test_n"]
        .sum()
    ),
)

print(
    "MEAN_CORR=",
    round(
        res["test_corr"]
        .mean(),
        5,
    ),
)

path = (
    ROOT
    / "replay_results"
    / "NEAR_DIRECT_ECONOMIC_MODEL_360D.csv"
)

res.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)

print(
    "NEAR_DIRECT_ECONOMIC_MODEL_360D_COMPLETE"
)
