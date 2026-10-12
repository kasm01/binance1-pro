from __future__ import annotations

from pathlib import Path
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "research" / "results"
OUT = RES / "NEAR_RESEARCH_PROMOTION_SCOREBOARD.csv"

MIN_PRELIM_N = 30
MIN_CANDIDATE_N = 100
MIN_PRODUCTION_N = 300
MIN_BUCKETS_PRELIM = 20
MIN_BUCKETS_CANDIDATE = 50
MIN_BUCKETS_PRODUCTION = 100

# SHORT strategy pipeline is not refactored yet. Market/execution research may continue,
# but strategy-derived SHORT (and mixed LONG+SHORT) evidence cannot be promoted.
STRATEGY_SHORT_LOCK_FAMILIES = {"entry_confirmation", "ema_regime", "micro_context_side"}


def _apply_architecture_lock(family: str, side: str, status: str):
    fam = str(family or "")
    side0 = str(side or "").lower()
    if fam == "micro_context" and side0 == "mixed":
        return "MIXED_RESEARCH_ONLY", "LONG_SHORT_MIXED_PRE_REFACTOR"
    if fam in STRATEGY_SHORT_LOCK_FAMILIES and side0 == "short":
        return "RESEARCH_ONLY", "SHORT_REFACTOR_REQUIRED"
    return status, "VALIDATION_NORMAL"


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else float("nan")
    except Exception:
        return float("nan")


def classify(*, n, buckets, net8, net10, net12, ci_lo=None, sessions=None, source_status="", winrate=None):
    n = int(n or 0)
    buckets = int(buckets or 0)
    sessions = int(sessions or 0) if sessions is not None else 0
    net8, net10, net12 = _f(net8), _f(net10), _f(net12)
    ci_lo = _f(ci_lo)
    winrate = _f(winrate)
    src = str(source_status or "").upper()

    if "REJECT" in src:
        return "REJECT"
    if n <= 0:
        return "OBSERVE"
    if n < MIN_PRELIM_N or buckets < MIN_BUCKETS_PRELIM:
        return "OBSERVE"
    if not math.isfinite(net8) or net8 <= 0:
        return "REJECT"

    # Preliminary: enough independent observations to inspect, but not enough to promote.
    status = "PRELIMINARY"

    robust_cost = math.isfinite(net10) and math.isfinite(net12) and net10 > 0 and net12 > 0
    ci_positive = math.isfinite(ci_lo) and ci_lo > 0
    win_ok = (not math.isfinite(winrate)) or winrate >= 0.55

    if n >= MIN_CANDIDATE_N and buckets >= MIN_BUCKETS_CANDIDATE and robust_cost and ci_positive and win_ok:
        status = "CANDIDATE"

    # Production requires much more evidence and more than one regime/session.
    if (
        status == "CANDIDATE"
        and n >= MIN_PRODUCTION_N
        and buckets >= MIN_BUCKETS_PRODUCTION
        and sessions >= 3
    ):
        status = "PRODUCTION_ELIGIBLE"

    return status


def add_entry_context(rows):
    p = RES / "NEAR_ENTRY_CONTEXT_ROBUST.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    for _, r in df.iterrows():
        n = int(r.get("trades", 0) or 0)
        buckets = int(r.get("unique_structure_buckets", 0) or 0)
        status = classify(
            n=n,
            buckets=buckets,
            net8=r.get("net_ev_8bps"),
            net10=r.get("net_ev_10bps"),
            net12=r.get("net_ev_12bps"),
            ci_lo=r.get("net_ci95_lo_8bps"),
            sessions=r.get("sessions", 0),
            source_status=r.get("evidence_status", ""),
            winrate=r.get("winrate"),
        )
        rows.append({
            "family": "micro_context",
            "item": f"{r.get('micro_feature')} + {r.get('context_feature')}",
            "side": "mixed",
            "horizon_s": r.get("horizon_s"),
            "n": n,
            "independent_buckets": buckets,
            "net8_bps": r.get("net_ev_8bps"),
            "net10_bps": r.get("net_ev_10bps"),
            "net12_bps": r.get("net_ev_12bps"),
            "ci_lo_net8_bps": r.get("net_ci95_lo_8bps"),
            "winrate": r.get("winrate"),
            "source_status": r.get("evidence_status", ""),
            "promotion_status": status,
        })


