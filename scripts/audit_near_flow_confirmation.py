#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]

D1 = ROOT / "data/offline_cache/NEARUSDT_1m_360d.csv"
D3 = ROOT / "data/offline_cache/NEARUSDT_3m_360d.csv"
FLOW = (
    ROOT
    / "data/micro_context/NEARUSDT_aggflow_1m_14d.csv"
)

HORIZON = 15
TP = 0.0020
SL = 0.0015
FEE = 0.0008
QUANTILES = [0.90, 0.95, 0.975, 0.99]


def zscore(s, n, minp=None):
    if minp is None:
        minp = n
    m = s.rolling(n, min_periods=minp).mean()
    sd = s.rolling(n, min_periods=minp).std()
    return (s - m) / sd.replace(0, np.nan)


def norm_features(df, p):
    o = df.open.astype(float)
    h = df.high.astype(float)
    l = df.low.astype(float)
    c = df.close.astype(float)
    v = df.volume.astype(float)
    qv = df.quote_asset_volume.astype(float)
    nt = df.number_of_trades.astype(float)
    tb = df.taker_buy_base_volume.astype(float)
    tq = df.taker_buy_quote_volume.astype(float)

    x = pd.DataFrame(index=df.index)

    for n in (1, 3, 5, 10, 20):
        x[f"{p}_ret{n}"] = c.pct_change(n)

    rng = (h - l) / c.replace(0, np.nan)

    x[f"{p}_body"] = (c - o) / o.replace(0, np.nan)
    x[f"{p}_range"] = rng

    x[f"{p}_upper"] = (
        h - pd.concat([o, c], axis=1).max(axis=1)
    ) / c.replace(0, np.nan)

    x[f"{p}_lower"] = (
        pd.concat([o, c], axis=1).min(axis=1) - l
    ) / c.replace(0, np.nan)

    x[f"{p}_close_loc"] = (
        (c - l) / (h - l).replace(0, np.nan)
    )

    e5 = c.ewm(span=5, adjust=False).mean()
    e10 = c.ewm(span=10, adjust=False).mean()
    e20 = c.ewm(span=20, adjust=False).mean()

    x[f"{p}_de5"] = c / e5 - 1
    x[f"{p}_de10"] = c / e10 - 1
    x[f"{p}_de20"] = c / e20 - 1
    x[f"{p}_e5e20"] = e5 / e20 - 1
    x[f"{p}_e5s3"] = e5 / e5.shift(3) - 1
    x[f"{p}_e20s5"] = e20 / e20.shift(5) - 1

    pc = c.shift(1)

    tr = pd.concat(
        [h-l, (h-pc).abs(), (l-pc).abs()],
        axis=1
    ).max(axis=1)

    x[f"{p}_atr"] = tr.rolling(14).mean() / c

    r = c.pct_change()

    for n in (5, 10, 20):
        x[f"{p}_rv{n}"] = r.rolling(n).std()

    x[f"{p}_rexp"] = rng / rng.rolling(20).mean()
    x[f"{p}_vz"] = zscore(v, 20)
    x[f"{p}_qvz"] = zscore(qv, 20)
    x[f"{p}_ntz"] = zscore(nt, 20)

    br = tb / v.replace(0, np.nan)

    x[f"{p}_buy"] = br
    x[f"{p}_qbuy"] = tq / qv.replace(0, np.nan)
    x[f"{p}_imb"] = 2 * br - 1

    return x.replace([np.inf, -np.inf], np.nan)


