#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[1]

DATA = (
    ROOT
    / "replay_results"
    / "NEAR_META_DATASET_360D.csv"
)

# Validation'da yalnız bu önceden belirlenmiş
# seçicilik seviyelerini test ediyoruz.
QUANTILES = [
    0.50,
    0.60,
    0.70,
    0.80,
    0.90,
]

MIN_VAL_TRADES = 25


def economics(g):
    if len(g) == 0:
        return {
            "n": 0,
            "net": np.nan,
            "median": np.nan,
            "win": np.nan,
            "pf": np.nan,
        }

    x = (
        g["realized_net_pct"]
        .to_numpy(float)
    )

    pos = x[x > 0].sum()
    neg = -x[x < 0].sum()

    return {
        "n": len(x),

        "net":
            float(np.mean(x)),

        "median":
            float(np.median(x)),

        "win":
            float(
                np.mean(x > 0)
                * 100
            ),

        "pf":
            float(
                pos / neg
                if neg > 0
                else np.inf
            ),
    }


df = pd.read_csv(DATA)

df = (
    df.sort_values(
        [
            "block",
            "entry_time",
        ]
    )
    .reset_index(drop=True)
)

# ---------------------------------------------
# Base model score normalization
# ---------------------------------------------

df["score_margin"] = (
    df["base_score"]
    - df["base_cut"]
)

df["score_ratio"] = (
    df["base_score"]
    / df["base_cut"].replace(0, np.nan)
    - 1.0
)

# ---------------------------------------------
# Strict leakage exclusions
# ---------------------------------------------

exclude = {
    "block",
    "entry_time",
    "raw_idx",

    "realized_net",
    "realized_net_pct",

    "meta_label",

    "base_cut",
}

feature_cols = [
    c
    for c in df.columns
    if c not in exclude
]

bad = [
    c
    for c in feature_cols
    if (
        "realized" in c.lower()
        or "label" in c.lower()
    )
]

if bad:
    raise SystemExit(
        f"TARGET_LEAK={bad}"
    )

if df[feature_cols].isna().any().any():
    raise SystemExit(
        "FEATURE_NAN_FOUND"
    )

print("===== EV DATASET =====")
print("ROWS=", len(df))
print("FEATURES=", len(feature_cols))

FOLDS = [
    (4, 5, 6),
    (5, 6, 7),
    (6, 7, 8),
    (7, 8, 9),
    (8, 9, 10),
]

rows = []

for fold_no, (
    train_end,
    val_block,
    test_block,
) in enumerate(
    FOLDS,
    start=1,
):
    tr = df[
        df["block"] <= train_end
    ].copy()

    va = df[
        df["block"] == val_block
    ].copy()

    te = df[
        df["block"] == test_block
    ].copy()

    Xtr = tr[
        feature_cols
    ].to_numpy(float)

    ytr = tr[
        "realized_net_pct"
    ].to_numpy(float)

    Xva = va[
        feature_cols
    ].to_numpy(float)

    Xte = te[
        feature_cols
    ].to_numpy(float)

    model = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=15,
        min_samples_leaf=100,
        l2_regularization=5.0,
        loss="squared_error",
        early_stopping=False,
        random_state=42,
    )

    model.fit(
        Xtr,
        ytr,
    )

    pva = model.predict(
        Xva
    )

    pte = model.predict(
        Xte
    )

    best = None

    # Validation selects predicted-EV tail.
    for q in QUANTILES:

        cut = float(
            np.quantile(
                pva,
                q,
            )
        )

        keep = (
            pva >= cut
        )

        vg = va.loc[
            keep
        ]

        e = economics(vg)

        if (
            e["n"]
            < MIN_VAL_TRADES
        ):
            continue

        cand = {
            "q": q,
            "cut": cut,
            "n": e["n"],
            "net": e["net"],
            "pf": e["pf"],
        }

        if (
            best is None
            or cand["net"]
            > best["net"]
        ):
            best = cand

    if best is None:
        raise SystemExit(
            f"NO_GATE_FOLD={fold_no}"
        )

    base_e = economics(
        te
    )

    keep_test = (
        pte >= best["cut"]
    )

    chosen = te.loc[
        keep_test
    ]

    ev_e = economics(
        chosen
    )

    # Prediction correlation is diagnostic only.
    corr = np.corrcoef(
        pte,
        te[
            "realized_net_pct"
        ].to_numpy(float),
    )[0, 1]

    rows.append({
        "fold":
            fold_no,

        "train_blocks":
            f"1-{train_end}",

        "val_block":
            val_block,

        "test_block":
            test_block,

        "train_n":
            len(tr),

        "val_n":
            len(va),

        "test_n":
            len(te),

        "selected_q":
            best["q"],

        "ev_cut":
            best["cut"],

        "val_gate_n":
            best["n"],

        "val_gate_net":
            best["net"],

        "test_corr":
            corr,

        "base_n":
            base_e["n"],

        "base_net":
            base_e["net"],

        "base_pf":
            base_e["pf"],

        "base_win":
            base_e["win"],

        "ev_n":
            ev_e["n"],

        "ev_net":
            ev_e["net"],

        "ev_pf":
            ev_e["pf"],

        "ev_win":
            ev_e["win"],

        "net_delta":
            (
                ev_e["net"]
                - base_e["net"]
            ),
    })


res = pd.DataFrame(rows)

print()
print("===== EV WALK FORWARD =====")

print(
    res.round(5)
    .to_string(index=False)
)

print()
print("===== SUMMARY =====")

delta = res[
    "net_delta"
]

print(
    "POSITIVE_DELTA=",
    int(
        (
            delta > 0
        ).sum()
    ),
    "/",
    len(delta),
)

print(
    "MEAN_DELTA_PCT=",
    round(
        delta.mean(),
        5,
    ),
)

print(
    "MEDIAN_DELTA_PCT=",
    round(
        delta.median(),
        5,
    ),
)

print(
    "EV_POSITIVE_FOLDS=",
    int(
        (
            res["ev_net"] > 0
        ).sum()
    ),
    "/",
    len(res),
)

print(
    "EV_WORST_FOLD=",
    round(
        res["ev_net"].min(),
        5,
    ),
)

# ---------------------------------------------
# Correct weighted returns:
# aggregate economic return / selected trades.
# ---------------------------------------------

base_weighted = (
    (
        res["base_net"]
        * res["base_n"]
    ).sum()
    / res["base_n"].sum()
)

ev_weighted = (
    (
        res["ev_net"]
        * res["ev_n"]
    ).sum()
    / res["ev_n"].sum()
)

print(
    "BASE_WEIGHTED_NET_PCT=",
    round(
        base_weighted,
        5,
    ),
)

print(
    "EV_WEIGHTED_NET_PCT=",
    round(
        ev_weighted,
        5,
    ),
)

print(
    "EV_TOTAL_TRADES=",
    int(
        res["ev_n"].sum()
    ),
)

print(
    "BASE_TOTAL_TRADES=",
    int(
        res["base_n"].sum()
    ),
)

print(
    "MEAN_TEST_CORR=",
    round(
        res[
            "test_corr"
        ].mean(),
        5,
    ),
)

path = (
    ROOT
    / "replay_results"
    / "NEAR_EV_REGRESSOR.csv"
)

res.to_csv(
    path,
    index=False,
)

print()
print(
    "OUTPUT=",
    path,
)

print(
    "NEAR_EV_REGRESSOR_COMPLETE"
)
