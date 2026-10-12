#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]

DATA = (
    ROOT
    / "replay_results"
    / "NEAR_META_DATASET_360D.csv"
)

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

    wins = x[x > 0].sum()
    losses = -x[x < 0].sum()

    pf = (
        wins / losses
        if losses > 0
        else np.inf
    )

    return {
        "n": len(x),
        "net": float(np.mean(x)),
        "median": float(np.median(x)),
        "win": float(
            np.mean(x > 0) * 100
        ),
        "pf": float(pf),
    }


df = pd.read_csv(DATA)

df = (
    df
    .sort_values(
        ["block", "entry_time"]
    )
    .reset_index(drop=True)
)

# ---------------------------------------------------------
# Score normalization relative to the OOF base threshold.
# Both are known at signal time.
# ---------------------------------------------------------

df["score_margin"] = (
    df["base_score"]
    - df["base_cut"]
)

df["score_ratio"] = (
    df["base_score"]
    / df["base_cut"].replace(0, np.nan)
    - 1.0
)

# ---------------------------------------------------------
# Strict feature exclusions.
#
# No target, future result, timestamps, raw row IDs or block.
# ---------------------------------------------------------

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

# Ensure no accidental outcome column entered.
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
        f"TARGET_LEAK_FEATURES={bad}"
    )

if df[feature_cols].isna().any().any():
    raise SystemExit(
        "FEATURE_NAN_FOUND"
    )

print("===== META INPUT =====")
print("ROWS=", len(df))
print("FEATURES=", len(feature_cols))
print(
    "BLOCKS=",
    sorted(
        df["block"].unique().tolist()
    ),
)
print(
    "FEATURE_SAMPLE=",
    feature_cols[:12],
)

# ---------------------------------------------------------
# Expanding chronological meta folds.
# ---------------------------------------------------------

FOLDS = [
    # train_end, val_block, test_block
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
        "meta_label"
    ].to_numpy(int)

    Xva = va[
        feature_cols
    ].to_numpy(float)

    yva = va[
        "meta_label"
    ].to_numpy(int)

    Xte = te[
        feature_cols
    ].to_numpy(float)

    yte = te[
        "meta_label"
    ].to_numpy(int)

    model = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=15,
        min_samples_leaf=100,
        l2_regularization=5.0,
        early_stopping=False,
        random_state=42,
    )

    model.fit(
        Xtr,
        ytr,
    )

    pva = model.predict_proba(
        Xva
    )[:, 1]

    pte = model.predict_proba(
        Xte
    )[:, 1]

    try:
        val_auc = roc_auc_score(
            yva,
            pva,
        )
    except Exception:
        val_auc = np.nan

    try:
        test_auc = roc_auc_score(
            yte,
            pte,
        )
    except Exception:
        test_auc = np.nan

    # -----------------------------------------------------
    # Validation chooses one gate quantile.
    # Test is never used in selection.
    # -----------------------------------------------------

    best = None

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

        candidate = {
            "q": q,
            "cut": cut,
            "net": e["net"],
            "n": e["n"],
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

    base_e = economics(te)

    test_keep = (
        pte >= best["cut"]
    )

    meta_te = te.loc[
        test_keep
    ]

    meta_e = economics(
        meta_te
    )

    rows.append({
        "fold": fold_no,

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

        "val_auc":
            val_auc,

        "test_auc":
            test_auc,

        "selected_q":
            best["q"],

        "meta_cut":
            best["cut"],

        "val_gate_n":
            best["n"],

        "val_gate_net":
            best["net"],

        "base_test_n":
            base_e["n"],

        "base_net":
            base_e["net"],

        "base_pf":
            base_e["pf"],

        "base_win":
            base_e["win"],

        "meta_test_n":
            meta_e["n"],

        "meta_net":
            meta_e["net"],

        "meta_pf":
            meta_e["pf"],

        "meta_win":
            meta_e["win"],

        "net_delta":
            (
                meta_e["net"]
                - base_e["net"]
            ),
    })

res = pd.DataFrame(rows)

print()
print("===== META WALK FORWARD =====")

print(
    res.round(5)
    .to_string(index=False)
)

print()
print("===== PAIRED SUMMARY =====")

delta = res[
    "net_delta"
]

print(
    "POSITIVE_DELTA=",
    int((delta > 0).sum()),
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
    "META_POSITIVE_FOLDS=",
    int(
        (
            res["meta_net"]
            > 0
        ).sum()
    ),
    "/",
    len(res),
)

print(
    "META_WORST_FOLD=",
    round(
        res["meta_net"].min(),
        5,
    ),
)

# ---------------------------------------------------------
# Weighted economics across untouched test blocks.
# ---------------------------------------------------------

base_weighted = np.average(
    res["base_net"],
    weights=res["base_test_n"],
)

meta_weighted = np.average(
    res["meta_net"],
    weights=res["meta_test_n"],
)

print(
    "BASE_WEIGHTED_NET_PCT=",
    round(
        base_weighted,
        5,
    ),
)

print(
    "META_WEIGHTED_NET_PCT=",
    round(
        meta_weighted,
        5,
    ),
)

print(
    "WEIGHTED_DELTA_PCT=",
    round(
        meta_weighted
        - base_weighted,
        5,
    ),
)

print(
    "META_TOTAL_TEST_TRADES=",
    int(
        res[
            "meta_test_n"
        ].sum()
    ),
)

print(
    "BASE_TOTAL_TEST_TRADES=",
    int(
        res[
            "base_test_n"
        ].sum()
    ),
)

path = (
    ROOT
    / "replay_results"
    / "NEAR_META_WALKFORWARD.csv"
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
    "NEAR_META_WALKFORWARD_COMPLETE"
)
