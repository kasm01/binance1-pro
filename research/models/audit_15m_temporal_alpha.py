#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[2]

FEATURES = (
    ROOT
    / "research/results"
    / "NEAR_15M_TEMPORAL_FEATURES.csv"
)

TARGETS = (
    ROOT
    / "research/results"
    / "NEAR_15M_ECONOMIC_TARGETS.csv"
)

OUT = (
    ROOT
    / "research/results"
    / "NEAR_15M_TEMPORAL_ALPHA_WF.csv"
)

QUANTILES = [
    0.80,
    0.90,
    0.95,
    0.975,
    0.99,
]

HORIZON_BARS = 4
MIN_VAL_TRADES = 30


def dedup_indices(idx, spacing=4):
    out = []
    last = -10**18

    for x in idx:
        x = int(x)

        if x - last >= spacing:
            out.append(x)
            last = x

    return np.asarray(
        out,
        dtype=int,
    )


def economics(x):
    x = np.asarray(
        x,
        dtype=float,
    )

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

        "mean":
            float(np.mean(x)),

        "median":
            float(np.median(x)),

        "win":
            float(
                np.mean(x > 0) * 100
            ),

        "pf":
            float(
                pos / neg
                if neg > 0
                else np.inf
            ),
    }


print("===== LOAD =====")

f = pd.read_csv(FEATURES)

t = pd.read_csv(
    TARGETS,
    usecols=[
        "feature_close_time",
        "net_return_pct",
    ],
)

df = f.merge(
    t,
    left_on="close_time",
    right_on="feature_close_time",
    how="inner",
    validate="one_to_one",
)

df = (
    df.sort_values("close_time")
    .reset_index(drop=True)
)

print("ROWS=", len(df))

exclude = {
    "open_time",
    "close_time",
    "open",
    "high",
    "low",
    "close",
    "feature_close_time",
    "net_return_pct",
}

all_features = [
    c
    for c in df.columns
    if c not in exclude
]

current_features = [
    c
    for c in all_features
    if (
        "_lag" not in c
        and "_delta" not in c
    )
]

temporal_features = list(
    all_features
)

print(
    "CURRENT_FEATURES=",
    len(current_features),
)

print(
    "TEMPORAL_FEATURES=",
    len(temporal_features),
)

if df[
    temporal_features
].isna().any().any():
    raise SystemExit(
        "FEATURE_NAN_FOUND"
    )

y = (
    df["net_return_pct"]
    .to_numpy(float)
)

n = len(df)

# Expanding chronological walk-forward.
FOLDS = [
    (0.50, 0.625, 0.75),
    (0.625, 0.75, 0.8333),
    (0.70, 0.8333, 0.9166),
    (0.75, 0.9166, 1.00),
]

rows = []

for model_name, cols in (
    ("CURRENT", current_features),
    ("TEMPORAL", temporal_features),
):

    X = (
        df[cols]
        .to_numpy(float)
    )

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

        # Purge target overlap.
        fit_end = max(
            train_end - HORIZON_BARS,
            1,
        )

        val_eval_end = max(
            val_end - HORIZON_BARS,
            train_end + 1,
        )

        model = HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_iter=250,
            max_leaf_nodes=15,
            min_samples_leaf=100,
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

            idx = dedup_indices(
                idx,
                HORIZON_BARS,
            )

            e = economics(
                yval[idx]
            )

            if (
                e["n"]
                < MIN_VAL_TRADES
            ):
                continue

            cand = {
                "q": q,
                "cut": cut,
                "econ": e,
            }

            if (
                best is None
                or e["mean"]
                > best["econ"]["mean"]
            ):
                best = cand

        if best is None:
            raise SystemExit(
                f"NO_GATE_{model_name}_{fold_no}"
            )

        idx = np.flatnonzero(
            ptest >= best["cut"]
        )

        idx = dedup_indices(
            idx,
            HORIZON_BARS,
        )

        test_e = economics(
            ytest[idx]
        )

        corr = np.corrcoef(
            ptest,
            ytest,
        )[0, 1]

        rows.append({
            "model":
                model_name,

            "fold":
                fold_no,

            "features":
                len(cols),

            "selected_q":
                best["q"],

            "cut":
                best["cut"],

            "val_n":
                best["econ"]["n"],

            "val_net_pct":
                best["econ"]["mean"],

            "test_n":
                test_e["n"],

            "test_net_pct":
                test_e["mean"],

            "test_median_pct":
                test_e["median"],

            "win_pct":
                test_e["win"],

            "profit_factor":
                test_e["pf"],

            "test_corr":
                corr,
        })


res = pd.DataFrame(rows)

print()
print("===== WALK FORWARD =====")

print(
    res.round(5)
    .to_string(index=False)
)

print()
print("===== PAIRED CURRENT vs TEMPORAL =====")

a = (
    res[
        res["model"]
        == "CURRENT"
    ]
    .set_index("fold")
)

b = (
    res[
        res["model"]
        == "TEMPORAL"
    ]
    .set_index("fold")
)

delta = (
    b["test_net_pct"]
    - a["test_net_pct"]
)

paired = pd.DataFrame({
    "current":
        a["test_net_pct"],

    "temporal":
        b["test_net_pct"],

    "delta":
        delta,

    "n_current":
        a["test_n"],

    "n_temporal":
        b["test_n"],
})

print(
    paired.round(5)
    .to_string()
)

print()
print("===== SUMMARY =====")

print(
    "TEMPORAL_POSITIVE_DELTA=",
    int((delta > 0).sum()),
    "/",
    len(delta),
)

print(
    "TEMPORAL_MEAN_DELTA_PCT=",
    round(
        delta.mean(),
        5,
    ),
)

print(
    "TEMPORAL_MEDIAN_DELTA_PCT=",
    round(
        delta.median(),
        5,
    ),
)

bt = b["test_net_pct"]

print(
    "TEMPORAL_POSITIVE_FOLDS=",
    int((bt > 0).sum()),
    "/",
    len(bt),
)

print(
    "TEMPORAL_WORST_FOLD=",
    round(
        bt.min(),
        5,
    ),
)

weighted = (
    (
        b["test_net_pct"]
        * b["test_n"]
    ).sum()
    / b["test_n"].sum()
)

print(
    "TEMPORAL_WEIGHTED_NET_PCT=",
    round(
        weighted,
        5,
    ),
)

print(
    "TEMPORAL_TOTAL_TRADES=",
    int(
        b["test_n"].sum()
    ),
)

print(
    "TEMPORAL_MEAN_CORR=",
    round(
        b["test_corr"].mean(),
        5,
    ),
)

res.to_csv(
    OUT,
    index=False,
)

print()
print("OUTPUT=", OUT)

print(
    "TEMPORAL_ALPHA_WF_COMPLETE"
)