def add_entry_context_by_side(rows):
    p = RES / "NEAR_ENTRY_CONTEXT_BY_SIDE.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    for _, r in df.iterrows():
        n = int(r.get("trades", 0) or 0)
        buckets = int(r.get("unique_structure_buckets", 0) or 0)
        status = classify(
            n=n,
            buckets=buckets,
            net8=r.get("net_ev_8bps"),
            net10=r.get("net_ev_10bps"),
            net12=r.get("net_ev_12bps"),
            ci_lo=r.get("net_ci95_lo_8bps"),
            sessions=r.get("sessions_tested", 0),
            source_status=r.get("evidence_status", ""),
            winrate=r.get("winrate"),
        )
        rows.append({
            "family": "micro_context_side",
            "item": f"{r.get('micro_feature')} + {r.get('context_feature')}",
            "side": str(r.get("side")),
            "horizon_s": r.get("horizon_s"),
            "n": n,
            "independent_buckets": buckets,
            "net8_bps": r.get("net_ev_8bps"),
            "net10_bps": r.get("net_ev_10bps"),
            "net12_bps": r.get("net_ev_12bps"),
            "ci_lo_net8_bps": r.get("net_ci95_lo_8bps"),
            "winrate": r.get("winrate"),
            "source_status": r.get("evidence_status", ""),
            "promotion_status": status,
        })


def add_entry_confirmation(rows):
    p = RES / "NEAR_ENTRY_CONFIRMATION_SHADOW.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    for _, r in df.iterrows():
        n = int(r.get("n", 0) or 0)
        buckets = int(r.get("minute_buckets", 0) or 0)
        status = classify(
            n=n,
            buckets=buckets,
            net8=r.get("net_ev_8bps"),
            net10=r.get("net_ev_10bps"),
            net12=r.get("net_ev_12bps"),
            ci_lo=r.get("net_ci95_lo_8bps"),
            sessions=r.get("sessions", 0),
            source_status=r.get("status", ""),
            winrate=r.get("winrate"),
        )
        rows.append({
            "family": "entry_confirmation",
            "item": str(r.get("state")),
            "side": str(r.get("side")),
            "horizon_s": r.get("horizon_s"),
            "n": n,
            "independent_buckets": buckets,
            "net8_bps": r.get("net_ev_8bps"),
            "net10_bps": r.get("net_ev_10bps"),
            "net12_bps": r.get("net_ev_12bps"),
            "ci_lo_net8_bps": r.get("net_ci95_lo_8bps"),
            "winrate": r.get("winrate"),
            "source_status": r.get("status", ""),
            "promotion_status": status,
        })


def add_ema(rows):
    p = RES / "NEAR_EMA_REGIME.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    for _, r in df.iterrows():
        n = int(r.get("samples", 0) or 0)
        buckets = int(r.get("structure_buckets", 0) or 0)
        net8 = r.get("net_ev_8bps")
        # EMA analyzer currently has only base 8 bps cost; do not invent 10/12 bps evidence.
        status = "OBSERVE" if n < MIN_CANDIDATE_N else ("REJECT" if _f(net8) <= 0 else "PRELIMINARY")
        rows.append({
            "family": "ema_regime",
            "item": str(r.get("rule")),
            "side": "long" if "LONG" in str(r.get("rule")) or "GT" in str(r.get("rule")) else "short",
            "horizon_s": r.get("horizon_s"),
            "n": n,
            "independent_buckets": buckets,
            "net8_bps": net8,
            "net10_bps": float("nan"),
            "net12_bps": float("nan"),
            "ci_lo_net8_bps": float("nan"),
            "winrate": r.get("winrate"),
            "source_status": r.get("status", ""),
            "promotion_status": status,
        })


def add_execution(rows):
    p = RES / "NEAR_SHADOW_EXECUTION_SUMMARY.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    for _, r in df.iterrows():
        n = int(r.get("n", 0) or 0)
        adv = _f(r.get("avg_advantage_bps"))
        # Execution is an entry-cost advantage, not trade PnL. No fake CI or horizon metrics.
        sessions = int(r.get("sessions", 0) or 0)
        ci_lo = _f(r.get("adv_ci95_lo_bps"))
        if n < MIN_PRELIM_N:
            status = "OBSERVE"
        elif adv <= 0:
            status = "REJECT"
        elif n < MIN_CANDIDATE_N or sessions < 3 or not math.isfinite(ci_lo) or ci_lo <= 0:
            status = "PRELIMINARY"
        elif n < MIN_PRODUCTION_N:
            status = "CANDIDATE"
        else:
            status = "PRODUCTION_ELIGIBLE"
        rows.append({
            "family": "execution",
            "item": f"{r.get('fill_model')} wait={r.get('wait_s')}s maker_fee={r.get('maker_fee_bps')}bps",
            "side": str(r.get("side")),
            "horizon_s": r.get("wait_s"),
            "n": n,
            "independent_buckets": n,
            "net8_bps": adv,
            "net10_bps": float("nan"),
            "net12_bps": float("nan"),
            "ci_lo_net8_bps": r.get("adv_ci95_lo_bps"),
            "winrate": float("nan"),
            "source_status": r.get("status", ""),
            "promotion_status": status,
        })


