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

STALL_VALUES = [
    0,      # disabled
    300,    # 5 min
    600,    # 10 min
    900,    # 15 min
    1200,   # current 20 min
    1800,   # 30 min
    2400,   # 40 min
]

MODES = [
    "CURRENT_SHADOW",
    "CONFIRM_ENFORCED",
]

summary = []

print("===== STALL TTL SENSITIVITY =====")
print("fixed_tp=", r.FIXED_TP)
print("fixed_giveback=", r.FIXED_GIVEBACK)
print("fee=", r.TAKER_FEE)
print("leverage=", r.LEV)
print()

for mode in MODES:
    for stall in STALL_VALUES:
        r.STALL_TTL = stall

        rows = []

        for window in r.WINDOWS:
            rows.extend(
                r.run_window(
                    window,
                    mode,
                )
            )

        df = pd.DataFrame(rows)

        if df.empty:
            continue

        counts = (
            df["exit_reason"]
            .value_counts()
            .to_dict()
        )

        trades = len(df)
        wins = int(
            (df["net_roi"] > 0).sum()
        )

        summary.append({
            "mode": mode,
            "stall_sec": stall,
            "stall_min": (
                "OFF"
                if stall == 0
                else stall / 60
            ),
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
            "fixed_roi_exits": counts.get(
                "fixed_roi_tp_lifecycle_lock",
                0,
            ),
            "stall_exits": counts.get(
                "stall_exit",
                0,
            ),
            "sl_exits": counts.get(
                "sl_hit",
                0,
            ),
            "roi_hard_stop": counts.get(
                "roi_hard_stop_lifecycle",
                0,
            ),
            "window_end": counts.get(
                "window_end",
                0,
            ),
        })

out = pd.DataFrame(summary)

out = out.sort_values(
    ["mode", "net_sum_pct"],
    ascending=[True, False],
)

path = (
    ROOT
    / "replay_results"
    / "SOLUSDT_stall_sensitivity.csv"
)

out.to_csv(
    path,
    index=False,
)

pd.set_option(
    "display.max_columns",
    None,
)
pd.set_option(
    "display.width",
    240,
)

print(
    out.round(4)
    .to_string(index=False)
)

print()
print("===== BEST PER MODE =====")

for mode in MODES:
    x = out[
        out["mode"] == mode
    ].sort_values(
        "net_sum_pct",
        ascending=False,
    )

    if len(x):
        b = x.iloc[0]

        print(
            mode,
            "best_stall=",
            b["stall_min"],
            "net=",
            round(
                b["net_sum_pct"],
                4,
            ),
            "%",
            "gross=",
            round(
                b["gross_sum_pct"],
                4,
            ),
            "%",
            "trades=",
            int(b["trades"]),
            "win_rate=",
            round(
                b["win_rate_pct"],
                2,
            ),
            "%",
        )

print()
print("OUTPUT=", path)
print("STALL_SENSITIVITY_COMPLETE")
