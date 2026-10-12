#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[2]

DATA = (
    ROOT
    / "research/results"
    / "NEAR_STRONG_SIGNAL_DATASET.csv.gz"
)

D1 = (
    ROOT
    / "data/offline_cache"
    / "NEARUSDT_1m_360d.csv"
)

OUT = (
    ROOT
    / "research/results"
    / "NEAR_DUAL_SIGNAL_GATE_WF.csv"
)

TP = 0.0025
SL = 0.0050
FEE = 0.0008
HORIZON = 10

QUANTILES = [
    0.60,
    0.70,
    0.80,
    0.90,
]

MIN_VAL_TRADES = 40


def economics(x):
    x = np.asarray(x, dtype=float)

    if len(x) == 0:
        return {
            "n": 0,
            "mean": np.nan,
            "median": np.nan,
            "win": np.nan,
            "pf": np.nan,
        }

    pos = x[x > 0].sum()
    neg = -x[x < 0].sum()

    return {
        "n": len(x),
        "mean": float(x.mean()),
        "median": float(np.median(x)),
        "win": float((x > 0).mean() * 100),
        "pf": float(pos / neg if neg > 0 else np.inf),
    }


ds = pd.read_csv(DATA)

# Only causal signal features.
feature_cols = [
    c
    for c in ds.columns
    if (
        c.startswith("m3_")
        or c.startswith("m5_")
        or c.startswith("m15_")
    )
]

if not feature_cols:
    raise SystemExit("NO_FEATURES")

print("===== INPUT =====")
print("ROWS=", len(ds))
print("FEATURES=", len(feature_cols))

d1 = pd.read_csv(D1)

ot = d1["open_time"].to_numpy(dtype=np.int64)
o = d1["open"].astype(float).to_numpy()
h = d1["high"].astype(float).to_numpy()
l = d1["low"].astype(float).to_numpy()
c = d1["close"].astype(float).to_numpy()

follow = np.zeros(len(ds), dtype=int)
danger = np.zeros(len(ds), dtype=int)
econ = np.zeros(len(ds), dtype=float)

for i, r in ds.iterrows():

    entry_time = int(r["entry_open_time"])

    idx = int(
        np.searchsorted(
            ot,
            entry_time,
            side="left",
        )
    )

    entry = float(o[idx])

    result = "HOLD"

    for k in range(HORIZON):

        j = idx + k

        sl_hit = (
            l[j] / entry - 1.0
            <= -SL
        )

        tp_hit = (
            h[j] / entry - 1.0
            >= TP
        )

        # Conservative same-minute ordering.
        if sl_hit:
            result = "SL"
            break

        if tp_hit:
            result = "TP"
            break

    if result == "TP":
        follow[i] = 1
        econ[i] = TP - FEE

    elif result == "SL":
        danger[i] = 1
        econ[i] = -SL - FEE

    else:
        exit_price = float(
            c[idx + HORIZON - 1]
        )

        econ[i] = (
            exit_price / entry
            - 1.0
            - FEE
        )

X = ds[feature_cols].to_numpy(float)

if not np.isfinite(X).all():
    raise SystemExit("BAD_FEATURE_VALUE")

n = len(ds)

print()
print("===== LABELS =====")
print(
    "FOLLOW_RATE=",
    round(follow.mean(), 5),
)
print(
    "DANGER_RATE=",
    round(danger.mean(), 5),
)
print(
    "RAW_ECON_PCT=",
    round(econ.mean() * 100, 5),
)

