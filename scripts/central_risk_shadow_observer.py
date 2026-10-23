#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import redis

from core.binance_futures_v3 import account
from orchestration.risk.central_risk_master import PortfolioRiskState, PositionExposure
from orchestration.risk.central_risk_shadow_profile import build_shadow_master, describe_profile

LOG_DIR = ROOT / "logs"
STATE_PATH = LOG_DIR / "central_risk_shadow_state.json"
JSONL_PATH = LOG_DIR / "central_risk_shadow.jsonl"
STREAM = os.getenv("CENTRAL_RISK_SHADOW_STREAM", "telemetry:central_risk:shadow")
CURRENT_KEY = os.getenv("CENTRAL_RISK_SHADOW_CURRENT_KEY", "telemetry:central_risk:shadow:current")
MAXLEN = int(os.getenv("CENTRAL_RISK_SHADOW_MAXLEN", "5000") or 5000)
TTL_SEC = int(os.getenv("CENTRAL_RISK_SHADOW_TTL_SEC", "900") or 900)


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _strategy_id(symbol: str, side: str) -> str:
    key = (str(symbol).upper().strip(), str(side).lower().strip())
    mapping = {
        ("NEARUSDT", "long"): "LONG1",
        ("INJUSDT", "short"): "SHORT1",
    }
    return mapping.get(key, f"UNMAPPED:{key[0]}:{key[1].upper()}")


def _mtm_notional(row: Dict[str, Any]) -> Tuple[float, float, str]:
    qty = _f(row.get("positionAmt"))
    if qty == 0.0:
        return 0.0, 0.0, "none"
    direct = abs(_f(row.get("notional")))
    if direct > 0.0:
        mark = direct / abs(qty)
        return direct, mark, "account_notional"
    mark = _f(row.get("markPrice"))
    if mark > 0.0:
        return abs(qty * mark), mark, "account_mark"
    entry = _f(row.get("entryPrice"))
    upnl = _f(row.get("unrealizedProfit"))
    if entry > 0.0:
        # USD-M linear contract identity: uPnL = positionAmt * (mark-entry).
        inferred_mark = entry + (upnl / qty)
        if inferred_mark > 0.0:
            return abs(qty * inferred_mark), inferred_mark, "inferred_mark_from_upnl"
        return abs(qty * entry), entry, "entry_price_fallback"
    return 0.0, 0.0, "unknown"


