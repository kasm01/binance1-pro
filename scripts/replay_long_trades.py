#!/usr/bin/env python3

from pathlib import Path
from bisect import bisect_right
from collections import Counter
import json
import os

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(".env", override=False)

RESULTS = Path("replay_results")
DATA = Path("replay_data/sol_20260912_13/aggtrades")

LEVERAGE = float(
    os.getenv("DEFAULT_ORDER_LEVERAGE", "3")
)

TP_ARM = float(
    os.getenv("FIXED_ROI_TP_PCT", "0.0045")
)

TP_GIVEBACK = float(
    os.getenv("FIXED_ROI_TP_GIVEBACK", "0.0008")
)

HARD_STOP = float(
    os.getenv("ROI_HARD_STOP_PCT", "-0.075")
)

POLL_MS = int(
    float(
        os.getenv(
            "POSITION_LIFECYCLE_INTERVAL_SEC",
            "2",
        )
    ) * 1000
)

TAKER_FEE = float(
    os.getenv("REPLAY_TAKER_FEE_RATE", "0.0004")
)

SLIPPAGE_BPS = float(
    os.getenv("REPLAY_SLIPPAGE_BPS", "0")
)

WINDOWS = ("A", "B", "C")


def load_trades(window):
    p = DATA / f"SOLUSDT_{window}_aggTrades.json"
    raw = json.loads(p.read_text(encoding="utf-8"))

    ts = []
    px = []

    for x in raw:
        ts.append(int(x["T"]))
        px.append(float(x["p"]))

    return ts, px


def market_price_at(ts_list, px_list, when):
    i = bisect_right(ts_list, int(when)) - 1

    if i < 0:
        return None

    return float(px_list[i])


def net_roi(gross_roi):
    fee_cost = (
        2.0
        * TAKER_FEE
        * LEVERAGE
    )

    slip = (
        2.0
        * (SLIPPAGE_BPS / 10000.0)
        * LEVERAGE
    )

    return float(
        gross_roi
        - fee_cost
        - slip
    )


def simulate_exit(
    entry_ts,
    entry_px,
    end_ts,
    ts_list,
    px_list,
):
    best_roi = 0.0
    armed = False

    t = int(entry_ts) + POLL_MS

    while t <= end_ts:
        px = market_price_at(
            ts_list,
            px_list,
            t,
        )

        if px is None:
            t += POLL_MS
            continue

        roi = (
            (float(px) / float(entry_px)) - 1.0
        ) * LEVERAGE

        best_roi = max(
            best_roi,
            roi,
        )

        # Current fixed ROI evaluator:
        # hard stop has first priority.
        if roi <= HARD_STOP:
            return {
                "exit_ts": t,
                "exit_px": px,
                "reason": "hard_stop",
                "gross_roi": roi,
                "best_roi": best_roi,
            }

        if best_roi >= TP_ARM:
            armed = True

        if (
            armed
            and (best_roi - roi) >= TP_GIVEBACK
        ):
            return {
                "exit_ts": t,
                "exit_px": px,
                "reason": "fixed_roi_giveback",
                "gross_roi": roi,
                "best_roi": best_roi,
            }

        t += POLL_MS

    px = market_price_at(
        ts_list,
        px_list,
        end_ts,
    )

    if px is None:
        px = entry_px

    roi = (
        (float(px) / float(entry_px)) - 1.0
    ) * LEVERAGE

    best_roi = max(
        best_roi,
        roi,
    )

    return {
        "exit_ts": end_ts,
        "exit_px": px,
        "reason": "window_end",
        "gross_roi": roi,
        "best_roi": best_roi,
    }


def candidate_allowed(row, mode):
    if str(row["sniper"]) != "PASS":
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


