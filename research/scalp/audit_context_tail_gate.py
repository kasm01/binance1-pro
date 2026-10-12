#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[2]

DATA = (
    ROOT / "research/results"
    / "NEAR_STRONG_SIGNAL_DATASET.csv.gz"
)

CONTEXT = (
    ROOT / "research/results"
    / "ALT_MARKET_CONTEXT_3M.csv"
)

D1 = (
    ROOT / "data/offline_cache"
    / "NEARUSDT_1m_360d.csv"
)

OUT = (
    ROOT / "research/results"
    / "NEAR_CONTEXT_TAIL_GATE_WF.csv"
)

TP = 0.0025
SL = 0.0050
FEE = 0.0008
HORIZON = 10

QUANTILES = [0.60, 0.70, 0.80, 0.90]
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


def make_model(seed):
    return HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=15,
        min_samples_leaf=150,
        l2_regularization=5.0,
        early_stopping=False,
        random_state=seed,
    )


ds = pd.read_csv(DATA)

ctx = pd.read_csv(CONTEXT)

ctx = (
    ctx.sort_values("close_time")
    .reset_index(drop=True)
)

# ---------------------------------------------------------
# Attach latest CLOSED 3m market context to each 5m setup.
# ---------------------------------------------------------

ds = (
    ds.sort_values("feature_close_time")
    .reset_index(drop=True)
)

df = pd.merge_asof(
    ds,
    ctx,
    left_on="feature_close_time",
    right_on="close_time",
    direction="backward",
    allow_exact_matches=True,
)

df = df.drop(columns=["close_time"])

context_cols = [
    c for c in ctx.columns
    if c != "close_time"
]

base_cols = [
    c for c in df.columns
    if (
        c.startswith("m3_")
        or c.startswith("m5_")
        or c.startswith("m15_")
    )
]

expanded_cols = (
    base_cols
    + context_cols
)

if df[
    expanded_cols
].isna().any().any():
    raise SystemExit("CONTEXT_FEATURE_NAN")

print("===== INPUT =====")
print("ROWS=", len(df))
print("BASE_FEATURES=", len(base_cols))
print("CONTEXT_FEATURES=", len(context_cols))
print("EXPANDED_FEATURES=", len(expanded_cols))

# ---------------------------------------------------------
# Rebuild first-hit economic labels.
# ---------------------------------------------------------

d1 = pd.read_csv(D1)

ot = d1["open_time"].to_numpy(dtype=np.int64)
o = d1["open"].astype(float).to_numpy()
h = d1["high"].astype(float).to_numpy()
l = d1["low"].astype(float).to_numpy()
c = d1["close"].astype(float).to_numpy()

n = len(df)

follow = np.zeros(n, dtype=int)
danger = np.zeros(n, dtype=int)
econ = np.zeros(n, dtype=float)

# Complementary risk target:
# strong early adverse movement before full SL.
early_tail = (
    df["mae_5m_pct"]
    .to_numpy(float)
    <= -0.30
).astype(int)

for i, r in df.iterrows():

    entry_time = int(r["entry_open_time"])

    idx = int(
        np.searchsorted(
            ot,
            entry_time,
            side="left",
        )
    )

    if idx >= len(d1):
        raise SystemExit("ENTRY_INDEX_FAILURE")

    entry = float(o[idx])

    result = "HOLD"

    for k in range(HORIZON):

        j = idx + k

        if j >= len(d1):
            break

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


print()
print("===== LABELS =====")
print("FOLLOW_RATE=", round(follow.mean(), 5))
print("DANGER_RATE=", round(danger.mean(), 5))
print("EARLY_TAIL_RATE=", round(early_tail.mean(), 5))
print("RAW_ECON_PCT=", round(econ.mean() * 100, 5))


FOLDS = [
    (0.50, 0.625, 0.75),
    (0.625, 0.75, 0.8333),
    (0.70, 0.8333, 0.9166),
    (0.75, 0.9166, 1.00),
]

rows = []

