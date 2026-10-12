#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]

D1 = ROOT / "data/offline_cache/NEARUSDT_1m_360d.csv"
D3 = ROOT / "data/offline_cache/NEARUSDT_3m_360d.csv"
OI = ROOT / "data/micro_context/NEARUSDT_oi_5m_29d.csv"
FU = ROOT / "data/micro_context/NEARUSDT_funding_29d.csv"

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
oi = pd.read_csv(OI)
fu = pd.read_csv(FU)

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

# ---------- OI ----------
oi["timestamp"] = pd.to_numeric(oi["timestamp"]).astype("int64")
oi["oi"] = pd.to_numeric(oi["sumOpenInterest"], errors="coerce")
oi["oiv"] = pd.to_numeric(oi["sumOpenInterestValue"], errors="coerce")

for n in (1, 3, 6):
    oi[f"oi_ret{n}"] = oi["oi"].pct_change(n)

oi["oiv_ret3"] = oi["oiv"].pct_change(3)
oi["oi_z288"] = zscore(oi["oi"], 288, 60)

oi_features = oi[
    [
        "timestamp",
        "oi_ret1",
        "oi_ret3",
        "oi_ret6",
        "oiv_ret3",
        "oi_z288",
    ]
].sort_values("timestamp")

# ---------- FUNDING ----------
fu["fundingTime"] = pd.to_numeric(
    fu["fundingTime"]
).astype("int64")

fu["funding"] = pd.to_numeric(
    fu["fundingRate"],
    errors="coerce",
)

fu["funding_change"] = fu["funding"].diff()
fu["funding_mean6"] = fu["funding"].rolling(
    6, min_periods=3
).mean()

fu["funding_z12"] = zscore(
    fu["funding"], 12, 6
)

fund_features = fu[
    [
        "fundingTime",
        "funding",
        "funding_change",
        "funding_mean6",
        "funding_z12",
    ]
].sort_values("fundingTime")

joint = pd.merge_asof(
    base,
    oi_features,
    left_on="close_time",
    right_on="timestamp",
    direction="backward",
)

joint = pd.merge_asof(
    joint.sort_values("close_time"),
    fund_features,
    left_on="close_time",
    right_on="fundingTime",
    direction="backward",
)

joint["funding_age_h"] = (
    joint["close_time"] - joint["fundingTime"]
) / 3_600_000.0

y, net, hit = barrier(d1)

joint = joint.iloc[:len(y)].copy()

micro_cols = [
    "oi_ret1",
    "oi_ret3",
    "oi_ret6",
    "oiv_ret3",
    "oi_z288",
    "funding",
    "funding_change",
    "funding_mean6",
    "funding_z12",
    "funding_age_h",
]

drop_cols = [
    "close_time",
    "timestamp",
    "fundingTime",
]

feature_cols = [
    c for c in joint.columns
    if c not in drop_cols
]

# Same rows for A and B.
valid = joint[feature_cols].notna().all(axis=1).to_numpy()

joint = joint.loc[valid].reset_index(drop=True)
y = y[valid]
net = net[valid]
hit = hit[valid]

base_cols = [
    c for c in feature_cols
    if c not in micro_cols
]

oi_cols = [
    "oi_ret1",
    "oi_ret3",
    "oi_ret6",
    "oiv_ret3",
    "oi_z288",
]

funding_cols = [
    "funding",
    "funding_change",
    "funding_mean6",
    "funding_z12",
    "funding_age_h",
]

X_A = joint[
    base_cols
].to_numpy(float)

X_OI = joint[
    base_cols + oi_cols
].to_numpy(float)

X_FUND = joint[
    base_cols + funding_cols
].to_numpy(float)

X_BOTH = joint[
    base_cols + oi_cols + funding_cols
].to_numpy(float)

n = len(y)

print("===== COMMON MODEL SAMPLE =====")
print("ROWS=", n)

