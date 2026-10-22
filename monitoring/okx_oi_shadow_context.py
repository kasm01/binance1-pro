from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from orchestration.context.entry_context_snapshot import strictly_prior_oi_snapshot
from orchestration.context.market_context_contract import classify_confirmed_position_build

SNAPSHOT_PREFIX = "shadow:market_context:okx_oi:"
STRUCTURE_PREFIX = "shadow:market_context:binance_structure:"
COMBINED_PREFIX = "shadow:market_context:combined:"
CANDIDATE_STREAM = "shadow:telemetry:entry_context"


def _f(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None




def _period_seconds(period: Any) -> Optional[float]:
    """Convert OKX period strings (5m,1H,4H,1D) to seconds."""
    try:
        raw = str(period or "").strip()
        if not raw:
            return None
        unit = raw[-1].lower()
        value = float(raw[:-1])
        mult = {"m": 60.0, "h": 3600.0, "d": 86400.0}.get(unit)
        if mult is None or value <= 0:
            return None
        return value * mult
    except Exception:
        return None

def read_okx_oi_shadow(
    redis_client: Any,
    symbol: str,
    *,
    max_cache_age_sec: float = 330.0,
    max_source_age_sec: float = 21600.0,
) -> Dict[str, Any]:
    sym = str(symbol or "").upper().strip()
    out: Dict[str, Any] = {
        "symbol": sym,
        "status": "UNKNOWN",
        "oi_direction": "UNKNOWN",
        "oi_ret_period": None,
        "cache_age_sec": None,
        "source_age_sec": None,
        "period": None,
    }
    if redis_client is None or not sym:
        return out
    try:
        raw = redis_client.get(f"{SNAPSHOT_PREFIX}{sym}")
        if not raw:
            out["status"] = "MISSING"
            return out
        obj = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(obj, dict):
            out["status"] = "INVALID"
            return out
        now_ms = int(time.time() * 1000)
        observed_ms = int(obj.get("observed_at_ms") or 0)
        cache_age = max(0.0, (now_ms - observed_ms) / 1000.0) if observed_ms > 0 else None
        source_age = _f(obj.get("source_age_sec"))
        period = obj.get("period")
        period_sec = _period_seconds(period)
        # For bucketed OI history, source_ts is the period bucket timestamp.
        # A 4H row can therefore be ~0..4H old while still being the current bucket.
        # Treat source freshness relative to its native period, not like tick data.
        dynamic_source_limit = float(max_source_age_sec)
        if period_sec is not None:
            dynamic_source_limit = max(dynamic_source_limit, period_sec * 1.50)
        source_phase = (source_age % period_sec) if (source_age is not None and period_sec) else None
        out.update({
            "status": str(obj.get("status") or "UNKNOWN").upper(),
            "oi_direction": str(obj.get("oi_direction") or "UNKNOWN").upper(),
            "oi_ret_period": _f(obj.get("oi_ret_period")),
            "cache_age_sec": cache_age,
            "source_age_sec": source_age,
            "period": period,
            "period_sec": period_sec,
            "source_phase_age_sec": source_phase,
            "source_fresh_limit_sec": dynamic_source_limit,
            "source_ts_ms": obj.get("source_ts_ms"),
        })
        stale = (
            (cache_age is None or cache_age > float(max_cache_age_sec))
            or (source_age is None or source_age > dynamic_source_limit)
        )
        if stale:
            out["status"] = "STALE"
        return out
    except Exception as exc:
        out["status"] = "ERROR"
        out["error"] = type(exc).__name__
        return out



def read_binance_structure_shadow(
    redis_client: Any,
    symbol: str,
    *,
    max_cache_age_sec: float = 210.0,
    max_source_age_sec: float = 180.0,
) -> Dict[str, Any]:
    sym = str(symbol or "").upper().strip()
    out: Dict[str, Any] = {
        "symbol": sym, "status": "UNKNOWN", "m1_ret1": None, "m3_ret1": None,
        "deep_pullback": None, "low_recovery": None, "price_down_3m": None,
        "cache_age_sec": None, "source_age_sec": None,
    }
    if redis_client is None or not sym:
        return out
    try:
        raw = redis_client.get(f"{STRUCTURE_PREFIX}{sym}")
        if not raw:
            out["status"] = "MISSING"; return out
        obj = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(obj, dict):
            out["status"] = "INVALID"; return out
        now_ms = int(time.time() * 1000)
        observed_ms = int(obj.get("observed_at_ms") or 0)
        cache_age = max(0.0, (now_ms-observed_ms)/1000.0) if observed_ms > 0 else None
        source_age = _f(obj.get("source_age_sec"))
        out.update({
            "status": str(obj.get("status") or "UNKNOWN").upper(),
            "m1_ret1": _f(obj.get("m1_ret1")), "m3_ret1": _f(obj.get("m3_ret1")),
            "deep_pullback": obj.get("deep_pullback"), "low_recovery": obj.get("low_recovery"),
            "price_down_3m": obj.get("price_down_3m"), "recovery_from_low": _f(obj.get("recovery_from_low")),
            "cache_age_sec": cache_age, "source_age_sec": source_age,
            "source_close_time_ms": obj.get("source_close_time_ms"),
            "research_3m_close_time_ms": obj.get("research_3m_close_time_ms"),
            "research_m3_ret1": _f(obj.get("research_m3_ret1")),
            "research_m3_ret2": _f(obj.get("research_m3_ret2")),
            "research_m3_ret3": _f(obj.get("research_m3_ret3")),
            "research_m3_up_frac3": _f(obj.get("research_m3_up_frac3")),
            "research_m3_ret1_mean3": _f(obj.get("research_m3_ret1_mean3")),
            "research_m3_ret1_accel": _f(obj.get("research_m3_ret1_accel")),
            "research_m3_buy_ratio": _f(obj.get("research_m3_buy_ratio")),
            "research_m3_imbalance": _f(obj.get("research_m3_imbalance")),
            "research_m3_imb_mean3": _f(obj.get("research_m3_imb_mean3")),
            "research_m3_flow15_completed": _f(obj.get("research_m3_flow15_completed")),
            "research_m3_flow60_completed": _f(obj.get("research_m3_flow60_completed")),
            "research_m3_body": _f(obj.get("research_m3_body")),
            "research_m3_range": _f(obj.get("research_m3_range")),
            "research_m3_close_loc": _f(obj.get("research_m3_close_loc")),
            "research_m3_lower_wick_frac": _f(obj.get("research_m3_lower_wick_frac")),
            "research_m3_atr14_pct": _f(obj.get("research_m3_atr14_pct")),
            "research_m3_atr_rank_240": _f(obj.get("research_m3_atr_rank_240")),
            "research_m3_atr_rank_history": obj.get("research_m3_atr_rank_history"),
        })
        if cache_age is None or cache_age > max_cache_age_sec or source_age is None or source_age > max_source_age_sec:
            out["status"] = "STALE"
        return out
    except Exception as exc:
        out["status"] = "ERROR"; out["error"] = type(exc).__name__; return out



def read_market_context_shadow(redis_client: Any, symbol: str, *, max_cache_age_sec: float = 210.0) -> Dict[str, Any]:
    """Read the normalized combined MARKET CONTEXT snapshot with one local Redis GET."""
    sym = str(symbol or "").upper().strip()
    out: Dict[str, Any] = {"symbol": sym, "status": "UNKNOWN", "okx_oi": {}, "binance_structure": {}, "derived": {}}
    if redis_client is None or not sym:
        return out
    try:
        raw = redis_client.get(f"{COMBINED_PREFIX}{sym}")
        if not raw:
            out["status"] = "MISSING"
            return out
        obj = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(obj, dict):
            out["status"] = "INVALID"
            return out
        now_ms = int(time.time() * 1000)
        observed_ms = int(obj.get("observed_at_ms") or 0)
        cache_age = max(0.0, (now_ms-observed_ms)/1000.0) if observed_ms > 0 else None
        out.update(obj)
        out["cache_age_sec"] = cache_age
        if cache_age is None or cache_age > float(max_cache_age_sec):
            out["status"] = "STALE"
        return out
    except Exception as exc:
        out["status"] = "ERROR"
        out["error"] = type(exc).__name__
        return out

def emit_entry_context_shadow(
    redis_client: Any,
    *,
    symbol: str,
    side: str,
    signal_score: float,
    open_min_score: float,
    entry_interval: str,
    oi_context: Dict[str, Any],
    structure_context: Optional[Dict[str, Any]] = None,
    micro_context: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    maxlen: int = 30000,
) -> bool:
    if redis_client is None:
        return False
    sym = str(symbol or "").upper().strip()
    side_norm = str(side or "").lower().strip()
    if not sym or side_norm not in ("long", "short"):
        return False
    try:
        now_ms = int(time.time() * 1000)
        bucket = now_ms // 60000
        marker = f"shadow:telemetry:entry_context:dedupe:{sym}:{side_norm}:{bucket}"
        if not redis_client.set(marker, "1", nx=True, ex=90):
            return False

        x = extra if isinstance(extra, dict) else {}
        st = structure_context if isinstance(structure_context, dict) else {}
        micro = micro_context if isinstance(micro_context, dict) else {}
        oi_ok = str(oi_context.get("status") or "").upper() == "OK"
        st_ok = str(st.get("status") or "").upper() == "OK"
        structure_oi_support = bool(
            oi_ok and st_ok and str(oi_context.get("oi_direction") or "").upper() == "UP"
            and st.get("deep_pullback") is True and st.get("low_recovery") is True
            and st.get("price_down_3m") is True
        )

        # Canonical SHORT-style entry-time OI/price/flow context, telemetry only.
        # OI comes from one central 5m collector; price/flow inputs are reused
        # from the same 1m request that supplied ENTRY CONFIRMATION.
        entry_ctx_v1: Dict[str, Any] = {
            "available": False,
            "schema_version": "entry_market_context.v1",
            "reason": "missing_entry_inputs",
            "policy_effect": "TELEMETRY_ONLY",
        }
        try:
            confirm_open_ms = int(float(x.get("entry_confirmation_open_ms") or 0))
            ret15 = x.get("entry_price_return_15m")
            flow15 = x.get("entry_money_flow_15m")
            raw_oi = redis_client.get(f"context:oi:{sym}")
            oi_obj = json.loads(raw_oi) if isinstance(raw_oi, str) else (raw_oi if isinstance(raw_oi, dict) else {})
            if confirm_open_ms > 0 and ret15 is not None and flow15 is not None and isinstance(oi_obj, dict):
                oi_sel = strictly_prior_oi_snapshot(oi_obj, cutoff_open_ms=confirm_open_ms)
                if oi_sel.get("available"):
                    regime = classify_confirmed_position_build(
                        oi_delta_15m=oi_sel.get("oi_delta_15m"),
                        price_return_15m=ret15,
                        money_flow_15m=flow15,
                    )
                    entry_ctx_v1 = {
                        "available": True,
                        "schema_version": "entry_market_context.v1",
                        "snapshot_stage": "preorder_completed_1m",
                        "confirmation_open_ms": confirm_open_ms,
                        "price_response": {"return_15m": float(ret15)},
                        "money_flow": {"flow_15m": float(flow15)},
                        "open_interest": oi_sel,
                        "regime": {
                            "name": regime.get("name"),
                            "build_direction": regime.get("build_direction"),
                        },
                        "policy_effect": "TELEMETRY_ONLY",
                    }
                else:
                    entry_ctx_v1["reason"] = "missing_causal_oi"
                    entry_ctx_v1["open_interest"] = oi_sel
        except Exception as exc:
            entry_ctx_v1 = {
                "available": False,
                "schema_version": "entry_market_context.v1",
                "reason": "entry_context_exception",
                "error": type(exc).__name__,
                "policy_effect": "TELEMETRY_ONLY",
            }

        payload = {
            "schema_version": 1,
            "shadow_only": True,
            "observed_at_ms": now_ms,
            "symbol": sym,
            "side": side_norm,
            "signal_score": float(signal_score),
            "open_min_score": float(open_min_score),
            "score_margin": float(signal_score) - float(open_min_score),
            "entry_interval": str(entry_interval or ""),
            "oi_status": str(oi_context.get("status") or "UNKNOWN"),
            "oi_direction": str(oi_context.get("oi_direction") or "UNKNOWN"),
            "oi_ret_period": oi_context.get("oi_ret_period"),
            "oi_cache_age_sec": oi_context.get("cache_age_sec"),
            "oi_source_age_sec": oi_context.get("source_age_sec"),
            "oi_source_phase_age_sec": oi_context.get("source_phase_age_sec"),
            "oi_source_fresh_limit_sec": oi_context.get("source_fresh_limit_sec"),
            "oi_period": oi_context.get("period"),
            "oi_period_sec": oi_context.get("period_sec"),
            "structure_status": str(st.get("status") or "UNKNOWN"),
            "structure_cache_age_sec": st.get("cache_age_sec"),
            "structure_source_age_sec": st.get("source_age_sec"),
            "m1_ret1": st.get("m1_ret1"),
            "m3_ret1": st.get("m3_ret1"),
            "research_m3_ret1": st.get("research_m3_ret1"),
            "research_m3_ret2": st.get("research_m3_ret2"),
            "research_m3_ret3": st.get("research_m3_ret3"),
            "research_m3_up_frac3": st.get("research_m3_up_frac3"),
            "research_m3_ret1_mean3": st.get("research_m3_ret1_mean3"),
            "research_m3_ret1_accel": st.get("research_m3_ret1_accel"),
            "research_m3_buy_ratio": st.get("research_m3_buy_ratio"),
            "research_m3_imbalance": st.get("research_m3_imbalance"),
            "research_m3_imb_mean3": st.get("research_m3_imb_mean3"),
            "research_m3_flow15_completed": st.get("research_m3_flow15_completed"),
            "research_m3_flow60_completed": st.get("research_m3_flow60_completed"),
            "long_money_flow_exhaustion": bool(
                st_ok
                and st.get("research_m3_flow60_completed") is not None
                and float(st.get("research_m3_flow60_completed")) >= float(os.getenv("LONG_MONEY_FLOW_EXHAUSTION_60M", "0.15") or 0.15)
            ),
            "long_money_flow_exhaustion_threshold": float(os.getenv("LONG_MONEY_FLOW_EXHAUSTION_60M", "0.15") or 0.15),
            "long_money_flow_policy": "SHADOW_ONLY_NEW_ENTRY_VETO_CANDIDATE",
            "research_m3_body": st.get("research_m3_body"),
            "research_m3_range": st.get("research_m3_range"),
            "research_m3_close_loc": st.get("research_m3_close_loc"),
            "deep_pullback": st.get("deep_pullback"),
            "low_recovery": st.get("low_recovery"),
            "price_down_3m": st.get("price_down_3m"),
            "micro_status": str(micro.get("status") or "UNKNOWN"),
            "micro_cache_age_sec": micro.get("cache_age_sec"),
            "micro_event_age_sec": micro.get("event_age_sec"),
            "micro_spread_bps": micro.get("spread_bps"),
            "micro_basis_bps": micro.get("basis_bps"),
            "micro_funding_rate": micro.get("funding_rate"),
            "micro_mark_price": micro.get("mark_price"),
            "micro_index_price": micro.get("index_price"),
            "micro_microprice_dev_bps": micro.get("microprice_dev_bps"),
            "micro_l1_imbalance": micro.get("l1_imbalance"),
            "micro_depth5_imbalance": micro.get("depth5_imbalance"),
            "micro_depth20_imbalance": micro.get("depth20_imbalance"),
            "micro_t5_count": micro.get("t5_count"),
            "micro_t5_buy_ratio": micro.get("t5_buy_ratio"),
            "micro_t5_signed_ratio": micro.get("t5_signed_ratio"),
            "micro_t15_count": micro.get("t15_count"),
            "micro_t15_buy_ratio": micro.get("t15_buy_ratio"),
            "micro_t15_signed_ratio": micro.get("t15_signed_ratio"),
            "micro_t30_count": micro.get("t30_count"),
            "micro_t30_signed_ratio": micro.get("t30_signed_ratio"),
            "structure_oi_support": structure_oi_support,
            "entry_market_context": entry_ctx_v1,
            "quality_band": x.get("quality_band"),
            "near_oi_recovery_support": "UNKNOWN",
        }
        raw_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        redis_client.xadd(
            CANDIDATE_STREAM,
            {"json": raw_payload},
            maxlen=int(maxlen),
            approximate=True,
        )
        redis_client.set(
            f"shadow:telemetry:entry_context:last:{sym}:{side_norm}",
            raw_payload,
            ex=7200,
        )
        return True
    except Exception:
        return False


def mark_position_open_shadow(
    redis_client: Any,
    *,
    symbol: str,
    side: str,
    entry_price: float,
    signal_score: float,
    intent_id: str = "",
    qty: float = 0.0,
    notional: float = 0.0,
    leverage: float = 1.0,
    open_order_id: str = "",
    open_client_order_id: str = "",
    ttl_sec: int = 172800,
) -> bool:
    if redis_client is None:
        return False
    sym = str(symbol or "").upper().strip()
    side_norm = str(side or "").lower().strip()
    try:
        last_key = f"shadow:telemetry:entry_context:last:{sym}:{side_norm}"
        raw = redis_client.get(last_key)
        ctx = json.loads(raw) if raw else {}
        if not isinstance(ctx, dict):
            ctx = {}
        opened_ms = int(time.time() * 1000)
        intent_norm = str(intent_id or "").strip()
        trade_id = intent_norm or f"{sym}:{side_norm}:{opened_ms}"
        payload = dict(ctx)
        payload.update({
            "trade_id": trade_id,
            "intent_id": intent_norm,
            "position_open_at_ms": opened_ms,
            "position_entry_price": float(entry_price),
            "position_qty": float(qty or 0.0),
            "position_notional": float(notional or 0.0),
            "position_leverage": float(leverage or 1.0),
            "position_signal_score": float(signal_score),
            "position_side": side_norm,
            "position_symbol": sym,
            "open_order_id": str(open_order_id or ""),
            "open_client_order_id": str(open_client_order_id or ""),
            "shadow_only": True,
        })
        active_key = f"shadow:telemetry:position_context:active:{sym}:{side_norm}"
        redis_client.set(active_key, json.dumps(payload, ensure_ascii=False), ex=int(ttl_sec))
        redis_client.xadd(
            "shadow:telemetry:position_open",
            {"json": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
            maxlen=10000,
            approximate=True,
        )

        # Research-only execution mapping. Link the verified live MARKET fill to the
        # most recent L1 snapshot at-or-before the open timestamp. This does not
        # alter order placement, risk, sizing, or lifecycle decisions.
        try:
            l1_match = None
            for _, fields in redis_client.xrevrange(
                "shadow:telemetry:execution_l1",
                count=8,
            ):
                raw_l1 = fields.get("json") if isinstance(fields, dict) else None
                if not raw_l1:
                    continue
                obj = json.loads(raw_l1)
                if not isinstance(obj, dict):
                    continue
                if str(obj.get("symbol") or "").upper().strip() != sym:
                    continue
                obs_ms = int(obj.get("observed_at_ms") or 0)
                if obs_ms <= 0 or obs_ms > opened_ms:
                    continue
                age_ms = opened_ms - obs_ms
                if age_ms <= 3000:
                    l1_match = (obj, age_ms)
                    break

            if l1_match is not None:
                l1, l1_age_ms = l1_match
                compare_payload = {
                    "schema_version": 1,
                    "shadow_only": True,
                    "trade_id": trade_id,
                    "intent_id": intent_norm,
                    "symbol": sym,
                    "side": side_norm,
                    "opened_ms": opened_ms,
                    "actual_order_type": "MARKET",
                    "actual_fill_price": float(entry_price),
                    "actual_qty": float(qty or 0.0),
                    "actual_notional": float(notional or 0.0),
                    "actual_leverage": float(leverage or 1.0),
                    "order_id": str(open_order_id or ""),
                    "client_order_id": str(open_client_order_id or ""),
                    "signal_score": float(signal_score),
                    "l1_observed_at_ms": int(l1.get("observed_at_ms") or 0),
                    "l1_age_ms": int(l1_age_ms),
                    "best_bid": _f(l1.get("best_bid")),
                    "best_ask": _f(l1.get("best_ask")),
                    "bid_qty_l1": _f(l1.get("bid_qty_l1")),
                    "ask_qty_l1": _f(l1.get("ask_qty_l1")),
                    "mid": _f(l1.get("mid")),
                    "spread_bps": _f(l1.get("spread_bps")),
                    "t1_count": _f(l1.get("t1_count")),
                    "t1_qty": _f(l1.get("t1_qty")),
                    "t1_min_price": _f(l1.get("t1_min_price")),
                    "t1_max_price": _f(l1.get("t1_max_price")),
                }
                redis_client.xadd(
                    "shadow:telemetry:execution_compare_anchor",
                    {"json": json.dumps(compare_payload, ensure_ascii=False, separators=(",", ":"))},
                    maxlen=10000,
                    approximate=True,
                )
        except Exception:
            pass

        return True
    except Exception:
        return False


def emit_position_outcome_shadow(
    redis_client: Any,
    *,
    symbol: str,
    side: str,
    entry_price: float,
    close_price: float,
    pnl_pct: float,
    reason: str,
    qty: float = 0.0,
    leverage: float = 1.0,
    realized_pnl_usdt: float = 0.0,
    close_order_id: str = "",
    close_client_order_id: str = "",
) -> bool:
    if redis_client is None:
        return False
    sym = str(symbol or "").upper().strip()
    side_norm = str(side or "").lower().strip()
    try:
        active_key = f"shadow:telemetry:position_context:active:{sym}:{side_norm}"
        raw = redis_client.get(active_key)
        ctx = json.loads(raw) if raw else {}
        if not isinstance(ctx, dict):
            ctx = {}
        payload = dict(ctx)

        entry_px = float(entry_price or payload.get("position_entry_price") or 0.0)
        close_px = float(close_price or 0.0)
        qty_now = float(qty or payload.get("position_qty") or 0.0)
        lev = float(leverage or payload.get("position_leverage") or 1.0)
        entry_notional = abs(entry_px * qty_now) if entry_px > 0 and qty_now > 0 else float(payload.get("position_notional") or 0.0)
        exit_notional = abs(close_px * qty_now) if close_px > 0 and qty_now > 0 else 0.0

        if side_norm == "long":
            gross_pnl_usdt = (close_px - entry_px) * qty_now if entry_px > 0 and close_px > 0 and qty_now > 0 else float(realized_pnl_usdt or 0.0)
        else:
            gross_pnl_usdt = (entry_px - close_px) * qty_now if entry_px > 0 and close_px > 0 and qty_now > 0 else float(realized_pnl_usdt or 0.0)

        fee_rate = float(os.getenv("OUTCOME_TAKER_FEE_RATE", os.getenv("REPLAY_TAKER_FEE_RATE", "0.0004")) or 0.0004)
        slippage_bps = float(os.getenv("OUTCOME_SLIPPAGE_BPS", os.getenv("REPLAY_SLIPPAGE_BPS", "0")) or 0.0)
        slippage_rate = slippage_bps / 10000.0

        estimated_fee_usdt = (entry_notional + exit_notional) * fee_rate
        estimated_slippage_usdt = (entry_notional + exit_notional) * slippage_rate
        net_pnl_usdt = gross_pnl_usdt - estimated_fee_usdt - estimated_slippage_usdt
        gross_return_pct = (gross_pnl_usdt / entry_notional) if entry_notional > 0 else float(pnl_pct or 0.0)
        net_return_pct = (net_pnl_usdt / entry_notional) if entry_notional > 0 else 0.0

        payload.update({
            "position_close_at_ms": int(time.time() * 1000),
            "close_price": close_px,
            "entry_price": entry_px,
            "qty": qty_now,
            "leverage": lev,
            "gross_pnl_usdt": float(gross_pnl_usdt),
            "gross_return_pct": float(gross_return_pct),
            "gross_roi_pct": float(gross_return_pct * lev),
            "estimated_fee_rate": float(fee_rate),
            "estimated_fee_usdt": float(estimated_fee_usdt),
            "estimated_slippage_bps": float(slippage_bps),
            "estimated_slippage_usdt": float(estimated_slippage_usdt),
            "funding_cost_usdt": None,
            "funding_cost_source": "not_available",
            "net_pnl_usdt_est": float(net_pnl_usdt),
            "net_return_pct_est": float(net_return_pct),
            "net_roi_pct_est": float(net_return_pct * lev),
            "pnl_pct": float(pnl_pct),
            "close_reason": str(reason or ""),
            "close_order_id": str(close_order_id or ""),
            "close_client_order_id": str(close_client_order_id or ""),
            "symbol": sym,
            "side": side_norm,
            "cost_model": "estimated_taker_plus_slippage",
            "shadow_only": True,
        })
        redis_client.xadd(
            "shadow:telemetry:position_outcome",
            {"json": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
            maxlen=10000,
            approximate=True,
        )
        redis_client.delete(active_key)
        return True
    except Exception:
        return False
