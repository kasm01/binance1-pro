#!/usr/bin/env python3

from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[1]

D1 = ROOT / "data/offline_cache/NEARUSDT_1m_360d.csv"
D3 = ROOT / "data/offline_cache/NEARUSDT_3m_360d.csv"

# Microflow coverage gives us the exact 14d research window.
START_MS = int(
    pd.Timestamp(
        "2026-09-01T00:00:00Z"
    ).timestamp() * 1000
)

END_MS = int(
    pd.Timestamp(
        "2026-09-14T19:23:59.999Z"
    ).timestamp() * 1000
)

LEVERAGE = 3.0

# Approximate round-trip taker cost.
FEE = 0.0008

# General lifecycle values relevant before these small TP targets.
SL_PCT = 0.0100
STALL_SEC = 1200

Q = 0.95

SCENARIOS = {
    "CURRENT_45_08": {
        "tp_roi": 0.0045,
        "giveback_roi": 0.0008,
    },
    "DIRECT45": {
        "tp_roi": 0.0045,
        "giveback_roi": 0.0,
    },
    "DIRECT40": {
        "tp_roi": 0.0040,
        "giveback_roi": 0.0,
    },
    "DIRECT35": {
        "tp_roi": 0.0035,
        "giveback_roi": 0.0,
    },
    "DIRECT30": {
        "tp_roi": 0.0030,
        "giveback_roi": 0.0,
    },
}


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
        x[f"{prefix}_rv{n}"] = (
            r.rolling(n).std()
        )

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


def replay_trade(
    d,
    entry_idx,
    scenario,
):
    entry = float(
        d["close"].iloc[entry_idx]
    )

    entry_time = int(
        d["close_time"].iloc[entry_idx]
    )

    tp_roi = float(
        scenario["tp_roi"]
    )

    giveback_roi = float(
        scenario["giveback_roi"]
    )

    best_roi = 0.0
    last_best_time = entry_time

    # Plenty beyond 20m stall while still bounded.
    max_end = min(
        entry_idx + 180,
        len(d) - 1,
    )

    for j in range(
        entry_idx + 1,
        max_end + 1,
    ):
        high = float(d["high"].iloc[j])
        low = float(d["low"].iloc[j])
        close = float(d["close"].iloc[j])

        bar_end = int(
            d["close_time"].iloc[j]
        )

        high_pnl = (
            high / entry - 1.0
        )

        low_pnl = (
            low / entry - 1.0
        )

        high_roi = (
            high_pnl * LEVERAGE
        )

        low_roi = (
            low_pnl * LEVERAGE
        )

        # ----------------------------
        # Safety first.
        # General lifecycle SL = -1%.
        # Conservative same-bar rule:
        # loss can occur before TP.
        # ----------------------------
        if low_pnl <= -SL_PCT:
            gross = -SL_PCT

            return {
                "exit_reason": "sl_hit",
                "gross_pct": gross * 100,
                "net_pct":
                    (gross - FEE) * 100,
                "hold_min":
                    (bar_end - entry_time)
                    / 60_000,
            }

        # --------------------------------
        # New best ROI / stall clock.
        # Actual lifecycle last_best_ts
        # resets whenever PnL improves.
        # --------------------------------
        if high_roi > best_roi:
            best_roi = high_roi
            last_best_time = bar_end

        # --------------------------------
        # DIRECT TP
        # --------------------------------
        if giveback_roi <= 0:
            if high_roi >= tp_roi:
                gross = (
                    tp_roi / LEVERAGE
                )

                return {
                    "exit_reason":
                        "fixed_roi_direct",
                    "gross_pct":
                        gross * 100,
                    "net_pct":
                        (gross - FEE) * 100,
                    "hold_min":
                        (bar_end - entry_time)
                        / 60_000,
                }

        # --------------------------------
        # CURRENT GIVEBACK
        #
        # With OHLC bars, exact intrabar path
        # is unknown. Once armed, if bar low
        # reaches best-giveback we close at
        # the threshold, not at bar low.
        # --------------------------------
        else:
            if best_roi >= tp_roi:
                trigger_roi = (
                    best_roi
                    - giveback_roi
                )

                if low_roi <= trigger_roi:
                    gross = (
                        trigger_roi
                        / LEVERAGE
                    )

                    return {
                        "exit_reason":
                            "fixed_roi_giveback",
                        "gross_pct":
                            gross * 100,
                        "net_pct":
                            (gross - FEE) * 100,
                        "hold_min":
                            (bar_end - entry_time)
                            / 60_000,
                    }

        # --------------------------------
        # STALL — 20m since last new best
        # --------------------------------
        stalled_sec = (
            bar_end
            - last_best_time
        ) / 1000.0

        if stalled_sec >= STALL_SEC:
            gross = (
                close / entry - 1.0
            )

            return {
                "exit_reason":
                    "stall_exit",
                "gross_pct":
                    gross * 100,
                "net_pct":
                    (gross - FEE) * 100,
                "hold_min":
                    (bar_end - entry_time)
                    / 60_000,
            }

    # Safety fallback at end of replay.
    close = float(
        d["close"].iloc[max_end]
    )

    end_time = int(
        d["close_time"].iloc[max_end]
    )

    gross = (
        close / entry - 1.0
    )

    return {
        "exit_reason": "window_end",
        "gross_pct": gross * 100,
        "net_pct": (gross - FEE) * 100,
        "hold_min":
            (end_time - entry_time)
            / 60_000,
    }


