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

WINDOWS = ("A", "B", "C")

LEV = float(os.getenv("DEFAULT_ORDER_LEVERAGE", "3"))

FIXED_ENABLE = str(
    os.getenv("FIXED_ROI_TP_ENABLE", "0")
).lower() in ("1", "true", "yes", "on")

FIXED_TP = float(
    os.getenv("FIXED_ROI_TP_PCT", "0.0045")
)

FIXED_GIVEBACK = float(
    os.getenv("FIXED_ROI_TP_GIVEBACK", "0.0008")
)

ROI_HARD_STOP = float(
    os.getenv("ROI_HARD_STOP_PCT", "-0.075")
)

SL_PCT = float(
    os.getenv("SL_PCT", "0.01")
)

TP_PCT = float(
    os.getenv("TP_PCT", "0.02")
)

TRAILING_PCT = float(
    os.getenv("TRAILING_PCT", "0.03")
)

TRAILING_ACTIVATION = float(
    os.getenv("TRAILING_ACTIVATION_PCT", "0.003")
)

HARD_STOP_ENABLE = str(
    os.getenv("HARD_STOP_ENABLE", "0")
).lower() in ("1", "true", "yes", "on")

HARD_STOP_LOSS = float(
    os.getenv("HARD_STOP_LOSS_PCT", "0.04")
)

PROFIT_PROTECT_ENABLE = str(
    os.getenv("PROFIT_PROTECT_ENABLE", "0")
).lower() in ("1", "true", "yes", "on")

PROFIT_PROTECT_ARM = float(
    os.getenv("PROFIT_PROTECT_ARM_PCT", "0.020")
)

PROFIT_PROTECT_PULLBACK = float(
    os.getenv("PROFIT_PROTECT_PULLBACK_PCT", "0.004")
)

TP_RUNNER_ENABLE = str(
    os.getenv("TP_RUNNER_ENABLE", "0")
).lower() in ("1", "true", "yes", "on")

TP_ARM = float(
    os.getenv("TP_ARM_PNL_PCT", "0.020")
)

TP_RUNNER_PULLBACK = float(
    os.getenv("TP_RUNNER_PULLBACK_PCT", "0.006")
)

