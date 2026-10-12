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

# Bu testte stall kapalı.
r.STALL_TTL = 0

TP_VALUES = [
    0.0045,
    0.0060,
    0.0075,
    0.0090,
    0.0120,
]

GB_VALUES = [
    0.0008,
    0.0010,
    0.0015,
    0.0020,
    0.0030,
]

MODES = [
    "CURRENT_SHADOW",
    "CONFIRM_ENFORCED",
]

rows_out = []

print("===== FIXED ROI GRID =====")
print("stall=OFF")
print("fee=", r.TAKER_FEE)
print("leverage=", r.LEV)
print()

for mode in MODES:
    for tp in TP_VALUES:
        for gb in GB_VALUES:
            r.FIXED_TP = tp
            r.FIXED_GIVEBACK = gb

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
                "mode": mode,
                "tp_arm_pct": tp * 100,
                "giveback_pct": gb * 100,
                "trades": trades,
                "wins": wins,
                "win_rate_pct": wins / trades * 100,
                "gross_sum_pct": df["gross_roi"].sum() * 100,
                "net_sum_pct": df["net_roi"].sum() * 100,
                "avg_net_pct": df["net_roi"].mean() * 100,
                "median_net_pct": df["net_roi"].median() * 100,
                "worst_net_pct": df["net_roi"].min() * 100,
                "best_net_pct": df["net_roi"].max() * 100,
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

out = out.sort_values(
    ["mode", "net_sum_pct"],
    ascending=[True, False],
)

path = (
    ROOT
    / "replay_results"
    / "SOLUSDT_fixed_roi_grid.csv"
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
    260,
)

print(
    out.round(4)
    .to_string(index=False)
)

print()
print("===== TOP 10 PER MODE =====")

for mode in MODES:
    print()
    print("MODE=", mode)

    x = (
        out[out["mode"] == mode]
        .sort_values(
            "net_sum_pct",
            ascending=False,
        )
        .head(10)
    )

    print(
        x.round(4)
        .to_string(index=False)
    )

print()
print("OUTPUT=", path)
print("FIXED_ROI_GRID_COMPLETE")