# ============================================================
# DATA
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

ctx = pd.concat(
    [
        d3[["close_time"]],
        f3,
    ],
    axis=1,
).sort_values("close_time")

joint = pd.merge_asof(
    joint,
    ctx,
    on="close_time",
    direction="backward",
    allow_exact_matches=True,
)

valid = (
    joint.drop(
        columns=["close_time"]
    )
    .notna()
    .all(axis=1)
    .to_numpy()
)

idx_map = np.flatnonzero(valid)

X = (
    joint.drop(
        columns=["close_time"]
    )
    .to_numpy(float)
)[valid]

times = (
    joint["close_time"]
    .to_numpy(dtype=np.int64)
)[valid]

# Exact 14d common research window.
window = (
    (times >= START_MS)
    & (times <= END_MS)
)

Xw = X[window]
tw = times[window]
iw = idx_map[window]

n = len(Xw)

print("===== SAMPLE =====")
print("ROWS=", n)
print(
    "FIRST=",
    pd.to_datetime(
        int(tw[0]),
        unit="ms",
        utc=True,
    ),
)
print(
    "LAST=",
    pd.to_datetime(
        int(tw[-1]),
        unit="ms",
        utc=True,
    ),
)

FOLDS = [
    (0.40, 0.55, 0.70),
    (0.55, 0.70, 0.85),
    (0.70, 0.85, 1.00),
]

signal_rows = []

for fold_no, (
    tr_frac,
    va_frac,
    te_frac,
) in enumerate(
    FOLDS,
    start=1,
):
    train_end = int(
        n * tr_frac
    )
    val_end = int(
        n * va_frac
    )
    test_end = int(
        n * te_frac
    )

    # No future label is used here.
    # Model target comes from prior research model?
    #
    # Build same triple-barrier binary target
    # on the full 360d series for model training.
    #
    # We need target aligned with valid rows.
    c = d1["close"].astype(float).to_numpy()
    h = d1["high"].astype(float).to_numpy()
    l = d1["low"].astype(float).to_numpy()

    H = 15
    TP_LABEL = 0.0020
    SL_LABEL = 0.0015

    full_y = np.zeros(
        len(d1),
        dtype=int,
    )

    max_i = len(d1) - H

    for i in range(max_i):
        entry = c[i]
        label = 0

        for k in range(1, H + 1):
            loss = (
                l[i+k] / entry - 1
                <= -SL_LABEL
            )
            win = (
                h[i+k] / entry - 1
                >= TP_LABEL
            )

            if loss:
                label = 0
                break

            if win:
                label = 1
                break

        full_y[i] = label

    yw = full_y[iw]

    fit_end = max(
        train_end - H,
        1,
    )

    val_eval_end = max(
        val_end - H,
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
        Xw[:fit_end],
        yw[:fit_end],
    )

    sval = model.predict_proba(
        Xw[
            train_end:val_eval_end
        ]
    )[:, 1]

    stest = model.predict_proba(
        Xw[
            val_end:test_end
        ]
    )[:, 1]

    cut = float(
        np.quantile(
            sval,
            Q,
        )
    )

    local = np.flatnonzero(
        stest >= cut
    )

    # Same entry events across every lifecycle.
    # 15m signal de-dup only.
    keep = []
    last = -10**18

    for x in local:
        if x - last >= 15:
            keep.append(x)
            last = x

    for x in keep:
        widx = val_end + int(x)

        signal_rows.append({
            "fold": fold_no,
            "score": float(stest[x]),
            "row_idx": int(iw[widx]),
            "entry_time": int(tw[widx]),
        })