# Expanding chronological walk-forward.
FOLDS = [
    (0.50, 0.625, 0.75),
    (0.625, 0.75, 0.8333),
    (0.70, 0.8333, 0.9166),
    (0.75, 0.9166, 1.00),
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

    tr_end = int(n * train_frac)
    va_end = int(n * val_frac)
    te_end = int(n * test_frac)

    # Purge 10-minute future overlap.
    fit_end = max(
        tr_end - 3,
        1,
    )

    follow_model = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=15,
        min_samples_leaf=150,
        l2_regularization=5.0,
        early_stopping=False,
        random_state=42,
    )

    danger_model = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=15,
        min_samples_leaf=150,
        l2_regularization=5.0,
        early_stopping=False,
        random_state=43,
    )

    follow_model.fit(
        X[:fit_end],
        follow[:fit_end],
    )

    danger_model.fit(
        X[:fit_end],
        danger[:fit_end],
    )

    p_follow_val = follow_model.predict_proba(
        X[tr_end:va_end]
    )[:, 1]

    p_danger_val = danger_model.predict_proba(
        X[tr_end:va_end]
    )[:, 1]

    p_follow_test = follow_model.predict_proba(
        X[va_end:te_end]
    )[:, 1]

    p_danger_test = danger_model.predict_proba(
        X[va_end:te_end]
    )[:, 1]

    # Combined quality:
    # high follow probability,
    # low danger probability.
    qval = (
        p_follow_val
        - p_danger_val
    )

    qtest = (
        p_follow_test
        - p_danger_test
    )

    eval_val = econ[
        tr_end:va_end
    ]

    eval_test = econ[
        va_end:te_end
    ]

    best = None

    for q in QUANTILES:

        cut = float(
            np.quantile(
                qval,
                q,
            )
        )

        keep = (
            qval >= cut
        )

        ev = economics(
            eval_val[keep]
        )

        if ev["n"] < MIN_VAL_TRADES:
            continue

        cand = {
            "q": q,
            "cut": cut,
            "econ": ev,
        }

        if (
            best is None
            or ev["mean"]
            > best["econ"]["mean"]
        ):
            best = cand

    if best is None:
        raise SystemExit(
            f"NO_GATE_FOLD={fold_no}"
        )

    keep_test = (
        qtest >= best["cut"]
    )

    test_e = economics(
        eval_test[keep_test]
    )

    base_e = economics(
        eval_test
    )

    rows.append({
        "fold": fold_no,

        "selected_q":
            best["q"],

        "quality_cut":
            best["cut"],

        "val_n":
            best["econ"]["n"],

        "val_net_pct":
            best["econ"]["mean"] * 100,

        "base_test_n":
            base_e["n"],

        "base_net_pct":
            base_e["mean"] * 100,

        "gate_test_n":
            test_e["n"],

        "gate_net_pct":
            test_e["mean"] * 100,

        "gate_median_pct":
            test_e["median"] * 100,

        "gate_win_pct":
            test_e["win"],

        "gate_pf":
            test_e["pf"],

        "net_delta_pct":
            (
                test_e["mean"]
                - base_e["mean"]
            ) * 100,
    })


res = pd.DataFrame(rows)

print()
print("===== DUAL MODEL WALK FORWARD =====")

print(
    res.round(5)
    .to_string(index=False)
)

print()
print("===== SUMMARY =====")

delta = res["net_delta_pct"]

print(
    "POSITIVE_DELTA=",
    int((delta > 0).sum()),
    "/",
    len(delta),
)

print(
    "GATE_POSITIVE_FOLDS=",
    int(
        (
            res["gate_net_pct"]
            > 0
        ).sum()
    ),
    "/",
    len(res),
)

print(
    "MEAN_DELTA_PCT=",
    round(delta.mean(), 5),
)

print(
    "MEDIAN_DELTA_PCT=",
    round(delta.median(), 5),
)

weighted = (
    (
        res["gate_net_pct"]
        * res["gate_test_n"]
    ).sum()
    / res["gate_test_n"].sum()
)

print(
    "GATE_WEIGHTED_NET_PCT=",
    round(weighted, 5),
)

print(
    "GATE_WORST_FOLD=",
    round(
        res["gate_net_pct"].min(),
        5,
    ),
)

print(
    "GATE_TOTAL_TRADES=",
    int(
        res["gate_test_n"].sum()
    ),
)

res.to_csv(
    OUT,
    index=False,
)

print()
print("OUTPUT=", OUT)
print("DUAL_SIGNAL_GATE_WF_COMPLETE")