def add_execution_queue(rows):
    p = RES / "NEAR_SHADOW_EXECUTION_QUEUE_SUMMARY.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    for _, r in df.iterrows():
        n = int(r.get("n", 0) or 0)
        adv = _f(r.get("avg_advantage_bps"))
        sessions = int(r.get("sessions", 0) or 0)
        ci_lo = _f(r.get("adv_ci95_lo_bps"))
        queue_mult = _f(r.get("queue_mult"))
        maker_fee = _f(r.get("maker_fee_bps"))
        conservative = (
            math.isfinite(queue_mult) and queue_mult >= 1.0
            and math.isfinite(maker_fee) and maker_fee >= 2.0
        )
        if n < MIN_PRELIM_N:
            status = "OBSERVE"
        elif not math.isfinite(adv) or adv <= 0:
            status = "REJECT"
        elif n < MIN_CANDIDATE_N or sessions < 3 or not math.isfinite(ci_lo) or ci_lo <= 0 or not adverse_ok:
            status = "PRELIMINARY"
        elif n < MIN_PRODUCTION_N or not conservative:
            status = "CANDIDATE"
        else:
            status = "PRODUCTION_ELIGIBLE"
        rows.append({
            "family": "execution_queue",
            "item": f"QUEUE ${r.get('notional_usdt')} x{queue_mult:g} wait={r.get('wait_s')}s maker_fee={maker_fee:g}bps",
            "side": str(r.get("side")),
            "horizon_s": r.get("wait_s"),
            "n": n,
            "independent_buckets": n,
            "net8_bps": adv,
            "net10_bps": float("nan"),
            "net12_bps": float("nan"),
            "ci_lo_net8_bps": r.get("adv_ci95_lo_bps"),
            "winrate": float("nan"),
            "source_status": r.get("status", ""),
            "promotion_status": status,
        })