signals = pd.DataFrame(signal_rows)

print()
print("===== SIGNALS =====")
print(
    signals.groupby("fold")
    .size()
    .rename("n")
    .to_string()
)
print("TOTAL=", len(signals))

# ============================================================
# LIFECYCLE GRID
# ============================================================

rows = []

for _, sig in signals.iterrows():
    entry_idx = int(
        sig["row_idx"]
    )

    for name, cfg in SCENARIOS.items():
        r = replay_trade(
            d1,
            entry_idx,
            cfg,
        )

        rows.append({
            "fold": int(sig["fold"]),
            "scenario": name,
            "entry_time":
                int(sig["entry_time"]),
            "score":
                float(sig["score"]),
            **r,
        })

out = pd.DataFrame(rows)

print()
print("===== LIFECYCLE GRID =====")

summary = (
    out.groupby("scenario")
    .agg(
        trades=("net_pct", "count"),
        gross_avg_pct=("gross_pct", "mean"),
        net_avg_pct=("net_pct", "mean"),
        net_median_pct=("net_pct", "median"),
        total_net_pct=("net_pct", "sum"),
        win_pct=(
            "net_pct",
            lambda x:
                (x > 0).mean() * 100,
        ),
        avg_hold_min=("hold_min", "mean"),
        median_hold_min=("hold_min", "median"),
    )
)

# Profit factor.
pf = {}

for name, g in out.groupby("scenario"):
    wins = g.loc[
        g.net_pct > 0,
        "net_pct",
    ].sum()

    losses = -g.loc[
        g.net_pct < 0,
        "net_pct",
    ].sum()

    pf[name] = (
        wins / losses
        if losses > 0
        else np.inf
    )

summary["profit_factor"] = pd.Series(pf)

print(
    summary.round(5)
    .sort_values(
        "net_avg_pct",
        ascending=False,
    )
    .to_string()
)

print()
print("===== EXIT REASONS =====")

reason = pd.crosstab(
    out["scenario"],
    out["exit_reason"],
)

print(
    reason.to_string()
)

print()
print("===== FOLD NET =====")

fold = (
    out.groupby(
        ["fold", "scenario"]
    )["net_pct"]
    .mean()
    .unstack()
)

print(
    fold.round(5)
    .to_string()
)

print()
print("===== DELTA vs CURRENT =====")

base = summary.loc[
    "CURRENT_45_08",
    "net_avg_pct",
]

for name in (
    "DIRECT45",
    "DIRECT40",
    "DIRECT35",
    "DIRECT30",
):
    value = summary.loc[
        name,
        "net_avg_pct",
    ]

    print(
        name,
        "DELTA_PCT=",
        round(
            value - base,
            5,
        ),
        "DELTA_BPS=",
        round(
            (value - base) * 100,
            3,
        ),
    )

path = (
    ROOT
    / "replay_results"
    / "NEAR_DIRECT_ROI_GRID.csv"
)

out.to_csv(
    path,
    index=False,
)

print()
print("OUTPUT=", path)
print("NEAR_DIRECT_ROI_GRID_COMPLETE")