def barrier(df):
    c = df.close.astype(float).to_numpy()
    h = df.high.astype(float).to_numpy()
    l = df.low.astype(float).to_numpy()

    n = len(df) - HORIZON
    entry = c[:n]
    hit = np.zeros(n, dtype=np.int8)
    gross = np.zeros(n)

    for k in range(1, HORIZON + 1):
        active = hit == 0
        hr = h[k:k+n] / entry - 1
        lr = l[k:k+n] / entry - 1

        loss = active & (lr <= -SL)
        win = active & (hr >= TP) & ~loss

        hit[loss] = -1
        gross[loss] = -SL

        hit[win] = 1
        gross[win] = TP

    timeout = hit == 0
    terminal = c[HORIZON:HORIZON+n] / entry - 1
    gross[timeout] = terminal[timeout]

    return (hit == 1).astype(int), gross - FEE, hit


def dedup(idx):
    keep = []
    last = -10**18

    for i in idx:
        if i - last >= HORIZON:
            keep.append(i)
            last = i

    return np.asarray(keep, dtype=int)


d1 = pd.read_csv(D1)
d3 = pd.read_csv(D3)
flow = pd.read_csv(FLOW)

f1 = norm_features(d1, "m1")
f3 = norm_features(d3, "m3")

base = pd.concat(
    [d1[["close_time"]], f1],
    axis=1
).sort_values("close_time")

ctx3 = pd.concat(
    [d3[["close_time"]], f3],
    axis=1
).sort_values("close_time")

base = pd.merge_asof(
    base,
    ctx3,
    on="close_time",
    direction="backward",
    allow_exact_matches=True,
)

# ---------- AGGTRADE MICRO-FLOW ----------
flow["close_time"] = pd.to_numeric(
    flow["close_time"],
    errors="raise",
).astype("int64")

flow_cols = [
    "aggr_buy_count_ratio",
    "aggr_buy_qty_ratio",
    "signed_qty_imbalance",
    "aggr_buy_notional_ratio",
    "signed_notional_imbalance",
    "max_notional_share",
    "top5_notional_share",
    "aggtrade_count_ratio20",
    "total_notional_ratio20",
    "avg_trade_notional_ratio20",
    "p95_trade_notional_ratio20",
    "imbalance_mean3",
    "imbalance_mean5",
    "imbalance_accel3",
    "buy_ratio_mean3",
]

flow_features = (
    flow[
        ["close_time"] + flow_cols
    ]
    .sort_values("close_time")
    .copy()
)

# Model timestamp'inde yalnız kapanmış micro-flow dakikası görünür.
joint = pd.merge_asof(
    base.sort_values("close_time"),
    flow_features,
    on="close_time",
    direction="backward",
    allow_exact_matches=True,
)

y, net, hit = barrier(d1)

joint = joint.iloc[:len(y)].copy()

drop_cols = [
    "close_time",
]

feature_cols = [
    c for c in joint.columns
    if c not in drop_cols
]

# BASE ve FLOW tam olarak aynı timestamp satırlarını görsün.
valid = (
    joint[feature_cols]
    .notna()
    .all(axis=1)
    .to_numpy()
)

joint = (
    joint.loc[valid]
    .reset_index(drop=True)
)

y = y[valid]
net = net[valid]
hit = hit[valid]

base_cols = [
    c for c in feature_cols
    if c not in flow_cols
]

X_A = joint[
    base_cols
].to_numpy(float)

X_FLOW = joint[
    base_cols + flow_cols
].to_numpy(float)

n = len(y)

print("===== COMMON MODEL SAMPLE =====")
print("ROWS=", n)

FOLDS = [
    (0.40, 0.55, 0.70),
    (0.55, 0.70, 0.85),
    (0.70, 0.85, 1.00),
]

GATES = {
    "NONE":
        np.ones(n, dtype=bool),

    "IMB_NOW_POS":
        joint[
            "signed_notional_imbalance"
        ].to_numpy() > 0,

    "IMB3_POS":
        joint[
            "imbalance_mean3"
        ].to_numpy() > 0,

    "IMB_NOW_AND_3":
        (
            joint[
                "signed_notional_imbalance"
            ].to_numpy() > 0
        )
        &
        (
            joint[
                "imbalance_mean3"
            ].to_numpy() > 0
        ),

    "BUY50_AND_IMB3":
        (
            joint[
                "aggr_buy_notional_ratio"
            ].to_numpy() > 0.50
        )
        &
        (
            joint[
                "imbalance_mean3"
            ].to_numpy() > 0
        ),
}

