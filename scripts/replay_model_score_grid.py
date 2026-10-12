#!/usr/bin/env python3

from pathlib import Path
import importlib.util
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "replay_v2",
    ROOT / "scripts/replay_long_trades_v2.py",
)

r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

# ---------------------------------------------------------
# Replay policy
# ---------------------------------------------------------
r.STALL_TTL = 0

SCORE_VALUES = [
    0.525,
    0.56,
    0.58,
    0.60,
    0.62,
    0.64,
    0.66,
    0.68,
    0.70,
]

EXIT_PROFILES = {
    "CURRENT_045_008": (
        0.0045,
        0.0008,
    ),
    "WIDE_120_010": (
        0.0120,
        0.0010,
    ),
}

MODES = [
    "CURRENT_SHADOW",
    "CONFIRM_ENFORCED",
]

score_gate = 0.525


def candidate_allowed(row, mode):
    global score_gate

    if str(row["sniper"]) != "PASS":
        return False

    try:
        score = float(row["model_score"])
    except Exception:
        return False

    if score < float(score_gate):
        return False

    if mode == "CURRENT_SHADOW":
        return True

    if mode == "CONFIRM_ENFORCED":
        return (
            str(
                row.get("confirm_proposed")
                or ""
            ).lower()
            == "open"
        )

    return False


# Replace only replay candidate selector.
r.candidate_allowed = candidate_allowed

rows_out = []

print("===== MODEL SCORE GATE GRID =====")
print("stall=OFF")
print("fee=", r.TAKER_FEE)
print("leverage=", r.LEV)
print()

for profile, (tp, gb) in EXIT_PROFILES.items():
    r.FIXED_TP = tp
    r.FIXED_GIVEBACK = gb

    for mode in MODES:
        for score in SCORE_VALUES:
            score_gate = score

            trades_all = []

            for window in r.WINDOWS:
                trades_all.extend(
                    r.run_window(
                        window,
                        mode,
                    )
                )

            df = pd.DataFrame(trades_all)

            if df.empty:
                rows_out.append({
                    "profile": profile,
                    "mode": mode,
                    "score_gate": score,
                    "trades": 0,
                })
                continue

            trades = len(df)

            wins = int(
                (df["net_roi"] > 0).sum()
            )

            counts = (
                df["exit_reason"]
                .value_counts()
                .to_dict()
            )

            rows_out.append({
                "profile": profile,
                "mode": mode,
                "score_gate": score,
                "trades": trades,
                "wins": wins,
                "win_rate_pct": (
                    wins / trades * 100
                ),
                "gross_sum_pct": (
                    df["gross_roi"].sum()
                    * 100
                ),
                "net_sum_pct": (
                    df["net_roi"].sum()
                    * 100
                ),
                "avg_gross_pct": (
                    df["gross_roi"].mean()
                    * 100
                ),
                "avg_net_pct": (
                    df["net_roi"].mean()
                    * 100
                ),
                "median_net_pct": (
                    df["net_roi"].median()
                    * 100
                ),
                "worst_net_pct": (
                    df["net_roi"].min()
                    * 100
                ),
                "best_net_pct": (
                    df["net_roi"].max()
                    * 100
                ),
                "fixed_exits": counts.get(
                    "fixed_roi_tp_lifecycle_lock",
                    0,
                ),
                "sl_exits": counts.get(
                    "sl_hit",
                    0,
                ),
                "window_end": counts.get(
                    "window_end",
                    0,
                ),
            })

out = pd.DataFrame(rows_out)

path = (
    ROOT
    / "replay_results"
    / "SOLUSDT_model_score_grid.csv"
)

out.to_csv(
    path,
    index=False,
)

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 280)

for profile in EXIT_PROFILES:
    for mode in MODES:
        print()
        print("=" * 90)
        print(profile, "/", mode)
        print("=" * 90)

        x = out[
            (out["profile"] == profile)
            & (out["mode"] == mode)
        ].sort_values(
            "score_gate"
        )

        print(
            x.round(4)
            .to_string(index=False)
        )

print()
print("===== BEST GROSS PER PROFILE/MODE =====")

valid = out[
    out["trades"].fillna(0) > 0
].copy()

for (profile, mode), x in valid.groupby(
    ["profile", "mode"]
):
    b = x.sort_values(
        "gross_sum_pct",
        ascending=False,
    ).iloc[0]

    print(
        profile,
        mode,
        "score=",
        b["score_gate"],
        "trades=",
        int(b["trades"]),
        "gross=",
        round(b["gross_sum_pct"], 4),
        "%",
        "net=",
        round(b["net_sum_pct"], 4),
        "%",
        "win_rate=",
        round(b["win_rate_pct"], 2),
        "%",
    )

print()
print("OUTPUT=", path)
print("MODEL_SCORE_GRID_COMPLETE")