STALL_TTL = int(
    os.getenv("STALL_TTL_SEC", "1200")
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


def load_trades(window):
    path = DATA / f"SOLUSDT_{window}_aggTrades.json"
    raw = json.loads(path.read_text(encoding="utf-8"))

    ts = []
    px = []

    for x in raw:
        ts.append(int(x["T"]))
        px.append(float(x["p"]))

    return ts, px


def px_at(ts, pxs, when):
    idx = bisect_right(ts, int(when)) - 1

    if idx < 0:
        return None

    return float(pxs[idx])


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


def net_roi(gross):
    fees = 2.0 * TAKER_FEE * LEV
    slip = 2.0 * (SLIPPAGE_BPS / 10000.0) * LEV

    return gross - fees - slip


def simulate_exit(
    entry_ts,
    entry_px,
    end_ts,
    ts,
    pxs,
):
    best_roi = 0.0
    best_pnl = 0.0
    highest = float(entry_px)

    fixed_armed = False
    tp_runner_armed = False

    last_best_ts = int(entry_ts)

    t = int(entry_ts) + POLL_MS

    while t <= end_ts:
        px = px_at(ts, pxs, t)

        if px is None:
            t += POLL_MS
            continue

        pnl = (
            float(px) / float(entry_px)
            - 1.0
        )

        roi = pnl * LEV

        # =====================================================
        # PRODUCTION PRIORITY 1:
        # _evaluate_lifecycle_roi_exit
        # =====================================================

        if roi > best_roi:
            best_roi = roi

        if roi <= ROI_HARD_STOP:
            return {
                "exit_ts": t,
                "exit_px": px,
                "reason": "roi_hard_stop_lifecycle",
                "gross_roi": roi,
                "best_roi": best_roi,
            }

        if FIXED_ENABLE:
            if FIXED_GIVEBACK <= 0.0:
                if roi >= FIXED_TP:
                    return {
                        "exit_ts": t,
                        "exit_px": px,
                        "reason": "fixed_roi_tp_lifecycle",
                        "gross_roi": roi,
                        "best_roi": best_roi,
                    }

            else:
                if best_roi >= FIXED_TP:
                    fixed_armed = True

                if (
                    fixed_armed
                    and roi <= best_roi - FIXED_GIVEBACK
                ):
                    return {
                        "exit_ts": t,
                        "exit_px": px,
                        "reason": "fixed_roi_tp_lifecycle_lock",
                        "gross_roi": roi,
                        "best_roi": best_roi,
                    }

        # =====================================================
        # PRODUCTION PRIORITY 2:
        # _evaluate_position_lifecycle_exit
        # =====================================================

        highest = max(
            highest,
            float(px),
        )

        if pnl > best_pnl:
            best_pnl = pnl
            last_best_ts = t

        if (
            TP_RUNNER_ENABLE
            and best_pnl >= TP_ARM
        ):
            tp_runner_armed = True

        # Safety: hard stop then SL.
        if (
            HARD_STOP_ENABLE
            and pnl <= -abs(HARD_STOP_LOSS)
        ):
            return {
                "exit_ts": t,
                "exit_px": px,
                "reason": "hard_stop_hit",
                "gross_roi": roi,
                "best_roi": best_roi,
            }

        if (
            SL_PCT > 0
            and float(px)
            <= float(entry_px) * (1.0 - SL_PCT)
        ):
            return {
                "exit_ts": t,
                "exit_px": px,
                "reason": "sl_hit",
                "gross_roi": roi,
                "best_roi": best_roi,
            }

        # Profit protect.
        protect_armed = (
            PROFIT_PROTECT_ENABLE
            and best_pnl >= PROFIT_PROTECT_ARM
        )

        if protect_armed:
            pullback = (
                (highest - float(px))
                / max(highest, 1e-12)
            )

            if pullback >= PROFIT_PROTECT_PULLBACK:
                return {
                    "exit_ts": t,
                    "exit_px": px,
                    "reason": "profit_protect_pullback",
                    "gross_roi": roi,
                    "best_roi": best_roi,
                }

        # Trailing.
        trailing_armed = (
            TRAILING_PCT > 0
            and highest > entry_px
            and (
                TRAILING_ACTIVATION <= 0
                or best_pnl >= TRAILING_ACTIVATION
            )
        )

        if trailing_armed:
            trail_stop = (
                highest
                * (1.0 - TRAILING_PCT)
            )

            if float(px) <= trail_stop:
                return {
                    "exit_ts": t,
                    "exit_px": px,
                    "reason": "trailing_hit",
                    "gross_roi": roi,
                    "best_roi": best_roi,
                }

        # TP runner.
        if (
            tp_runner_armed
            and (
                best_pnl - pnl
            ) >= TP_RUNNER_PULLBACK
        ):
            return {
                "exit_ts": t,
                "exit_px": px,
                "reason": "tp_runner_exit",
                "gross_roi": roi,
                "best_roi": best_roi,
            }

        # Conventional TP.
        if (
            TP_PCT > 0
            and float(px)
            >= float(entry_px) * (1.0 + TP_PCT)
        ):
            return {
                "exit_ts": t,
                "exit_px": px,
                "reason": "tp_hit",
                "gross_roi": roi,
                "best_roi": best_roi,
            }

        # Scalp disabled in current env.
        # Reverse signal intentionally NOT simulated.
        # Profit lock disabled.
        # USDT loss kill disabled.
        # Dead trade disabled.

        if (
            STALL_TTL > 0
            and (t - last_best_ts)
            >= STALL_TTL * 1000
        ):
            return {
                "exit_ts": t,
                "exit_px": px,
                "reason": "stall_exit",
                "gross_roi": roi,
                "best_roi": best_roi,
            }

        t += POLL_MS

    px = px_at(ts, pxs, end_ts)

    if px is None:
        px = entry_px

    pnl = (
        float(px) / float(entry_px)
        - 1.0
    )

    roi = pnl * LEV

    return {
        "exit_ts": int(end_ts),
        "exit_px": float(px),
        "reason": "window_end",
        "gross_roi": roi,
        "best_roi": max(best_roi, roi),
    }


def run_window(window, mode):
    src = RESULTS / f"SOLUSDT_{window}_replay.csv"
    df = pd.read_csv(src)

    df = df.sort_values(
        "timestamp_ms"
    ).reset_index(drop=True)

    ts, pxs = load_trades(window)

    if not ts:
        return []

    end_ts = int(ts[-1])

    out = []
    next_free_ts = -1

    for _, row in df.iterrows():
        now = int(row["timestamp_ms"])

        if now <= next_free_ts:
            continue

        if not candidate_allowed(row, mode):
            continue

        entry_px = float(row["price"])

        result = simulate_exit(
            entry_ts=now,
            entry_px=entry_px,
            end_ts=end_ts,
            ts=ts,
            pxs=pxs,
        )

        gross = float(
            result["gross_roi"]
        )

        out.append({
            "window": window,
            "mode": mode,
            "entry_time": row["time_trt"],
            "entry_ts": now,
            "entry_px": entry_px,
            "model_score": float(row["model_score"]),
            "entry_quality": row.get("entry_quality"),
            "retrace_ratio": row.get("retrace_ratio"),
            "exit_ts": int(result["exit_ts"]),
            "exit_px": float(result["exit_px"]),
            "exit_reason": result["reason"],
            "gross_roi": gross,
            "net_roi": net_roi(gross),
            "best_roi": float(result["best_roi"]),
        })

        next_free_ts = int(
            result["exit_ts"]
        )

    return out


def summarize(df, label):
    print()
    print(f"===== {label} =====")

    if df.empty:
        print("NO_TRADES")
        return

    wins = int(
        (df["net_roi"] > 0).sum()
    )

    losses = len(df) - wins

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
            df["gross_roi"].sum() * 100,
            4,
        ),
        "%",
    )

    print(
        "net_roi_sum=",
        round(
            df["net_roi"].sum() * 100,
            4,
        ),
        "%",
    )

    print(
        "avg_net_roi=",
        round(
            df["net_roi"].mean() * 100,
            4,
        ),
        "%",
    )

    print(
        "median_net_roi=",
        round(
            df["net_roi"].median() * 100,
            4,
        ),
        "%",
    )

    print(
        "best_trade=",
        round(
            df["net_roi"].max() * 100,
            4,
        ),
        "%",
    )

    print(
        "worst_trade=",
        round(
            df["net_roi"].min() * 100,
            4,
        ),
        "%",
    )

    print()
    print("EXIT REASONS:")

    for k, v in Counter(
        df["exit_reason"]
    ).items():
        print(k, v)


def main():
    print("===== SOLUSDT TRADE REPLAY V2 =====")

    print("leverage=", LEV)
    print("fixed_tp=", FIXED_TP)
    print("fixed_giveback=", FIXED_GIVEBACK)
    print("roi_hard_stop=", ROI_HARD_STOP)
    print("sl_pct=", SL_PCT)
    print("tp_pct=", TP_PCT)
    print("trailing_pct=", TRAILING_PCT)
    print("trailing_activation=", TRAILING_ACTIVATION)
    print("stall_ttl=", STALL_TTL)
    print("poll_ms=", POLL_MS)
    print("fee=", TAKER_FEE)
    print("reverse_simulated=NO")

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

            summarize(
                pd.DataFrame(rows),
                f"{window} / {mode}",
            )

    final = pd.DataFrame(all_rows)

    out = (
        RESULTS
        / "SOLUSDT_trade_level_replay_v2.csv"
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
    print("TRADE_LEVEL_REPLAY_V2_COMPLETE")


if __name__ == "__main__":
    main()