rows = []

for fold_no, (tr_frac, va_frac, te_frac) in enumerate(
    FOLDS,
    start=1,
):
    train_end = int(n * tr_frac)
    val_end = int(n * va_frac)
    test_end = int(n * te_frac)

    fit_end = max(
        train_end - HORIZON,
        1,
    )

    val_eval_end = max(
        val_end - HORIZON,
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
        X_A[:fit_end],
        y[:fit_end],
    )

    sval = model.predict_proba(
        X_A[train_end:val_eval_end]
    )[:, 1]

    stest = model.predict_proba(
        X_A[val_end:test_end]
    )[:, 1]

    print()
    print(
        "FOLD",
        fold_no,
        "VAL=",
        len(sval),
        "TEST=",
        len(stest),
    )

    for q in QUANTILES:
        cut = float(
            np.quantile(
                sval,
                q,
            )
        )

        raw_idx = np.flatnonzero(
            stest >= cut
        )

        for gate_name, gate_mask in GATES.items():

            local_gate = gate_mask[
                val_end:test_end
            ]

            idx = raw_idx[
                local_gate[raw_idx]
            ]

            idx = dedup(idx)

            rt = net[
                val_end:test_end
            ][idx]

            ht = hit[
                val_end:test_end
            ][idx]

            rows.append({
                "fold": fold_no,
                "q": q,
                "gate": gate_name,
                "cut": cut,
                "test_n": len(idx),
                "net_avg_pct":
                    rt.mean() * 100
                    if len(rt)
                    else np.nan,
                "net_median_pct":
                    np.median(rt) * 100
                    if len(rt)
                    else np.nan,
                "win_pct":
                    (rt > 0).mean() * 100
                    if len(rt)
                    else np.nan,
                "tp_first_pct":
                    (ht == 1).mean() * 100
                    if len(ht)
                    else np.nan,
            })

out = pd.DataFrame(rows)

print()
print("===== FLOW ENTRY CONFIRMATION =====")

print(
    out.round(5)
    .to_string(index=False)
)

print()
print("===== GATE SUMMARY =====")

summary = (
    out.groupby("gate")
    .agg(
        cases=("gate", "count"),
        total_n=("test_n", "sum"),
        mean_net=("net_avg_pct", "mean"),
        median_net=("net_avg_pct", "median"),
        mean_win=("win_pct", "mean"),
        mean_tp=("tp_first_pct", "mean"),
    )
    .sort_values(
        "mean_net",
        ascending=False,
    )
)

print(
    summary.round(5)
    .to_string()
)

print()
print("===== DELTA vs NONE =====")

base = (
    out[out.gate == "NONE"]
    .set_index(["fold", "q"])
)

for gate_name in (
    "IMB_NOW_POS",
    "IMB3_POS",
    "IMB_NOW_AND_3",
    "BUY50_AND_IMB3",
):
    g = (
        out[out.gate == gate_name]
        .set_index(["fold", "q"])
    )

    delta = (
        g["net_avg_pct"]
        - base["net_avg_pct"]
    )

    print()
    print(gate_name)
    print(
        "POSITIVE=",
        int((delta > 0).sum()),
        "/",
        len(delta),
        "MEAN_DELTA=",
        round(delta.mean(), 5),
        "MEDIAN_DELTA=",
        round(delta.median(), 5),
    )

path = (
    ROOT
    / "replay_results"
    / "NEAR_FLOW_CONFIRMATION.csv"
)

out.to_csv(path, index=False)

print()
print("OUTPUT=", path)
print("NEAR_FLOW_CONFIRMATION_COMPLETE")