def run_window(window, mode):
    src = (
        RESULTS
        / f"SOLUSDT_{window}_replay.csv"
    )

    df = pd.read_csv(src)

    df = df.sort_values(
        "timestamp_ms"
    ).reset_index(drop=True)

    ts_list, px_list = load_trades(window)

    if not ts_list:
        return []

    window_end = int(ts_list[-1])

    trades = []
    next_free_ts = -1

    for _, row in df.iterrows():
        ts = int(row["timestamp_ms"])

        if ts <= next_free_ts:
            continue

        if not candidate_allowed(
            row,
            mode,
        ):
            continue

        entry_px = float(row["price"])

        result = simulate_exit(
            entry_ts=ts,
            entry_px=entry_px,
            end_ts=window_end,
            ts_list=ts_list,
            px_list=px_list,
        )

        gross = float(
            result["gross_roi"]
        )

        trades.append({
            "window": window,
            "mode": mode,
            "entry_time": row["time_trt"],
            "entry_ts": ts,
            "entry_px": entry_px,
            "model_score": float(
                row["model_score"]
            ),
            "entry_quality": row.get(
                "entry_quality"
            ),
            "retrace_ratio": row.get(
                "retrace_ratio"
            ),
            "exit_ts": int(
                result["exit_ts"]
            ),
            "exit_px": float(
                result["exit_px"]
            ),
            "exit_reason": result["reason"],
            "gross_roi": gross,
            "net_roi": net_roi(gross),
            "best_roi": float(
                result["best_roi"]
            ),
        })

        next_free_ts = int(
            result["exit_ts"]
        )

    return trades


def summarize(df, label):
    print()
    print(
        f"===== {label} ====="
    )

    if df.empty:
        print("NO_TRADES")
        return

    wins = int(
        (df["net_roi"] > 0).sum()
    )

    losses = int(
        (df["net_roi"] <= 0).sum()
    )

    print("trades=", len(df))
    print("wins=", wins)
    print("losses=", losses)

    print(
        "win_rate=",
        round(
            wins / len(df) * 100,
            2,
        ),
        "%",
    )

    print(
        "gross_roi_sum=",
        round(
            df["gross_roi"].sum()
            * 100,
            4,
        ),
        "%",
    )

    print(
        "net_roi_sum=",
        round(
            df["net_roi"].sum()
            * 100,
            4,
        ),
        "%",
    )

    print(
        "avg_net_roi=",
        round(
            df["net_roi"].mean()
            * 100,
            4,
        ),
        "%",
    )

    print(
        "median_net_roi=",
        round(
            df["net_roi"].median()
            * 100,
            4,
        ),
        "%",
    )

    print(
        "best_trade=",
        round(
            df["net_roi"].max()
            * 100,
            4,
        ),
        "%",
    )

    print(
        "worst_trade=",
        round(
            df["net_roi"].min()
            * 100,
            4,
        ),
        "%",
    )

    print()
    print("EXIT REASONS:")

    counts = Counter(
        df["exit_reason"]
    )

    for k, v in counts.items():
        print(k, v)


def main():
    print(
        "===== SOLUSDT TRADE LEVEL REPLAY ====="
    )

    print("leverage=", LEVERAGE)
    print("tp_arm=", TP_ARM)
    print("tp_giveback=", TP_GIVEBACK)
    print("hard_stop=", HARD_STOP)
    print("poll_ms=", POLL_MS)
    print("taker_fee_rate=", TAKER_FEE)
    print("slippage_bps=", SLIPPAGE_BPS)

    all_rows = []

    for mode in (
        "CURRENT_SHADOW",
        "CONFIRM_ENFORCED",
    ):
        for window in WINDOWS:
            rows = run_window(
                window,
                mode,
            )

            all_rows.extend(rows)

            d = pd.DataFrame(rows)

            summarize(
                d,
                f"{window} / {mode}",
            )

    final = pd.DataFrame(all_rows)

    out = (
        RESULTS
        / "SOLUSDT_trade_level_replay.csv"
    )

    final.to_csv(
        out,
        index=False,
    )

    print()
    print("===== COMBINED =====")

    for mode in (
        "CURRENT_SHADOW",
        "CONFIRM_ENFORCED",
    ):
        summarize(
            final[
                final["mode"] == mode
            ],
            mode,
        )

    print()
    print("OUTPUT=", out)
    print("TRADE_LEVEL_REPLAY_COMPLETE")


if __name__ == "__main__":
    main()