def _load_state(equity: float) -> PortfolioRiskState:
    try:
        obj = json.loads(STATE_PATH.read_text())
        return PortfolioRiskState(
            equity_peak=max(_f(obj.get("equity_peak"), equity), equity),
            mode=str(obj.get("mode") or "NORMAL"),
            recovery_successes=int(obj.get("recovery_successes") or 0),
        )
    except Exception:
        return PortfolioRiskState(equity_peak=float(equity), mode="NORMAL", recovery_successes=0)


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.time()
    acc = account()  # exactly one external REST call per observer run
    equity = _f(acc.get("totalMarginBalance"), _f(acc.get("totalWalletBalance")))
    wallet = _f(acc.get("totalWalletBalance"))
    upnl = _f(acc.get("totalUnrealizedProfit"))

    positions: List[PositionExposure] = []
    position_rows: List[Dict[str, Any]] = []
    for row in acc.get("positions") or []:
        if not isinstance(row, dict):
            continue
        qty = _f(row.get("positionAmt"))
        if abs(qty) <= 0.0:
            continue
        symbol = str(row.get("symbol") or "").upper().strip()
        side = "long" if qty > 0 else "short"
        notional, mark, mark_source = _mtm_notional(row)
        if notional <= 0.0:
            continue
        sid = _strategy_id(symbol, side)
        positions.append(PositionExposure(sid, symbol, side, notional, "NORMAL"))
        position_rows.append({
            "strategy_id": sid,
            "symbol": symbol,
            "side": side,
            "qty": abs(qty),
            "entry_price": _f(row.get("entryPrice")),
            "mark_price": mark,
            "mark_source": mark_source,
            "notional": notional,
            "unrealized_pnl": _f(row.get("unrealizedProfit")),
            "leverage": _f(row.get("leverage")),
        })

    master = build_shadow_master()
    profile = describe_profile()
    prior = _load_state(equity)
    state, state_reasons = master.update_state_on_mtm(state=prior, mtm_equity=equity)
    health = master.evaluate_exposure_health(portfolio_equity=equity, positions=positions)
    cfg = master.config

    symbol_totals: Dict[str, float] = {}
    for p in positions:
        symbol_totals[p.symbol] = symbol_totals.get(p.symbol, 0.0) + float(p.notional)
    symbol_cap = cfg.max_symbol_exposure_ratio
    warn_frac = float(cfg.exposure_warning_fraction)
    symbol_health: Dict[str, Dict[str, Any]] = {}
    for symbol, notional in sorted(symbol_totals.items()):
        ratio = notional / max(equity, 1e-12)
        status = "OK"
        if symbol_cap is not None and ratio > float(symbol_cap) + 1e-12:
            status = "BREACH"
        elif symbol_cap is not None and ratio >= float(symbol_cap) * warn_frac:
            status = "WARNING"
        symbol_health[symbol] = {"notional": notional, "ratio": ratio, "status": status}

    dd = (equity / state.equity_peak - 1.0) if state.equity_peak > 0 else 0.0
    report: Dict[str, Any] = {
        "schema_version": "central_risk_shadow_observer.v1",
        "ts": ts,
        "profile_id": profile["profile_id"],
        "stage": profile["stage"],
        "authority": "SHADOW_ONLY",
        "production_ready": bool(profile["production_ready"]),
        "production_issues": profile["production_issues"],
        "account": {
            "wallet_balance": wallet,
            "unrealized_pnl": upnl,
            "mtm_equity": equity,
            "available_balance": _f(acc.get("availableBalance")),
        },
        "portfolio_state": {
            **state.to_dict(),
            "drawdown_ratio": dd,
            "reasons": list(state_reasons),
        },
        "exposure_health": health.to_dict(),
        "symbol_health": symbol_health,
        "positions": position_rows,
        "caps": {
            "gross": cfg.max_gross_exposure_ratio,
            "long": cfg.max_long_exposure_ratio,
            "short": cfg.max_short_exposure_ratio,
            "abs_net": cfg.max_abs_net_exposure_ratio,
            "symbol": cfg.max_symbol_exposure_ratio,
            "warning_fraction": cfg.exposure_warning_fraction,
        },
    }

    STATE_PATH.write_text(json.dumps(state.to_dict(), indent=2, allow_nan=False))
    raw = json.dumps(report, separators=(",", ":"), allow_nan=False)
    with JSONL_PATH.open("a", encoding="utf-8") as f:
        f.write(raw + "\n")

    try:
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True,
            socket_timeout=1.0,
        )
        r.xadd(STREAM, {"json": raw}, maxlen=MAXLEN, approximate=True)
        r.setex(CURRENT_KEY, TTL_SEC, raw)
    except Exception as e:
        print(f"[CENTRAL-RISK-SHADOW][WARN] redis telemetry failed: {e}")

    h = report["exposure_health"]
    print(
        "CENTRAL_RISK_SHADOW "
        f"status={h['status']} mode={state.normalized_mode()} equity={equity:.8f} "
        f"dd={dd:.4%} positions={h['open_positions'] if 'open_positions' in h else len(positions)} "
        f"gross={h['gross_ratio']:.4f} long={h['long_ratio']:.4f} "
        f"short={h['short_ratio']:.4f} abs_net={h['abs_net_ratio']:.4f} "
        f"production_ready={report['production_ready']}"
    )
    for row in position_rows:
        print(
            "  POSITION "
            f"{row['strategy_id']} {row['symbol']} {row['side']} "
            f"notional={row['notional']:.4f} mark={row['mark_price']:.8f} "
            f"src={row['mark_source']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
