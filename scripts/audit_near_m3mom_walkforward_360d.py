#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

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

valid = (
    joint.drop(columns=["close_time"])
    .notna()
    .all(axis=1)
    .to_numpy()
)

idx_map = np.flatnonzero(valid)

X = (
    joint
    .drop(columns=["close_time"])
    .to_numpy(float)
)[valid]

times = (
    joint["close_time"]
    .to_numpy(dtype=np.int64)
)[valid]

y_full = build_labels(d1)
y = y_full[idx_map]

m3_ret3 = (
    joint["m3_ret3"]
    .to_numpy(float)
)[valid]

n = len(X)

print("===== SAMPLE =====")
print("ROWS=", n)

# expanding ~180d train, then rolling 30d val/test
FOLDS = [
    (0.50, 0.5833, 0.6666),
    (0.5833, 0.6666, 0.7499),
    (0.6666, 0.7499, 0.8332),
    (0.7499, 0.8332, 0.9165),
]

rows = []

for fold_no, (
    tr_frac,
    va_frac,
    te_frac,
) in enumerate(FOLDS, start=1):

    train_end = int(n * tr_frac)
    val_end = int(n * va_frac)
    test_end = int(n * te_frac)

    fit_end = max(
        train_end - LABEL_H,
        1,
    )

    val_eval_end = max(
        val_end - LABEL_H,
        train_end + 1,
    )

    model = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=250,
        max_leaf_nodes=31,
        min_samples_leaf=100,
        l2_regularization=2.0,
        early_stopping=False,
        random_state=42,
    )

    model.fit(
        X[:fit_end],
        y[:fit_end],
    )

    sval = model.predict_proba(
        X[train_end:val_eval_end]
    )[:, 1]

    stest = model.predict_proba(
        X[val_end:test_end]
    )[:, 1]

    cut = float(
        np.quantile(
            sval,
            Q,
        )
    )

    candidates = np.flatnonzero(
        stest >= cut
    )

    # 15m independent-entry spacing
    dedup = []
    last = -10**18

    for x in candidates:
        if x - last >= 15:
            dedup.append(x)
            last = x

    for gate_name in (
        "NONE",
        "M3_MOM",
    ):

        chosen = []

        for x in dedup:
            global_valid_idx = val_end + x

            if (
                gate_name == "M3_MOM"
                and m3_ret3[
                    global_valid_idx
                ] <= 0
            ):
                continue

            chosen.append(
                global_valid_idx
            )

        results = []

        for gx in chosen:
            raw_idx = int(
                idx_map[gx]
            )

            results.append(
                replay(
                    d1,
                    raw_idx,
                )
            )

        arr = np.asarray(
            results,
            dtype=float,
        )

        rows.append({
            "fold": fold_no,
            "gate": gate_name,
            "cut": cut,
            "trades": len(arr),
            "net_avg_pct":
                arr.mean() * 100
                if len(arr)
                else np.nan,
            "net_median_pct":
                np.median(arr) * 100
                if len(arr)
                else np.nan,
            "win_pct":
                (arr > 0).mean() * 100
                if len(arr)
                else np.nan,
        })

res = pd.DataFrame(rows)

print()
print("===== WALK FORWARD =====")

print(
    res.round(5)
    .to_string(index=False)
)

print()
print("===== PAIRED DELTA =====")

a = (
    res[res.gate == "NONE"]
    .set_index("fold")
)

b = (
    res[res.gate == "M3_MOM"]
    .set_index("fold")
)

delta = (
    b["net_avg_pct"]
    - a["net_avg_pct"]
)

paired = pd.DataFrame({
    "none": a["net_avg_pct"],
    "m3_mom": b["net_avg_pct"],
    "delta": delta,
    "n_none": a["trades"],
    "n_m3": b["trades"],
})

print(
    paired.round(5)
    .to_string()
)

print()
print("===== SUMMARY =====")

print(
    "POSITIVE_DELTA=",
    int((delta > 0).sum()),
    "/",
    len(delta),
)

print(
    "MEAN_DELTA_PCT=",
    round(delta.mean(), 5),
)

print(
    "MEDIAN_DELTA_PCT=",
    round(delta.median(), 5),
)

print(
    "M3_POSITIVE_FOLDS=",
    int(
        (
            b["net_avg_pct"]
            > 0
        ).sum()
    ),
    "/",
    len(b),
)

print(
    "M3_WORST_FOLD=",
    round(
        b["net_avg_pct"].min(),
        5,
    ),
)

path = (
    ROOT
    / "replay_results"
    / "NEAR_M3MOM_WALKFORWARD_360D.csv"
)

res.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("NEAR_M3MOM_WALKFORWARD_360D_COMPLETE")