for variant, cols in (
    ("BASE_DUAL", base_cols),
    ("CONTEXT_TAIL", expanded_cols),
):

    X = df[cols].to_numpy(float)

    if not np.isfinite(X).all():
        raise SystemExit(
            f"BAD_FEATURE_VALUE_{variant}"
        )

    for fold_no, (
        train_frac,
        val_frac,
        test_frac,
    ) in enumerate(FOLDS, start=1):

        tr_end = int(n * train_frac)
        va_end = int(n * val_frac)
        te_end = int(n * test_frac)

        # 10-minute forward-label purge.
        fit_end = max(
            tr_end - 3,
            1,
        )

        mf = make_model(42)
        md = make_model(43)

        mf.fit(
            X[:fit_end],
            follow[:fit_end],
        )

        md.fit(
            X[:fit_end],
            danger[:fit_end],
        )

        pfv = mf.predict_proba(
            X[tr_end:va_end]
        )[:, 1]

        pdv = md.predict_proba(
            X[tr_end:va_end]
        )[:, 1]

        pft = mf.predict_proba(
            X[va_end:te_end]
        )[:, 1]

        pdt = md.predict_proba(
            X[va_end:te_end]
        )[:, 1]

        if variant == "CONTEXT_TAIL":

            mt = make_model(44)

            mt.fit(
                X[:fit_end],
                early_tail[:fit_end],
            )

            ptv = mt.predict_proba(
                X[tr_end:va_end]
            )[:, 1]

            ptt = mt.predict_proba(
                X[va_end:te_end]
            )[:, 1]

            qval = (
                pfv
                * (1.0 - pdv)
                * (1.0 - ptv)
            )

            qtest = (
                pft
                * (1.0 - pdt)
                * (1.0 - ptt)
            )

        else:

            # Baseline dual model expressed
            # multiplicatively for comparable scale.
            qval = (
                pfv
                * (1.0 - pdv)
            )

            qtest = (
                pft
                * (1.0 - pdt)
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
                f"NO_GATE_{variant}_{fold_no}"
            )

        keep_test = (
            qtest >= best["cut"]
        )

        gate_e = economics(
            eval_test[keep_test]
        )

        base_e = economics(
            eval_test
        )

        rows.append({
            "variant":
                variant,

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
                best["econ"]["mean"] * 100,

            "test_n":
                gate_e["n"],

            "test_net_pct":
                gate_e["mean"] * 100,

            "test_median_pct":
                gate_e["median"] * 100,

            "win_pct":
                gate_e["win"],

            "pf":
                gate_e["pf"],

            "raw_test_net_pct":
                base_e["mean"] * 100,
        })


res = pd.DataFrame(rows)

print()
print("===== WALK FORWARD =====")

print(
    res.round(5)
    .to_string(index=False)
)

a = (
    res[
        res["variant"] == "BASE_DUAL"
    ]
    .set_index("fold")
)

b = (
    res[
        res["variant"] == "CONTEXT_TAIL"
    ]
    .set_index("fold")
)

delta = (
    b["test_net_pct"]
    - a["test_net_pct"]
)

print()
print("===== CONTEXT+TAIL vs BASE =====")

paired = pd.DataFrame({
    "base":
        a["test_net_pct"],

    "context_tail":
        b["test_net_pct"],

    "delta":
        delta,

    "n_base":
        a["test_n"],

    "n_context_tail":
        b["test_n"],
})

print(
    paired.round(5)
    .to_string()
)

print()
print("===== SUMMARY =====")

print(
    "CONTEXT_POSITIVE_DELTA=",
    int((delta > 0).sum()),
    "/",
    len(delta),
)

print(
    "CONTEXT_MEAN_DELTA_PCT=",
    round(delta.mean(), 5),
)

print(
    "CONTEXT_MEDIAN_DELTA_PCT=",
    round(delta.median(), 5),
)

print(
    "CONTEXT_POSITIVE_FOLDS=",
    int(
        (
            b["test_net_pct"] > 0
        ).sum()
    ),
    "/",
    len(b),
)

weighted = (
    (
        b["test_net_pct"]
        * b["test_n"]
    ).sum()
    / b["test_n"].sum()
)

print(
    "CONTEXT_WEIGHTED_NET_PCT=",
    round(weighted, 5),
)

print(
    "CONTEXT_WORST_FOLD=",
    round(
        b["test_net_pct"].min(),
        5,
    ),
)

print(
    "CONTEXT_TOTAL_TRADES=",
    int(
        b["test_n"].sum()
    ),
)

print(
    "CONTEXT_PF_GT1=",
    int((b["pf"] > 1).sum()),
    "/",
    len(b),
)

res.to_csv(
    OUT,
    index=False,
)

print()
print("OUTPUT=", OUT)
print("CONTEXT_TAIL_GATE_WF_COMPLETE")