def add_execution_queue_robust(rows):
    p = RES / "NEAR_SHADOW_EXECUTION_QUEUE_ROBUST.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    for _, r in df.iterrows():
        n = int(r.get("n_min", 0) or 0)
        sessions = int(r.get("sessions_min", 0) or 0)
        adv = _f(r.get("worst_avg_advantage_bps"))
        ci_lo = _f(r.get("worst_ci95_lo_bps"))
        markout5 = _f(r.get("worst_avg_maker_weighted_markout_5s_bps"))
        markout15 = _f(r.get("worst_avg_maker_weighted_markout_15s_bps"))
        wait_timing = _f(r.get("worst_avg_wait_timing_bps"))
        maker_incremental = _f(r.get("worst_avg_maker_incremental_bps"))
        qm = _f(r.get("queue_mult"))
        mf = _f(r.get("maker_fee_bps"))
        complete = bool(r.get("size_scenarios_complete"))
        validation_blocks = int(r.get("validation_blocks", sessions) or 0)
        positive_block_pct = _f(r.get("positive_block_pct"))
        safe_m5_block_pct = _f(r.get("safe_markout5_block_pct"))
        safe_m15_block_pct = _f(r.get("safe_markout15_block_pct"))
        conservative = math.isfinite(qm) and qm >= 1.0 and math.isfinite(mf) and mf >= 2.0
        adverse_ok = (
            math.isfinite(markout5) and markout5 >= 0.0
            and math.isfinite(markout15) and markout15 >= 0.0
        )
        candidate_block_ok = (
            validation_blocks >= 3
            and math.isfinite(positive_block_pct) and positive_block_pct >= 66.7
            and math.isfinite(safe_m5_block_pct) and safe_m5_block_pct >= 66.7
            and math.isfinite(safe_m15_block_pct) and safe_m15_block_pct >= 66.7
        )
        production_block_ok = (
            validation_blocks >= 6
            and positive_block_pct >= 75.0
            and safe_m5_block_pct >= 75.0
            and safe_m15_block_pct >= 75.0
        )
        if not complete or n < MIN_PRELIM_N:
            status = "OBSERVE"
            reason = "INSUFFICIENT_SIZE_ROBUST_DATA"
        elif not math.isfinite(adv) or adv <= 0:
            status = "REJECT"
            reason = "NON_POSITIVE_ADVANTAGE"
        elif not math.isfinite(maker_incremental) or maker_incremental <= 0:
            status = "REJECT"
            reason = "NON_POSITIVE_MAKER_INCREMENTAL"
        elif n < MIN_CANDIDATE_N:
            status = "PRELIMINARY"
            reason = "NEED_MORE_ANCHORS"
        elif not math.isfinite(ci_lo) or ci_lo <= 0:
            status = "PRELIMINARY"
            reason = "CI_NOT_POSITIVE"
        elif not adverse_ok:
            status = "PRELIMINARY"
            reason = "ADVERSE_SELECTION_FAIL"
        elif not candidate_block_ok:
            status = "PRELIMINARY"
            reason = "NEED_MORE_STABLE_BLOCKS"
        elif n < MIN_PRODUCTION_N:
            status = "CANDIDATE"
            reason = "NEED_MORE_PRODUCTION_SAMPLES"
        elif not conservative:
            status = "CANDIDATE"
            reason = "NON_CONSERVATIVE_QUEUE_OR_FEE"
        elif not production_block_ok:
            status = "CANDIDATE"
            reason = "NEED_MORE_PRODUCTION_BLOCKS"
        else:
            status = "PRODUCTION_ELIGIBLE"
            reason = "ALL_ROBUST_GATES_PASSED"
        rows.append({
            "family": "execution_queue_robust",
            "item": f"SIZE_ROBUST ${r.get('min_notional_usdt')}-${r.get('max_notional_usdt')} x{qm:g} wait={r.get('wait_s')}s maker_fee={mf:g}bps",
            "side": str(r.get("side")),
            "horizon_s": r.get("wait_s"),
            "n": n,
            "independent_buckets": n,
            "net8_bps": adv,
            "net10_bps": float("nan"),
            "net12_bps": float("nan"),
            "ci_lo_net8_bps": ci_lo,
            "maker_markout5_bps": markout5,
            "maker_markout15_bps": markout15,
            "wait_timing_bps": wait_timing,
            "maker_incremental_bps": maker_incremental,
            "validation_blocks": validation_blocks,
            "positive_block_pct": positive_block_pct,
            "safe_markout5_block_pct": safe_m5_block_pct,
            "safe_markout15_block_pct": safe_m15_block_pct,
            "promotion_reason": reason,
            "winrate": float("nan"),
            "source_status": r.get("status", ""),
            "promotion_status": status,
        })


def main():
    rows = []
    add_entry_context(rows)
    add_entry_context_by_side(rows)
    add_entry_confirmation(rows)
    add_ema(rows)
    add_execution(rows)
    add_execution_queue(rows)
    add_execution_queue_robust(rows)
    df = pd.DataFrame(rows)
    if df.empty:
        print("NO_SCOREBOARD_ROWS")
        return

    mask_individual_queue = (df["family"] == "execution_queue") & df["promotion_status"].isin(["CANDIDATE", "PRODUCTION_ELIGIBLE"])
    df.loc[mask_individual_queue, "promotion_status"] = "PRELIMINARY"

    locked = df.apply(
        lambda r: _apply_architecture_lock(
            r.get("family"), r.get("side"), r.get("promotion_status")
        ),
        axis=1,
    )
    df["promotion_status"] = [x[0] for x in locked]
    df["validation_state"] = [x[1] for x in locked]

    rank = {
        "PRODUCTION_ELIGIBLE": 0,
        "CANDIDATE": 1,
        "PRELIMINARY": 2,
        "OBSERVE": 3,
        "RESEARCH_ONLY": 4,
        "MIXED_RESEARCH_ONLY": 5,
        "REJECT": 6,
    }
    df["_rank"] = df["promotion_status"].map(rank).fillna(9)
    df = df.sort_values(["_rank", "family", "net8_bps"], ascending=[True, True, False]).drop(columns="_rank")
    df.to_csv(OUT, index=False)

    print("status_counts")
    print(df.promotion_status.value_counts().to_string())
    print("\nTOP")
    cols = ["family","item","side","horizon_s","n","independent_buckets","net8_bps","net10_bps","net12_bps","promotion_status"]
    print(df[cols].head(30).to_string(index=False))
    print("\nout", OUT)


if __name__ == "__main__":
    main()