MODELS = {
    "A_BASE": X_A,
    "D_OI_FUNDING": X_BOTH,
}

# Yaklaşık 27.8 günlük ortak örneği
# üç kronolojik fold'a bölüyoruz.
#
# FOLD1: train 40% / val 15% / test 15%
# FOLD2: train 55% / val 15% / test 15%
# FOLD3: train 70% / val 15% / test 15%
#
# Train expanding; VAL ve TEST daima gelecekte.

FOLDS = [
    (0.40, 0.55, 0.70),
    (0.55, 0.70, 0.85),
    (0.70, 0.85, 1.00),
]

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

    print()
    print(
        "FOLD",
        fold_no,
        "TRAIN=",
        fit_end,
        "VAL=",
        val_end - train_end,
        "TEST=",
        test_end - val_end,
    )

    for name, X in MODELS.items():

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
            X[train_end:val_end]
        )[:, 1]

        stest = model.predict_proba(
            X[val_end:test_end]
        )[:, 1]

        val_auc = roc_auc_score(
            y[train_end:val_end],
            sval,
        )

        test_auc = roc_auc_score(
            y[val_end:test_end],
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

            iv = dedup(
                np.flatnonzero(
                    sval >= cut
                )
            )

            if len(iv) < 20:
                continue

            rv = net[
                train_end:val_end
            ][iv]

            choices.append(
                (
                    float(rv.mean()),
                    q,
                    cut,
                    len(iv),
                )
            )

        if not choices:
            continue

        choices.sort(
            key=lambda z: z[0],
            reverse=True,
        )

        val_best_net, q, cut, val_n = choices[0]

        it = dedup(
            np.flatnonzero(
                stest >= cut
            )
        )

        rt = net[
            val_end:test_end
        ][it]

        ht = hit[
            val_end:test_end
        ][it]

        rows.append({
            "fold": fold_no,
            "model": name,
            "q": q,
            "cut": cut,
            "val_auc": val_auc,
            "test_auc": test_auc,
            "val_n": val_n,
            "test_n": len(it),
            "val_best_net_pct":
                val_best_net * 100,
            "test_net_avg_pct":
                rt.mean() * 100
                if len(rt)
                else np.nan,
            "test_net_median_pct":
                np.median(rt) * 100
                if len(rt)
                else np.nan,
            "test_win_pct":
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
print("===== NEAR MICRO WALK-FORWARD =====")

print(
    out.round(5)
    .to_string(index=False)
)

print()
print("===== D - A BY FOLD =====")

a = (
    out[out.model == "A_BASE"]
    .set_index("fold")
)

d = (
    out[out.model == "D_OI_FUNDING"]
    .set_index("fold")
)

delta = pd.DataFrame({
    "auc_delta":
        d.test_auc - a.test_auc,
    "net_delta":
        d.test_net_avg_pct
        - a.test_net_avg_pct,
    "median_delta":
        d.test_net_median_pct
        - a.test_net_median_pct,
    "win_delta":
        d.test_win_pct
        - a.test_win_pct,
    "tp_first_delta":
        d.tp_first_pct
        - a.tp_first_pct,
})

print(
    delta.round(5)
    .to_string()
)

print()
print("===== MODEL MEANS =====")

print(
    out.groupby("model")
    .agg(
        folds=("fold", "count"),
        total_test_n=("test_n", "sum"),
        mean_test_auc=("test_auc", "mean"),
        mean_test_net=("test_net_avg_pct", "mean"),
        median_test_net=("test_net_avg_pct", "median"),
        mean_win=("test_win_pct", "mean"),
        mean_tp_first=("tp_first_pct", "mean"),
    )
    .round(5)
    .to_string()
)

path = (
    ROOT
    / "replay_results"
    / "NEAR_MICRO_WALKFORWARD.csv"
)

out.to_csv(path, index=False)

print()
print("OUTPUT=", path)
print("NEAR_MICRO_WALKFORWARD_COMPLETE")
