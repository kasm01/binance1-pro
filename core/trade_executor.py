# -*- coding: utf-8 -*-
from __future__ import annotations
import threading

import asyncio
import inspect
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Set

import redis

from core.binance_futures_v3 import (
    account as _futures_v3_account,
    balance as _futures_v3_balance,
    position_risk as _futures_v3_position_risk,
)

try:
    from monitoring.okx_oi_shadow_context import (
        emit_entry_context_shadow as _emit_okx_oi_entry_shadow,
        emit_position_outcome_shadow as _emit_okx_oi_outcome_shadow,
        mark_position_open_shadow as _mark_okx_oi_position_open_shadow,
        read_binance_structure_shadow as _read_binance_structure_shadow,
        read_okx_oi_shadow as _read_okx_oi_shadow,
        read_market_context_shadow as _read_market_context_shadow,
    )
except Exception:
    _emit_okx_oi_entry_shadow = None
    _emit_okx_oi_outcome_shadow = None
    _mark_okx_oi_position_open_shadow = None
    _read_binance_structure_shadow = None
    _read_okx_oi_shadow = None
    _read_market_context_shadow = None


class TradeExecutor:
    def __init__(
        self,
        client: Any = None,
        redis_client: Any = None,
        logger: Any = None,
        price_cache: Any = None,
        position_manager: Any = None,
        risk_manager: Any = None,
        telegram_bot: Any = None,
        dry_run: bool = False,
        max_leverage: float = 3.0,
        **kwargs: Any,
    ) -> None:
        self.client = client
        self.redis = redis_client
        self.logger = logger
        self.price_cache = price_cache
        self.position_manager = position_manager
        self.risk_manager = risk_manager
        self.telegram_bot = telegram_bot

        self.dry_run = str(dry_run or "0").strip().lower() in ("1", "true", "yes", "on")
        self.max_leverage = float(max_leverage or 3.0)

        self.default_order_leverage = int(
            float(os.getenv("DEFAULT_ORDER_LEVERAGE", str(int(self.max_leverage or 3))))
        )
        self.exchange_info_ttl_sec = float(
            os.getenv("EXCHANGE_INFO_TTL_SEC", "300") or 300.0
        )
        self._exchange_info_cache: Optional[Dict[str, Any]] = None
        self._exchange_info_cache_ts: float = 0.0

        self.order_poll_status = str(
            os.getenv("ORDER_POLL_STATUS", "1")
        ).strip().lower() in ("1", "true", "yes", "on")
        self.order_poll_wait_s = float(os.getenv("ORDER_POLL_WAIT_S", "2.0") or 2.0)

        self.order_verify_position = str(
            os.getenv("ORDER_VERIFY_POSITION", "0")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.hedge_mode_enabled = True

        self.whale_block_actions = {"block", "avoid", "hard_block"}
        self.whale_reduce_actions = {"reduce", "scale_down", "soft_reduce"}

        self.whale_hard_block_min_score = float(
            os.getenv("WHALE_HARD_BLOCK_MIN_SCORE", "0.85") or 0.85
        )
        self.whale_reduce_min_score = float(
            os.getenv("WHALE_REDUCE_MIN_SCORE", "0.60") or 0.60
        )
        self.whale_reduce_factor = float(
            os.getenv("WHALE_REDUCE_FACTOR", "0.50") or 0.50
        )

        self.max_open_positions = int(os.getenv("MAX_OPEN_POSITIONS", "3") or 3)
        self.block_same_symbol_reentry = str(
            os.getenv("BLOCK_SAME_SYMBOL_REENTRY", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.per_position_balance_pct = float(
            os.getenv("PER_POSITION_BALANCE_PCT", "0.50") or 0.50
        )

        self.last_snapshot: Dict[str, Any] = {}
        self.last_snapshot_by_symbol: Dict[str, Dict[str, Any]] = {}
        self.long_pending_by_symbol: Dict[str, Dict[str, Any]] = {}


        self.position_sync_enabled = str(
            os.getenv("POSITION_SYNC_ENABLED", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.position_sync_interval_sec = int(
            float(os.getenv("POSITION_SYNC_INTERVAL_SEC", "300") or 300)
        )
        # Timestamp of the last completed exchange/local reconciliation.
        # Used only to avoid duplicate empty-portfolio sync calls from lifecycle.
        self._last_position_sync_ts = 0.0

        self.position_sync_remove_orphans = str(
            os.getenv("POSITION_SYNC_REMOVE_ORPHANS", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.position_lifecycle_enabled = str(
            os.getenv("POSITION_LIFECYCLE_ENABLED", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.position_lifecycle_interval_sec = int(
            float(os.getenv("POSITION_LIFECYCLE_INTERVAL_SEC", "15") or 15)
        )
        # Last lifecycle-visible active-position count; observability only.
        self._last_lifecycle_active_count = 0
        # === ULTRA FAST SCALP EXIT ENGINE ===
        self.scalp_exit_enable = str(
            os.getenv("SCALP_EXIT_ENABLE", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.scalp_grace_sec = int(
            float(os.getenv("SCALP_GRACE_SEC", "20") or 20)
        )

        self.scalp_reverse_min_score = float(
            os.getenv("SCALP_REVERSE_MIN_SCORE", "0.54") or 0.52
        )

        self.scalp_stall_after_profit_sec = int(
            float(os.getenv("SCALP_STALL_AFTER_PROFIT_SEC", "180") or 120)
        )

        # === ROI / USDT BASED EXIT CONTROL ===
        self.usdt_loss_kill_enable = str(
            os.getenv("USDT_LOSS_KILL_ENABLE", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.max_loss_usdt_per_trade = float(
            os.getenv("MAX_LOSS_USDT_PER_TRADE", "4.0") or 4.0
        )

        self.roi_hard_stop_pct = float(
            os.environ["ROI_HARD_STOP_PCT"]
        )

        self.profit_lock_arm_roi_pct = float(
            os.getenv("PROFIT_LOCK_ARM_ROI_PCT", "0.0175") or 0.0175
        )  # %1.75 ROI kâr görünce arm

        self.profit_lock_retrace_roi_pct = float(
            os.getenv("PROFIT_LOCK_RETRACE_ROI_PCT", "0.0045") or 0.0045
        )  # %0.45 ROI geri dönüşte kilitle

        self.profit_floor_roi_pct = float(
            os.getenv("PROFIT_FLOOR_ROI_PCT", "0.0040") or 0.0040
        )  # kâr gördükten sonra min korunacak ROI

        self.scalp_profit_arm_roi_pct = float(
            os.getenv("SCALP_PROFIT_ARM_ROI_PCT", "0.0175") or 0.0175
        )

        self.scalp_fast_exit_profit_roi_pct = float(
            os.getenv("SCALP_FAST_EXIT_PROFIT_ROI_PCT", "0.0200") or 0.0200
        )

        self.scalp_fast_exit_pullback_roi_pct = float(
            os.getenv("SCALP_FAST_EXIT_PULLBACK_ROI_PCT", "0.0040") or 0.0040
        )

        self.scalp_retrace_roi_pct = float(
            os.getenv("SCALP_RETRACE_ROI_PCT", "0.0045") or 0.0045
        )

        self.scalp_micro_pullback_roi_pct = float(
            os.getenv("SCALP_MICRO_PULLBACK_ROI_PCT", "0.0035") or 0.0035
        )

        self.scalp_deep_pullback_roi_pct = float(
            os.getenv("SCALP_DEEP_PULLBACK_ROI_PCT", "0.0060") or 0.0060
        )

        # === STRONG PROFIT LOCK ===
        self.profit_lock_enable = str(
            os.getenv("PROFIT_LOCK_ENABLE", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.profit_lock_min_hold_sec = int(
            float(os.getenv("PROFIT_LOCK_MIN_HOLD_SEC", "10") or 10)
        )

        # erken kâr koruma
        self.profit_guard_arm_pct = float(
            os.getenv("PROFIT_GUARD_ARM_PCT", "0.008") or 0.008
        )
        self.profit_guard_retrace_pct = float(
            os.getenv("PROFIT_GUARD_RETRACE_PCT", "0.0035") or 0.0035
        )

        # sert kâr kilidi
        self.profit_lock_arm_pct = float(
            os.getenv("PROFIT_LOCK_ARM_PCT", "0.02") or 0.02
        )
        self.profit_lock_retrace_pct = float(
            os.getenv("PROFIT_LOCK_RETRACE_PCT", "0.0018") or 0.0018
        )

        # ters sinyal kâr koruma
        self.profit_reverse_arm_pct = float(
            os.getenv("PROFIT_REVERSE_ARM_PCT", "0.012") or 0.012
        )
        self.profit_reverse_min_score = float(
            os.getenv("PROFIT_REVERSE_MIN_SCORE", "0.50") or 0.50
        )

        # === PROFIT PROTECT - SINGLE ENV AUTHORITY ===
        self.profit_protect_enable = str(
            os.getenv("PROFIT_PROTECT_ENABLE", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.profit_protect_arm_pct = float(
            os.getenv("PROFIT_PROTECT_ARM_PCT", "0.020") or 0.020
        )

        self.profit_protect_pullback_pct = float(
            os.getenv("PROFIT_PROTECT_PULLBACK_PCT", "0.004") or 0.004
        )

        self.profit_protect_reverse_score = float(
            os.getenv("PROFIT_PROTECT_REVERSE_SCORE", "0.55") or 0.55
        )

        # minimum korunacak kâr tabanı
        self.profit_floor_pct = float(
            os.getenv("PROFIT_FLOOR_PCT", "0.004") or 0.004
        )
        # === ENTRY CONFIRMATION (2-BAR) ===
        # === DEAD TRADE EXIT ===
        self.dead_trade_exit_enable = str(
            os.getenv("DEAD_TRADE_EXIT_ENABLE", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.dead_trade_max_sec = int(
            float(os.getenv("DEAD_TRADE_MAX_SEC", "90") or 90)
        )

        self.dead_trade_min_best_pnl_pct = float(
            os.getenv("DEAD_TRADE_MIN_BEST_PNL_PCT", "0.002") or 0.002
        )
        self.default_sl_pct = float(os.getenv("SL_PCT", "0.01") or 0.01)
        self.default_tp_pct = float(os.getenv("TP_PCT", "0.02") or 0.02)
        self.default_trailing_pct = float(os.getenv("TRAILING_PCT", "0.03") or 0.03)

        self.trailing_activation_pct = float(
            os.getenv("TRAILING_ACTIVATION_PCT", "0.003") or 0.003
        )

        # === STALL EXIT - SINGLE AUTHORITY ===
        self.default_stall_ttl_sec = int(
            float(os.getenv("STALL_TTL_SEC", "1200") or 1200)
        )



        self.reverse_close_enabled = str(
            os.getenv("REVERSE_CLOSE_ENABLED", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.tp_runner_pullback_pct = float(
            os.getenv("TP_RUNNER_PULLBACK_PCT", "0.006") or 0.006
        )

        self.stall_peak_gate_pct = float(
            os.getenv("STALL_PEAK_GATE_PCT", "0.040") or 0.040
        )

        self.manual_close_detect_enable = str(
            os.getenv("MANUAL_CLOSE_DETECT_ENABLE", "1")
        ).strip().lower() in ("1", "true", "yes", "on")
        self.hard_stop_enable = str(
            os.getenv("HARD_STOP_ENABLE", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.hard_stop_loss_pct = float(
            os.getenv("HARD_STOP_LOSS_PCT", "0.040") or 0.040
        )
        self.manual_close_reconcile_on_lifecycle = str(
            os.getenv("MANUAL_CLOSE_RECONCILE_ON_LIFECYCLE", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        try:
            self.opposite_signal_min_score = float(
                os.getenv("OPPOSITE_SIGNAL_MIN_SCORE", "0.55") or 0.55
            )
        except Exception:
            self.opposite_signal_min_score = 0.55

        try:
            self.opposite_signal_max_age_sec = float(
                os.getenv("OPPOSITE_SIGNAL_MAX_AGE_SEC", "900") or 900.0
            )
        except Exception:
            self.opposite_signal_max_age_sec = 900.0

        try:
            self.opposite_signal_confirm_count = int(
                float(os.getenv("OPPOSITE_SIGNAL_CONFIRM_COUNT", "1") or 1)
            )
        except Exception:
            self.opposite_signal_confirm_count = 1

        self.tp_runner_enable = str(
            os.getenv("TP_RUNNER_ENABLE", "0")
        ).strip().lower() in ("1", "true", "yes", "on")

        self.tp_arm_pnl_pct = float(
            os.getenv("TP_ARM_PNL_PCT", "0.020") or 0.020
        )

    # ---------------------------------------------------------
    # basic helpers
    # ---------------------------------------------------------
    def _env_csv_set(self, key: str) -> Set[str]:
        raw = str(os.getenv(key, "") or "")
        return {
            item.strip().upper()
            for item in raw.split(",")
            if item and item.strip()
        }

    def _get_symbol_exit_profile(self, symbol: str) -> str:
        sym = str(symbol or "").upper().strip()
        aggressive = self._env_csv_set("COIN_EXIT_MODE_AGGRESSIVE")
        soft = self._env_csv_set("COIN_EXIT_MODE_SOFT")

        if sym in aggressive:
            return "aggressive"
        if sym in soft:
            return "soft"
        return "normal"

    def _apply_exit_profile(
        self,
        symbol: str,
        scalp_fast_exit_pullback_roi_pct: float,
        scalp_retrace_roi_pct: float,
        scalp_micro_pullback_roi_pct: float,
        scalp_deep_pullback_roi_pct: float,
        scalp_stall_after_profit_sec: float,
        profit_lock_retrace_roi_pct: float,
    ) -> Dict[str, float]:
        profile = self._get_symbol_exit_profile(symbol)

        if profile == "aggressive":
            scalp_fast_exit_pullback_roi_pct *= float(os.getenv("EXIT_PROFILE_AGGR_FAST_EXIT_PULLBACK_MULT", "0.80"))
            scalp_retrace_roi_pct *= float(os.getenv("EXIT_PROFILE_AGGR_RETRACE_MULT", "0.80"))
            scalp_micro_pullback_roi_pct *= float(os.getenv("EXIT_PROFILE_AGGR_MICRO_PULLBACK_MULT", "0.80"))
            scalp_deep_pullback_roi_pct *= float(os.getenv("EXIT_PROFILE_AGGR_DEEP_PULLBACK_MULT", "0.85"))
            scalp_stall_after_profit_sec *= float(os.getenv("EXIT_PROFILE_AGGR_STALL_AFTER_PROFIT_MULT", "0.75"))
            profit_lock_retrace_roi_pct *= float(os.getenv("EXIT_PROFILE_AGGR_PROFIT_LOCK_RETRACE_MULT", "0.85"))

        elif profile == "soft":
            scalp_fast_exit_pullback_roi_pct *= float(os.getenv("EXIT_PROFILE_SOFT_FAST_EXIT_PULLBACK_MULT", "1.20"))
            scalp_retrace_roi_pct *= float(os.getenv("EXIT_PROFILE_SOFT_RETRACE_MULT", "1.20"))
            scalp_micro_pullback_roi_pct *= float(os.getenv("EXIT_PROFILE_SOFT_MICRO_PULLBACK_MULT", "1.20"))
            scalp_deep_pullback_roi_pct *= float(os.getenv("EXIT_PROFILE_SOFT_DEEP_PULLBACK_MULT", "1.15"))
            scalp_stall_after_profit_sec *= float(os.getenv("EXIT_PROFILE_SOFT_STALL_AFTER_PROFIT_MULT", "1.25"))
            profit_lock_retrace_roi_pct *= float(os.getenv("EXIT_PROFILE_SOFT_PROFIT_LOCK_RETRACE_MULT", "1.15"))

        return {
            "profile": profile,
            "scalp_fast_exit_pullback_roi_pct": scalp_fast_exit_pullback_roi_pct,
            "scalp_retrace_roi_pct": scalp_retrace_roi_pct,
            "scalp_micro_pullback_roi_pct": scalp_micro_pullback_roi_pct,
            "scalp_deep_pullback_roi_pct": scalp_deep_pullback_roi_pct,
            "scalp_stall_after_profit_sec": scalp_stall_after_profit_sec,
            "profit_lock_retrace_roi_pct": profit_lock_retrace_roi_pct,
        }

    def _is_reduceonly_retryable_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        needles = [
            "reduceonly",
            "parameter 'reduceonly' sent when not required",
            "parameter reduceonly sent when not required",
            "-1106",
        ]
        return any(n in text for n in needles)

    def _build_close_order_kwargs(
        self,
        symbol: str,
        side: str,
        qty: float,
        position_side: Optional[str] = None,
        reduce_only: bool = True,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": qty,
        }

        # 🔥 HEDGE / ONE-WAY SAFE MODE
        if position_side:
            # hedge mode varsay → positionSide kullan
            kwargs["positionSide"] = position_side
            # reduceOnly gönderme (binance reject ediyor)
        else:
            # one-way mode → reduceOnly kullan
            if reduce_only:
                kwargs["reduceOnly"] = True
        return kwargs

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _env_int(key: str, default: int) -> int:
        try:
            return int(str(os.getenv(key, str(default))).strip())
        except Exception:
            return int(default)

    @staticmethod
    def _env_float(key: str, default: float) -> float:
        try:
            return float(str(os.getenv(key, str(default))).strip())
        except Exception:
            return float(default)

    @staticmethod
    def _truthy_env(key: str, default: str = "0") -> bool:
        val = str(os.getenv(key, default)).strip().lower()
        return val in ("1", "true", "yes", "on", "y")

    @staticmethod
    def _clip_float(val: Any, default: Optional[float] = None) -> Optional[float]:
        try:
            if val is None:
                return default
            return float(val)
        except Exception:
            return default

    @staticmethod
    def _safe_json(x: Any, limit: int = 1200) -> str:
        try:
            s = json.dumps(x, ensure_ascii=False, default=str)
        except Exception:
            s = str(x)
        if len(s) > limit:
            return s[:limit] + "...(trunc)"
        return s

    @staticmethod
    def _signal_u_from_any(signal: str) -> str:
        s = str(signal or "").strip().upper()
        if s in ("BUY", "LONG"):
            return "BUY"
        if s in ("SELL", "SHORT"):
            return "SELL"
        return "HOLD"

    @staticmethod
    def _normalize_side(signal: str) -> str:
        s = str(signal or "").strip().upper()
        if s == "BUY":
            return "long"
        if s == "SELL":
            return "short"
        return "hold"

    @staticmethod
    def _side_to_position_side(side: str) -> str:
        s = str(side or "").strip().lower()
        if s == "long":
            return "LONG"
        if s == "short":
            return "SHORT"
        return "BOTH"

    @staticmethod
    def _make_client_order_id(symbol: str, tag: str) -> str:
        sym = str(symbol).upper()
        rid = uuid.uuid4().hex[:12]
        return f"b1_{tag}_{sym}_{rid}"[:36]

    @staticmethod
    def _summarize_order(resp: Any) -> Dict[str, Any]:
        if not isinstance(resp, dict):
            return {"resp": str(resp)}

        keys = [
            "symbol",
            "side",
            "type",
            "orderId",
            "clientOrderId",
            "status",
            "price",
            "avgPrice",
            "origQty",
            "executedQty",
            "cumQty",
            "cumQuote",
            "reduceOnly",
            "positionSide",
            "timeInForce",
            "updateTime",
            "transactTime",
        ]
        out: Dict[str, Any] = {}
        for k in keys:
            if k in resp:
                out[k] = resp.get(k)

        for k in ("code", "msg"):
            if k in resp:
                out[k] = resp.get(k)

        return out

    def _get_all_local_positions(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}

        # 1) Önce PositionManager/list_symbols üzerinden sembolleri bul,
        #    ama pozisyonu çalışan wrapper olan self._get_position ile oku.
        try:
            pm = getattr(self, "position_manager", None)
            list_symbols_fn = getattr(pm, "list_symbols", None) if pm is not None else None

            if callable(list_symbols_fn):
                raw_symbols = list_symbols_fn() or []

                norm_symbols = []
                for s in raw_symbols:
                    try:
                        s_text = str(s).strip()
                        if ":" in s_text:
                            s_text = s_text.split(":")[-1]
                        s_text = s_text.upper().strip()
                        if s_text:
                            norm_symbols.append(s_text)
                    except Exception:
                        pass

                try:
                    if self.logger:
                        log_fn = self.logger.info if norm_symbols else self.logger.debug
                        log_fn(
                            "[EXEC][STATE] position_manager symbols | count=%s symbols=%s",
                            len(norm_symbols),
                            norm_symbols,
                        )
                except Exception:
                    pass

                for sym_u in norm_symbols:
                    try:
                        pos = self._get_position(sym_u)
                        if isinstance(pos, dict) and pos:
                            cp = dict(pos)
                            cp["symbol"] = sym_u
                            out[sym_u] = cp
                    except Exception:
                        if self.logger:
                            self.logger.exception(
                                "[EXEC][STATE] _get_position failed | symbol=%s",
                                sym_u,
                            )
        except Exception:
            if self.logger:
                self.logger.exception("[EXEC][STATE] position_manager list failed")

        # 2) Redis fallback
        if not out:
            try:
                r = getattr(self, "redis", None)
                if r is None:
                    r = getattr(self, "redis_client", None)

                if r is not None:
                    _pos_scan_pattern = "bot:positions:*"
                    keys = r.keys(_pos_scan_pattern) or []

                    key_list = []
                    for k in keys:
                        if isinstance(k, (bytes, bytearray)):
                            key_list.append(k.decode("utf-8", errors="ignore"))
                        else:
                            key_list.append(str(k))

                    try:
                        if self.logger:
                            log_fn = self.logger.info if key_list else self.logger.debug
                            log_fn(
                                "[EXEC][STATE] redis keys scan | count=%s keys=%s",
                                len(key_list),
                                key_list,
                            )
                    except Exception:
                        pass

                    for key_s in key_list:
                        try:
                            raw = r.get(key_s)
                            if not raw:
                                continue

                            if isinstance(raw, (bytes, bytearray)):
                                raw = raw.decode("utf-8", errors="ignore")

                            pos = json.loads(raw)
                            if not isinstance(pos, dict):
                                continue

                            sym_u = str(
                                pos.get("symbol") or key_s.split(":")[-1]
                            ).upper().strip()
                            if not sym_u:
                                continue

                            cp = dict(pos)
                            cp["symbol"] = sym_u
                            out[sym_u] = cp

                        except Exception:
                            if self.logger:
                                self.logger.exception(
                                    "[EXEC][STATE] redis position parse failed | key=%s",
                                    key_s,
                                )
            except Exception:
                if self.logger:
                    self.logger.exception("[EXEC][STATE] redis fallback list failed")

        # 3) In-memory fallback
        if not out:
            try:
                mem = getattr(self, "_positions", None)
                if isinstance(mem, dict):
                    for sym, pos in mem.items():
                        try:
                            sym_u = str(sym).upper().strip()
                            if not sym_u:
                                continue
                            if isinstance(pos, dict) and pos:
                                cp = dict(pos)
                                cp["symbol"] = sym_u
                                out[sym_u] = cp
                        except Exception:
                            pass
            except Exception:
                pass

        # 4) normalize + sadece geçerli açık pozisyonlar
        norm: Dict[str, Dict[str, Any]] = {}

        for sym, pos in out.items():
            try:
                if not isinstance(pos, dict):
                    continue

                sym_u = str(sym or pos.get("symbol") or "").upper().strip()
                if not sym_u:
                    continue

                side = str(pos.get("side") or "").strip().lower()

                try:
                    qty = float(pos.get("qty") or 0.0)
                except Exception:
                    qty = 0.0

                try:
                    entry_price = float(pos.get("entry_price") or 0.0)
                except Exception:
                    entry_price = 0.0

                if side not in ("long", "short"):
                    continue
                if qty <= 0:
                    continue
                if entry_price <= 0:
                    continue

                # -------------------------------------------------
                # BOT SIDE FILTER
                # -------------------------------------------------
                try:
                    bot_side_mode = str(
                        os.getenv("BOT_SIDE_MODE", "both") or "both"
                    ).strip().lower()

                    if bot_side_mode == "long" and side != "long":
                        continue

                    if bot_side_mode == "short" and side != "short":
                        continue

                except Exception:
                    pass

                cp = dict(pos)
                cp["symbol"] = sym_u
                cp["side"] = side
                cp["qty"] = float(qty)
                cp["entry_price"] = float(entry_price)
                cp["interval"] = str(cp.get("interval") or "1m").strip() or "1m"
                cp["notional"] = float(cp.get("notional") or (qty * entry_price))
                cp["sl_price"] = float(cp.get("sl_price") or 0.0)
                cp["tp_price"] = float(cp.get("tp_price") or 0.0)
                cp["trailing_pct"] = float(
                    cp.get("trailing_pct")
                    or getattr(self, "default_trailing_pct", 0.03)
                    or 0.03
                )
                cp["stall_ttl_sec"] = int(
                    cp.get("stall_ttl_sec")
                    or self.default_stall_ttl_sec
                )
                cp["best_pnl_pct"] = float(cp.get("best_pnl_pct") or 0.0)
                cp["last_best_ts"] = float(cp.get("last_best_ts") or time.time())
                cp["atr_value"] = float(cp.get("atr_value") or 0.0)
                cp["highest_price"] = float(cp.get("highest_price") or entry_price)
                cp["lowest_price"] = float(cp.get("lowest_price") or entry_price)

                meta = cp.get("meta")
                if not isinstance(meta, dict):
                    meta = {}
                if not isinstance(meta.get("probs"), dict):
                    meta["probs"] = {}
                if not isinstance(meta.get("extra"), dict):
                    meta["extra"] = {}
                cp["meta"] = meta

                norm[sym_u] = cp

            except Exception:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][STATE] normalize failed | symbol=%s",
                        sym,
                    )

        try:
            if self.logger:
                log_fn = self.logger.info if norm else self.logger.debug
                log_fn(
                    "[EXEC][STATE] local positions resolved | count=%s symbols=%s",
                    len(norm),
                    list(norm.keys()),
                )
        except Exception:
            pass

        return norm

    def _get_exchange_open_positions(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        client = getattr(self, "client", None)
        if client is None:
            return out

        def _append_from_rows(rows: Any) -> None:
            if not isinstance(rows, list):
                return

            for row in rows:
                if not isinstance(row, dict):
                    continue

                try:
                    amt = float(row.get("positionAmt") or 0.0)
                except Exception:
                    amt = 0.0

                if abs(amt) <= 1e-12:
                    continue

                sym = str(row.get("symbol") or "").upper().strip()
                if not sym:
                    continue

                side = "long" if amt > 0 else "short"

                entry_price = self._clip_float(row.get("entryPrice"), 0.0) or 0.0
                mark_price = self._clip_float(row.get("markPrice"), 0.0) or 0.0

                px = float(mark_price if mark_price > 0 else entry_price)
                notional = float(abs(amt) * px) if px > 0 else 0.0

                out.append(
                    {
                        "symbol": sym,
                        "side": side,
                        "qty": abs(float(amt)),
                        "entry_price": float(entry_price),
                        "mark_price": float(mark_price),
                        "notional": float(notional),
                        "raw": row,
                    }
                )

        # 1) Önce futures_account() -> positions
        try:
            fn_acc = getattr(client, "futures_account", None)
            if callable(fn_acc):
                acc = fn_acc()
                if isinstance(acc, dict):
                    _append_from_rows(acc.get("positions", []) or [])
                    if out:
                        return out
        except Exception as e:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][EXCHANGE-POS] futures_account positions read failed | err=%s",
                        str(e)[:300],
                    )
            except Exception:
                pass

        # 2) Legacy fallback: futures_position_information()
        try:
            fn = getattr(client, "futures_position_information", None)
            if callable(fn):
                rows = fn()
                _append_from_rows(rows)
        except Exception as e:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][EXCHANGE-POS] futures_position_information read failed | err=%s",
                        str(e)[:300],
                    )
            except Exception:
                pass

        # 3) Binance Futures current API fallback: /fapi/v3/positionRisk.
        if not out:
            try:
                _append_from_rows(_futures_v3_position_risk())
            except Exception as e:
                try:
                    if self.logger:
                        self.logger.warning(
                            "[EXEC][EXCHANGE-POS] v3 positionRisk read failed | err=%s",
                            str(e)[:300],
                        )
                except Exception:
                    pass

        return out

    def _get_exchange_open_positions_map(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}

        try:
            rows = self._get_exchange_open_positions()
            for row in rows:
                if not isinstance(row, dict):
                    continue

                sym = str(row.get("symbol") or "").upper().strip()
                side = str(row.get("side") or "").lower().strip()
                qty = float(row.get("qty") or 0.0)

                if not sym or side not in ("long", "short") or qty <= 0:
                    continue

                out[sym] = row
        except Exception:
            try:
                if self.logger:
                    self.logger.exception("[EXEC][EXCHANGE-POS] map build failed")
            except Exception:
                pass

        return out

    def _count_open_positions(self) -> int:
        seen: Dict[str, Dict[str, Any]] = {}

        # 1) Exchange
        try:
            ex_rows = self._get_exchange_open_positions()
            for row in ex_rows:
                if not isinstance(row, dict):
                    continue
                sym = str(row.get("symbol") or "").upper().strip()
                side = str(row.get("side") or "").lower().strip()
                qty = float(row.get("qty") or 0.0)
                if sym and side in ("long", "short") and qty > 0:
                    seen[sym] = row
        except Exception:
            pass

        # 2) Redis fallback / tamamlayıcı kaynak
        try:
            r = getattr(self, "redis", None) or getattr(self, "redis_client", None)
            if r is not None:
                _pos_scan_pattern = "bot:positions:*"
                keys = r.keys(_pos_scan_pattern) or []
                for key in keys:
                    try:
                        raw = r.get(key)
                        if not raw:
                            continue
                        if isinstance(raw, (bytes, bytearray)):
                            raw = raw.decode("utf-8", errors="ignore")

                        obj = json.loads(raw)
                        if not isinstance(obj, dict):
                            continue

                        sym = str(obj.get("symbol") or str(key).split(":")[-1]).upper().strip()
                        side = str(obj.get("side") or "").lower().strip()
                        qty = float(obj.get("qty") or 0.0)

                        if sym and side in ("long", "short") and qty > 0:
                            seen.setdefault(
                                sym,
                                {
                                    "symbol": sym,
                                    "side": side,
                                    "qty": qty,
                                },
                            )
                    except Exception:
                        continue
        except Exception:
            pass

        return int(len(seen))

    def _count_open_positions_for_side(self, side: Optional[str] = None) -> int:
        try:
            target = str(side or "").strip().lower()
            if target not in ("long", "short"):
                return int(self._count_open_positions())

            positions = []
            try:
                positions = list(getattr(self, "positions", {}).values())
            except Exception:
                positions = []

            count = 0
            for pos in positions:
                try:
                    qty = float(
                        pos.get("position_amt")
                        or pos.get("positionAmt")
                        or pos.get("qty")
                        or pos.get("amount")
                        or 0.0
                    )
                except Exception:
                    qty = 0.0

                if abs(qty) <= 0:
                    continue

                pos_side = str(
                    pos.get("side")
                    or pos.get("position_side")
                    or pos.get("positionSide")
                    or ""
                ).strip().lower()

                if pos_side not in ("long", "short"):
                    if qty > 0:
                        pos_side = "long"
                    elif qty < 0:
                        pos_side = "short"

                if pos_side == target:
                    count += 1

            return int(count)
        except Exception:
            try:
                return int(self._count_open_positions())
            except Exception:
                return 0

    def _has_open_position_on_symbol(self, symbol: str) -> bool:
        sym_u = str(symbol).upper().strip()
        if not sym_u:
            return False

        try:
            for row in self._get_exchange_open_positions():
                if str(row.get("symbol") or "").upper().strip() == sym_u:
                    return True
        except Exception:
            pass

        try:
            pos = self._get_position(sym_u)
            if isinstance(pos, dict):
                side = str(pos.get("side") or "").lower().strip()
                qty = float(pos.get("qty") or 0.0)
                if side in ("long", "short") and qty > 0:
                    return True
        except Exception:
            pass

        return False
    def _get_available_balance_usdt_sync(self) -> float:
        client = getattr(self, "client", None)
        if client is None:
            return 0.0

        try:
            fn = getattr(client, "futures_account", None)
            if callable(fn):
                acc = fn()
                if isinstance(acc, dict):
                    available = float(acc.get("availableBalance", 0.0) or 0.0)
                    if available > 0:
                        return available
        except Exception:
            pass

        try:
            acc = _futures_v3_account()
            available = float(acc.get("availableBalance", 0.0) or 0.0)
            if available > 0:
                return available
        except Exception:
            pass

        return 0.0

    async def _get_available_balance_usdt(self) -> float:
        try:
            return float(self._get_available_balance_usdt_sync())
        except Exception:
            return 0.0

    def _compute_balance_based_notional(
        self,
        symbol: str,
        side: str,
        price: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> float:
        extra0 = extra if isinstance(extra, dict) else {}

        available_balance = self._clip_float(
            extra0.get("available_balance_usdt"),
            None,
        )

        if available_balance is None or available_balance <= 0:
            available_balance = self._clip_float(
                self._get_available_balance_usdt_sync(),
                None,
            )

        if available_balance is None or available_balance <= 0:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][NOTIONAL][REJECT] "
                        "symbol=%s side=%s reason=no_available_balance",
                        str(symbol).upper(),
                        str(side).lower(),
                    )
            except Exception:
                pass
            return 0.0

        pct = self._clip_float(
            self.per_position_balance_pct,
            0.50,
        ) or 0.50

        pct = max(
            0.01,
            min(float(pct), 1.0),
        )

        notional = (
            float(available_balance)
            * float(pct)
        )

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][NOTIONAL] "
                    "symbol=%s side=%s price=%.6f "
                    "available_balance=%.2f pct=%.4f "
                    "notional=%.2f",
                    str(symbol).upper(),
                    str(side).lower(),
                    float(price),
                    float(available_balance),
                    float(pct),
                    float(notional),
                )
        except Exception:
            pass

        return float(notional)

    # ---------------------------------------------------------
    # coroutine / retry helpers
    # ---------------------------------------------------------
    def _fire_and_forget(self, maybe: Any, *, label: str = "task") -> None:
        try:
            if inspect.isawaitable(maybe):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(maybe)
                except RuntimeError:
                    try:
                        if self.logger:
                            self.logger.warning("[EXEC] %s coroutine returned but no running loop; dropped", label)
                    except Exception:
                        pass
        except Exception:
            pass

    async def _await_if_coro(self, maybe: Any, *, label: str = "awaitable") -> Any:
        try:
            if inspect.isawaitable(maybe):
                return await maybe
        except Exception:
            try:
                if self.logger:
                    self.logger.exception(f"[EXEC] await failed | label={label}")
            except Exception:
                pass
        return maybe

    def _call_with_retry(
        self,
        fn: Any,
        payload: Dict[str, Any],
        attempts: int = 3,
        base_sleep: float = 0.6,
    ) -> Any:
        last_err: Optional[Exception] = None
        attempts = max(1, int(attempts))

        for i in range(attempts):
            try:
                return fn(**payload)
            except Exception as e:
                last_err = e
                if i >= attempts - 1:
                    break
                sleep_s = float(base_sleep) * (2 ** i)
                time.sleep(sleep_s)

        if last_err is not None:
            raise last_err
        raise RuntimeError("call_with_retry failed without exception")

    # ---------------------------------------------------------
    # whale helpers
    # ---------------------------------------------------------
    def _extract_whale_context(self, extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}

        if isinstance(extra, dict):
            out.update(extra)

        def _merge_from_obj(obj: Any) -> None:
            if not isinstance(obj, dict):
                return

            for k in (
                "whale_score",
                "whale_dir",
                "whale_action",
                "whale_bias",
                "signal_score",
                "score",
                "score_total",
                "_score_total_final",
                "_score_selected",
                "trail_pct",
                "stall_ttl_sec",
                "price",
                "intent_id",
                "risk_tags",
                "reasons",
                "reason_codes",
                "w_min",
            ):
                v = obj.get(k)
                if v is not None and (k not in out or out.get(k) in (None, "", 0, 0.0, [], {})):
                    out[k] = v

            raw2 = obj.get("raw")
            if isinstance(raw2, dict):
                for k in (
                    "whale_score",
                    "whale_dir",
                    "whale_action",
                    "whale_bias",
                    "price",
                    "trail_pct",
                    "stall_ttl_sec",
                ):
                    v = raw2.get(k)
                    if v is not None and (k not in out or out.get(k) in (None, "", 0, 0.0)):
                        out[k] = v

        _merge_from_obj(extra)

        raw = out.get("raw")

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = None

        _merge_from_obj(raw)

        if isinstance(raw, dict):
            raw_nested = raw.get("raw")
            if isinstance(raw_nested, str):
                try:
                    raw_nested = json.loads(raw_nested)
                except Exception:
                    raw_nested = None
            _merge_from_obj(raw_nested)

            if isinstance(raw_nested, dict):
                raw_nested2 = raw_nested.get("raw")
                if isinstance(raw_nested2, str):
                    try:
                        raw_nested2 = json.loads(raw_nested2)
                    except Exception:
                        raw_nested2 = None
                _merge_from_obj(raw_nested2)

        try:
            ws = float(out.get("whale_score") or 0.0)
        except Exception:
            ws = 0.0
        out["whale_score"] = ws

        wd = str(out.get("whale_dir") or "none").strip().lower()
        if wd in ("buy", "bull", "up"):
            wd = "long"
        elif wd in ("sell", "bear", "down"):
            wd = "short"
        elif wd not in ("long", "short"):
            wd = "none"
        out["whale_dir"] = wd

        wb = str(out.get("whale_bias") or "").strip().lower()
        if not wb:
            if wd in ("long", "short") and ws > 0:
                wb = wd
            else:
                wb = "hold"
        out["whale_bias"] = wb

        return out

    @staticmethod
    def _whale_action(extra: Dict[str, Any]) -> str:
        try:
            return str(extra.get("whale_action", "") or "").strip().lower()
        except Exception:
            return ""

    @staticmethod
    def _whale_bias(side: str, extra: Dict[str, Any]) -> str:
        try:
            wdir = str(extra.get("whale_dir", "none") or "none").strip().lower()
            if side in ("long", "short") and wdir in ("long", "short"):
                if side == wdir:
                    return "align"
                return "oppose"
        except Exception:
            pass
        return "hold"



    def _get_cached_mid_price(self, symbol: str) -> Optional[float]:
        import os
        import json

        sym = str(symbol).upper()

        # -----------------------------
        # price cache object
        # -----------------------------
        try:
            pc = getattr(self, "price_cache", None)

            if pc is not None:
                for method_name in (
                    "get_mid",
                    "get_mid_price",
                    "get_price",
                    "get_last_price",
                ):
                    fn = getattr(pc, method_name, None)

                    if callable(fn):
                        try:
                            max_age = float(
                                os.getenv(
                                    "REDIS_PRICECACHE_MAX_AGE_SEC",
                                    "90",
                                ) or 90
                            )

                            v = fn(sym, max_age_sec=max_age)

                        except TypeError:
                            v = fn(sym)

                        fv = self._clip_float(v, None)

                        if fv is not None and fv > 0:
                            return fv

        except Exception:
            pass

        # -----------------------------
        # raw redis fallback
        # -----------------------------
        try:
            if self.redis is not None:

                keys = [
                    f"{os.getenv('REDIS_PREFIX', 'binance1_long')}:pricecache:{sym}",
                    f"pricecache:{sym}",
                    f"price:{sym}",
                ]

                for k in keys:

                    raw = self.redis.get(k)

                    if not raw:
                        continue

                    fv = self._clip_float(raw, None)

                    if fv is not None and fv > 0:
                        return fv

                    try:
                        txt = (
                            raw.decode("utf-8")
                            if isinstance(raw, (bytes, bytearray))
                            else str(raw)
                        )

                        obj = json.loads(txt)

                        if isinstance(obj, dict):

                            for kk in (
                                "mid",
                                "price",
                                "last",
                                "last_price",
                                "mark_price",
                                "bid",
                                "ask",
                            ):

                                vv = obj.get(kk)

                                fv = self._clip_float(vv, None)

                                if fv is not None and fv > 0:
                                    return fv

                            b = self._clip_float(
                                obj.get("bid"),
                                None,
                            )

                            a = self._clip_float(
                                obj.get("ask"),
                                None,
                            )

                            if (
                                b is not None
                                and a is not None
                                and b > 0
                                and a > 0
                            ):
                                return (
                                    float(b) + float(a)
                                ) / 2.0

                    except Exception:
                        pass

        except Exception:
            pass

        return None

    def _resolve_price(
        self,
        symbol: str,
        price: Any = None,
        mark_price: Any = None,
        last_price: Any = None,
    ) -> Optional[float]:
        for v in (mark_price, price, last_price):
            fv = self._clip_float(v, None)
            if fv is not None and fv > 0:
                return fv

        cached = self._get_cached_mid_price(symbol)
        if cached is not None and cached > 0:
            return float(cached)

        return None

    def _backfill_ema_metrics(
        self,
        symbol: str,
        interval: str,
        extra: Optional[Dict[str, Any]] = None,
        limit: int = 120,
    ) -> Dict[str, float]:
        extra0 = extra if isinstance(extra, dict) else {}

        def _safe_float(v: Any, default: float = 0.0) -> float:
            try:
                return float(v)
            except Exception:
                return float(default)

        ema7 = _safe_float(extra0.get("ema7") or extra0.get("ema_fast") or 0.0)
        ema25 = _safe_float(extra0.get("ema25") or extra0.get("ema_slow") or 0.0)
        ema99 = _safe_float(extra0.get("ema99") or 0.0)

        rows_cache = []
        closes: List[float] = []
        source = "none"

        # 1) raw / cached closes
        try:
            raw = extra0.get("raw") or {}
            raw = raw if isinstance(raw, dict) else {}
            maybe_closes = (
                raw.get("closes")
                or extra0.get("closes")
                or raw.get("close_series")
                or extra0.get("close_series")
                or []
            )
            if isinstance(maybe_closes, (list, tuple)):
                closes = [float(x) for x in maybe_closes if x is not None]
                if len(closes) >= 30:
                    source = "extra_closes"
        except Exception:
            closes = []

        # 2) client.futures_klines
        if len(closes) < 30:
            try:
                client = getattr(self, "client", None)
                fn = getattr(client, "futures_klines", None) if client is not None else None
                if callable(fn):
                    rows = fn(
                        symbol=str(symbol).upper(),
                        interval=str(interval or "3m"),
                        limit=int(limit),
                    )

                    tmp: List[float] = []
                    if isinstance(rows, list):
                        rows_cache = rows
                        for row in rows:
                            try:
                                if isinstance(row, (list, tuple)) and len(row) >= 5:
                                    tmp.append(float(row[4]))
                                elif isinstance(row, dict):
                                    tmp.append(float(row.get("close")))
                            except Exception:
                                pass

                    if len(tmp) >= 30:
                        closes = tmp
                        source = "futures_klines"

            except Exception as e:
                try:
                    if self.logger:
                        self.logger.warning(
                            "[EXEC][STATE][EMA] futures_klines failed | symbol=%s interval=%s err=%s",
                            str(symbol).upper(),
                            str(interval or ""),
                            str(e),
                        )
                except Exception:
                    pass

        def _extract_last_ohlc() -> Dict[str, float]:
            try:
                if isinstance(rows_cache, list) and len(rows_cache) >= 2:
                    row = rows_cache[-1]
                    prev_row = rows_cache[-2]

                    if isinstance(row, (list, tuple)) and len(row) >= 5:
                        return {
                            "open": _safe_float(row[1]),
                            "high": _safe_float(row[2]),
                            "low": _safe_float(row[3]),
                            "close": _safe_float(row[4]),
                            "prev_close": _safe_float(prev_row[4]) if isinstance(prev_row, (list, tuple)) and len(prev_row) >= 5 else _safe_float(row[1]),
                        }

                    if isinstance(row, dict):
                        return {
                            "open": _safe_float(row.get("open")),
                            "high": _safe_float(row.get("high")),
                            "low": _safe_float(row.get("low")),
                            "close": _safe_float(row.get("close")),
                            "prev_close": _safe_float(prev_row.get("close")) if isinstance(prev_row, dict) else _safe_float(row.get("open")),
                        }
            except Exception:
                pass

            try:
                last_close = float(closes[-1]) if len(closes) >= 1 else 0.0
                prev_close = float(closes[-2]) if len(closes) >= 2 else last_close
                recent = [float(x) for x in closes[-5:]] if closes else []
                return {
                    "open": float(prev_close),
                    "high": float(max(recent)) if recent else float(last_close),
                    "low": float(min(recent)) if recent else float(last_close),
                    "close": float(last_close),
                    "prev_close": float(prev_close),
                }
            except Exception:
                return {
                    "open": 0.0,
                    "high": 0.0,
                    "low": 0.0,
                    "close": 0.0,
                    "prev_close": 0.0,
                }

        ohlc = _extract_last_ohlc()

        # EMA zaten extra'dan geldiyse yine OHLC ile beraber dön
        if ema7 > 0 and ema25 > 0 and ema99 > 0:
            return {
                "ema7": float(ema7),
                "ema25": float(ema25),
                "ema99": float(ema99),
                "ema_fast": float(ema7),
                "ema_slow": float(ema25),
                **ohlc,
            }

        # 3) last fallback: tek fiyatla doldurma yerine başarısızlığı görünür bırak
        if len(closes) < 30:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][STATE][EMA] insufficient closes | symbol=%s interval=%s closes_n=%s source=%s",
                        str(symbol).upper(),
                        str(interval or ""),
                        int(len(closes)),
                        source,
                    )
            except Exception:
                pass

            return {
                "ema7": 0.0,
                "ema25": 0.0,
                "ema99": 0.0,
                "ema_fast": 0.0,
                "ema_slow": 0.0,
                **ohlc,
            }

        if len(closes) < 99:
            last_px = _safe_float(closes[-1] if closes else 0.0)
            closes = list(closes) + [last_px] * (99 - len(closes))

        def _ema(values: List[float], span: int) -> float:
            if not values:
                return 0.0
            alpha = 2.0 / (float(span) + 1.0)
            ema_val = float(values[0])
            for v in values[1:]:
                ema_val = alpha * float(v) + (1.0 - alpha) * ema_val
            return float(ema_val)

        ema7 = _ema(closes, 7)
        ema25 = _ema(closes, 25)
        ema99 = _ema(closes, 99)

        result = {
            "ema7": float(ema7),
            "ema25": float(ema25),
            "ema99": float(ema99),
            "ema_fast": float(ema7),
            "ema_slow": float(ema25),
            **ohlc,
        }

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][STATE][EMA] symbol=%s interval=%s ema7=%.6f ema25=%.6f ema99=%.6f closes_n=%s source=%s open=%.6f high=%.6f low=%.6f close=%.6f",
                    str(symbol).upper(),
                    str(interval or ""),
                    float(result["ema7"]),
                    float(result["ema25"]),
                    float(result["ema99"]),
                    int(len(closes)),
                    source,
                    float(result.get("open") or 0.0),
                    float(result.get("high") or 0.0),
                    float(result.get("low") or 0.0),
                    float(result.get("close") or 0.0),
                )
        except Exception:
            pass

        return result

    # ---------------------------------------------------------
    # exchange info cache
    # ---------------------------------------------------------
    def _get_exchange_info_cached(self, force_refresh: bool = False) -> Dict[str, Any]:
        now = time.time()

        if (
            not force_refresh
            and isinstance(self._exchange_info_cache, dict)
            and (now - float(self._exchange_info_cache_ts)) < float(self.exchange_info_cache_ttl_sec)
        ):
            return self._exchange_info_cache

        client = getattr(self, "client", None)
        if client is None:
            return {}

        try:
            fn = getattr(client, "futures_exchange_info", None)
            if not callable(fn):
                return {}

            data = fn()
            if isinstance(data, dict):
                self._exchange_info_cache = data
                self._exchange_info_cache_ts = now
                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][EXCHANGE_INFO] refreshed cache ttl=%.1fs symbols=%s",
                            float(self.exchange_info_cache_ttl_sec),
                            len(data.get("symbols", []) or []),
                        )
                except Exception:
                    pass
                return data
        except Exception as e:
            try:
                if self.logger:
                    self.logger.warning("[EXEC][EXCHANGE_INFO] refresh failed err=%s", str(e))
            except Exception:
                pass

        return self._exchange_info_cache or {}

    def _get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        sym = str(symbol).upper().strip()

        def _extract(symbol_row: Dict[str, Any]) -> Dict[str, Any]:
            filters = symbol_row.get("filters") or []
            if not isinstance(filters, list):
                filters = []

            tick_size = 0.0
            step_size = 0.0
            min_qty = 0.0
            min_notional = 0.0

            for f in filters:
                if not isinstance(f, dict):
                    continue

                ftype = str(f.get("filterType") or "").strip().upper()

                if ftype == "PRICE_FILTER":
                    try:
                        tick_size = float(f.get("tickSize") or 0.0)
                    except Exception:
                        pass

                elif ftype == "LOT_SIZE":
                    try:
                        step_size = float(f.get("stepSize") or 0.0)
                    except Exception:
                        pass
                    try:
                        min_qty = float(f.get("minQty") or 0.0)
                    except Exception:
                        pass

                elif ftype in ("MIN_NOTIONAL", "NOTIONAL"):
                    try:
                        min_notional = float(
                            f.get("notional")
                            or f.get("minNotional")
                            or 0.0
                        )
                    except Exception:
                        pass

            out = dict(symbol_row)
            out["symbol"] = sym
            out["tick_size"] = float(tick_size)
            out["step"] = float(step_size)
            out["step_size"] = float(step_size)
            out["min_qty"] = float(min_qty)
            out["min_notional"] = float(min_notional)
            return out

        try:
            exch = self._get_exchange_info_cached(force_refresh=False)
            symbols = exch.get("symbols", []) if isinstance(exch, dict) else []
            for s in symbols:
                if isinstance(s, dict) and str(s.get("symbol", "")).upper().strip() == sym:
                    info = _extract(s)
                    try:
                        if self.logger:
                            self.logger.info(
                                "[EXEC][SYMBOL_INFO] resolved | symbol=%s tick_size=%.10f step=%.10f min_qty=%.10f min_notional=%.10f",
                                sym,
                                float(info.get("tick_size") or 0.0),
                                float(info.get("step") or 0.0),
                                float(info.get("min_qty") or 0.0),
                                float(info.get("min_notional") or 0.0),
                            )
                    except Exception:
                        pass
                    return info
        except Exception:
            pass

        try:
            exch = self._get_exchange_info_cached(force_refresh=True)
            symbols = exch.get("symbols", []) if isinstance(exch, dict) else []
            for s in symbols:
                if isinstance(s, dict) and str(s.get("symbol", "")).upper().strip() == sym:
                    info = _extract(s)
                    try:
                        if self.logger:
                            self.logger.info(
                                "[EXEC][SYMBOL_INFO] resolved(refresh) | symbol=%s tick_size=%.10f step=%.10f min_qty=%.10f min_notional=%.10f",
                                sym,
                                float(info.get("tick_size") or 0.0),
                                float(info.get("step") or 0.0),
                                float(info.get("min_qty") or 0.0),
                                float(info.get("min_notional") or 0.0),
                            )
                    except Exception:
                        pass
                    return info
        except Exception as e:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][SYMBOL_INFO] fetch failed | symbol=%s err=%s",
                        sym,
                        str(e),
                    )
            except Exception:
                pass

        return {
            "symbol": sym,
            "tick_size": 0.0,
            "step": 0.0,
            "step_size": 0.0,
            "min_qty": 0.0,
            "min_notional": 0.0,
        }

    def _fmt_qty(self, symbol: str, qty: float) -> str:
        sym = str(symbol).upper().strip()
        q = float(qty or 0.0)

        if q <= 0:
            return "0"

        step = 0.0
        try:
            s_info = self._get_symbol_info(sym)
            if isinstance(s_info, dict):
                step = float(s_info.get("step_size") or s_info.get("step") or 0.0)
        except Exception:
            step = 0.0

        if step <= 0:
            try:
                if abs(q - round(q)) < 1e-12:
                    return str(int(round(q)))
            except Exception:
                pass
            return ("%.10f" % q).rstrip("0").rstrip(".")

        step_s = ("%.16f" % step).rstrip("0").rstrip(".")
        if "." in step_s:
            decimals = len(step_s.split(".")[1])
        else:
            decimals = 0

        fmt = "{:0." + str(decimals) + "f}"
        return fmt.format(q)

    def _normalize_close_quantity(
        self,
        symbol: str,
        qty: float,
        price: float,
    ) -> Dict[str, Any]:
        sym = str(symbol).upper().strip()

        out: Dict[str, Any] = {
            "symbol": sym,
            "raw_qty": float(qty or 0.0),
            "norm_qty": 0.0,
            "price": float(price or 0.0),
            "step": 0.0,
            "min_qty": 0.0,
            "min_notional": 0.0,
            "reject_reason": "-",
        }

        try:
            raw_qty = abs(float(qty or 0.0))
        except Exception:
            raw_qty = 0.0

        try:
            px = float(price or 0.0)
        except Exception:
            px = 0.0

        out["raw_qty"] = float(raw_qty)
        out["price"] = float(px)

        if not sym or raw_qty <= 0.0:
            out["reject_reason"] = "raw_qty_invalid"
            return out

        info = {}
        try:
            info = self._get_symbol_info(sym)
        except Exception:
            info = {}

        def _f(x: Any, default: float = 0.0) -> float:
            try:
                v = float(x)
                if v < 0:
                    return float(default)
                return v
            except Exception:
                return float(default)

        step = _f(
            (info or {}).get("step")
            or (info or {}).get("step_size")
            or 0.0,
            0.0,
        )
        min_qty = _f((info or {}).get("min_qty") or 0.0, 0.0)
        min_notional = _f((info or {}).get("min_notional") or 0.0, 0.0)

        out["step"] = float(step)
        out["min_qty"] = float(min_qty)
        out["min_notional"] = float(min_notional)

        norm_qty = float(raw_qty)

        # step varsa aşağı yuvarla
        if step > 0.0:
            try:
                steps = int(raw_qty / step)
                norm_qty = float(steps * step)
            except Exception:
                norm_qty = 0.0

            try:
                step_str = f"{step:.16f}".rstrip("0")
                if "." in step_str:
                    decimals = len(step_str.split(".")[1])
                    norm_qty = round(norm_qty, decimals)
                else:
                    norm_qty = round(norm_qty, 0)
            except Exception:
                pass
        else:
            norm_qty = float(raw_qty)

        # min_qty kontrolü
        if min_qty > 0.0 and norm_qty < min_qty:
            out["norm_qty"] = 0.0
            out["reject_reason"] = "below_min_qty"
            return out

        # CLOSE PATH:
        # reduce-only close mantığında min_notional yüzünden qty'yi 0 yapma.
        # Burada amaç mevcut pozisyonu kapatmak; open gibi veto etme.
        if norm_qty <= 0.0:
            # son fallback: raw qty zaten min_qty ise en az min_qty ile dene
            if min_qty > 0.0 and raw_qty >= min_qty:
                norm_qty = float(min_qty)
            else:
                out["norm_qty"] = 0.0
                out["reject_reason"] = "normalized_zero"
                return out

        # ekstra güvenlik: step sonrası oluşan qty, raw_qty'den büyük olmasın
        if norm_qty > raw_qty:
            norm_qty = float(raw_qty)
            if step > 0.0:
                try:
                    steps = int(norm_qty / step)
                    norm_qty = float(steps * step)
                except Exception:
                    pass

        # close'ta min_notional veto etmiyoruz; sadece bilgi olarak logluyoruz
        if px > 0.0 and min_notional > 0.0 and (norm_qty * px) < min_notional:
            out["reject_reason"] = "below_min_notional_but_close_allowed"
        else:
            out["reject_reason"] = "-"

        if norm_qty <= 0.0:
            out["norm_qty"] = 0.0
            if out["reject_reason"] == "-":
                out["reject_reason"] = "normalized_zero"
            return out

        out["norm_qty"] = float(norm_qty)

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][CLOSE][QTY] symbol=%s raw_qty=%.10f norm_qty=%.10f price=%.6f step=%.10f min_qty=%.10f min_notional=%.6f reject=%s",
                    sym,
                    float(out["raw_qty"]),
                    float(out["norm_qty"]),
                    float(out["price"]),
                    float(out["step"]),
                    float(out["min_qty"]),
                    float(out["min_notional"]),
                    str(out["reject_reason"]),
                )
        except Exception:
            pass

        return out

    def _extract_symbol_filters(self, symbol_info: Dict[str, Any]) -> Dict[str, float]:
        out = {
            "step_size": 0.0,
            "min_qty": 0.0,
            "min_notional": 0.0,
            "tick_size": 0.0,
        }

        try:
            filters = symbol_info.get("filters", []) or []
            for f in filters:
                if not isinstance(f, dict):
                    continue

                ftype = str(f.get("filterType", "")).upper()

                if ftype in ("LOT_SIZE", "MARKET_LOT_SIZE"):
                    step_size = float(f.get("stepSize", 0.0) or 0.0)
                    min_qty = float(f.get("minQty", 0.0) or 0.0)

                    if step_size > 0:
                        out["step_size"] = max(out["step_size"], step_size)
                    if min_qty > 0:
                        out["min_qty"] = max(out["min_qty"], min_qty)

                elif ftype in ("MIN_NOTIONAL", "NOTIONAL"):
                    min_notional = f.get("notional") or f.get("minNotional") or 0.0
                    out["min_notional"] = float(min_notional or 0.0)

                elif ftype == "PRICE_FILTER":
                    tick_size = float(f.get("tickSize", 0.0) or 0.0)
                    if tick_size > 0:
                        out["tick_size"] = tick_size
        except Exception:
            pass

        return out

    @staticmethod
    def _round_qty(qty: float, digits: int = 12) -> float:
        try:
            return float(round(float(qty), int(digits)))
        except Exception:
            return 0.0

    @staticmethod
    def _floor_to_step(qty: float, step: float) -> float:
        if step <= 0:
            return float(qty)
        try:
            return math.floor(float(qty) / float(step)) * float(step)
        except Exception:
            return 0.0

    def _normalize_order_qty(
        self,
        symbol: str,
        raw_qty: float,
        price: float,
        symbol_info: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        sym = str(symbol).upper()
        px = float(price or 0.0)
        rq = float(raw_qty or 0.0)

        filters = self._extract_symbol_filters(symbol_info or {})
        step = float(filters.get("step_size", 0.0) or 0.0)
        min_qty = float(filters.get("min_qty", 0.0) or 0.0)
        min_notional = float(filters.get("min_notional", 0.0) or 0.0)

        q = float(rq)
        if step > 0:
            q = self._floor_to_step(q, step)
        q = self._round_qty(q)

        reject_reason = ""
        if q <= 0:
            reject_reason = "qty_le_zero"
        elif min_qty > 0 and q < min_qty:
            reject_reason = "below_min_qty"
        elif px > 0 and min_notional > 0 and (q * px) < min_notional:
            reject_reason = "below_min_notional"

        meta = {
            "symbol": sym,
            "raw_qty": float(rq),
            "price": float(px),
            "step_size": float(step),
            "min_qty": float(min_qty),
            "min_notional": float(min_notional),
            "normalized_qty": float(q),
            "normalized_notional": float(q * px),
            "reject_reason": str(reject_reason),
        }

        if reject_reason:
            return 0.0, meta
        return float(q), meta

    def _env_bool(self, key: str, default: bool = False) -> bool:
        try:
            return str(os.getenv(key, "1" if default else "0")).strip().lower() in (
                "1", "true", "yes", "on"
            )
        except Exception:
            return default

    def _env_float(self, key: str, default: float) -> float:
        try:
            v = os.getenv(key, "")
            if v is None or str(v).strip() == "":
                return float(default)
            return float(v)
        except Exception:
            return float(default)

    def _get_coin_side_min_open_score(
        self,
        symbol: str,
        side: str,
        default_score: float,
    ) -> float:
        sym = str(symbol or "").upper().strip()
        side_norm = str(side or "").lower().strip()

        enabled = self._env_bool("COIN_SIDE_MIN_SCORE_ENABLE", False)
        fallback_to_global = self._env_bool("COIN_SIDE_MIN_SCORE_FALLBACK_TO_GLOBAL", True)

        if not enabled or sym == "" or side_norm not in ("long", "short"):
            return float(default_score)

        key = f"COIN_{side_norm.upper()}_MIN_SCORE_{sym}"
        raw = os.getenv(key, "")

        if raw is None or str(raw).strip() == "":
            return float(default_score) if fallback_to_global else float(default_score)

        try:
            return float(raw)
        except Exception:
            return float(default_score)

    def _get_coin_side_thresholds(
        self,
        symbol: str,
        default_long_thr: float,
        default_short_thr: float,
    ) -> tuple[float, float]:
        sym = str(symbol or "").upper().strip()
        enabled = self._env_bool("COIN_SIDE_MODEL_THRESHOLD_ENABLE", False)

        if not enabled or sym == "":
            return float(default_long_thr), float(default_short_thr)

        long_key = f"COIN_LONG_THRESHOLD_{sym}"
        short_key = f"COIN_SHORT_THRESHOLD_{sym}"

        long_thr = self._env_float(long_key, default_long_thr)
        short_thr = self._env_float(short_key, default_short_thr)

        return float(long_thr), float(short_thr)

    def _adapt_dead_trade_thresholds(
        self,
        symbol: str,
        side: str,
        base_max_sec: float,
        base_min_best: float,
        signal_score: float,
        whale_score: float,
        whale_dir: str,
    ) -> tuple[float, float]:
        try:
            enabled = bool(int(os.getenv("DEAD_TRADE_ADAPTIVE_ENABLE", "1") or 1))
        except Exception:
            enabled = True

        if not enabled:
            return float(base_max_sec), float(base_min_best)

        try:
            score_thr = float(os.getenv("DEAD_TRADE_ADAPTIVE_SCORE_THR", "0.68") or 0.68)
            whale_thr = float(os.getenv("DEAD_TRADE_ADAPTIVE_WHALE_THR", "0.58") or 0.58)
            time_mult = float(os.getenv("DEAD_TRADE_ADAPTIVE_TIME_MULT", "1.50") or 1.50)
            minbest_mult = float(os.getenv("DEAD_TRADE_ADAPTIVE_MINBEST_MULT", "0.85") or 0.85)
        except Exception:
            score_thr = 0.68
            whale_thr = 0.58
            time_mult = 1.50
            minbest_mult = 0.85

        aligned = str(whale_dir or "").lower() == str(side or "").lower()

        max_sec = float(base_max_sec)
        min_best = float(base_min_best)

        if float(signal_score) >= score_thr and float(whale_score) >= whale_thr and aligned:
            max_sec *= float(time_mult)
            min_best *= float(minbest_mult)

            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][DEAD-TRADE][ADAPT] symbol=%s side=%s max_sec=%.1f min_best=%.6f signal_score=%.4f whale_score=%.4f whale_dir=%s",
                        symbol,
                        side,
                        float(max_sec),
                        float(min_best),
                        float(signal_score),
                        float(whale_score),
                        str(whale_dir),
                    )
            except Exception:
                pass

        return float(max_sec), float(min_best)













    # ---------------------------------------------------------
    # leverage helpers
    # ---------------------------------------------------------
    def _resolve_signal_score_for_open(
        self,
        side: str,
        extra: Optional[Dict[str, Any]] = None,
        probs: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Canonical MODEL SCORE GATE authority.

        Only immutable side-specific model_score may authorize OPEN.

        ranking/policy fields such as:
          - signal_score
          - score
          - score_total
          - _score_selected
          - _score_total_final

        are intentionally ignored here.

        Missing / malformed model_score fails closed.
        """
        extra0 = extra if isinstance(extra, dict) else {}

        raw0 = extra0.get("raw") or {}

        if isinstance(raw0, str):
            try:
                raw0 = json.loads(raw0)
            except Exception:
                raw0 = {}

        if not isinstance(raw0, dict):
            raw0 = {}

        def _read_model_score(
            container: Dict[str, Any],
        ) -> Optional[float]:
            if not isinstance(container, dict):
                return None

            if "model_score" not in container:
                return None

            try:
                value = float(
                    container.get("model_score")
                )
            except Exception:
                return 0.0

            if not math.isfinite(value):
                return 0.0

            return max(
                0.0,
                min(1.0, value),
            )

        # Current/fresh context is authoritative.
        score = _read_model_score(extra0)

        if score is not None:
            return float(score)

        # Orchestration may wrap the original intent/event in raw.
        score = _read_model_score(raw0)

        if score is not None:
            return float(score)

        # Missing immutable model score must never be rescued by
        # ranking/policy scores or probability heuristics.
        return 0.0

    def _resolve_target_leverage(
        self,
        extra: Optional[Dict[str, Any]] = None,
    ) -> int:
        target = int(
            self.default_order_leverage
        )

        target = max(
            1,
            min(
                int(target),
                int(self.max_leverage),
            ),
        )

        return int(target)

    def _set_symbol_leverage(self, symbol: str, leverage: int) -> int:
        sym = str(symbol).upper()
        lev = int(max(1, leverage))

        try:
            import time, os
            ttl = float(os.getenv("LEVERAGE_SET_CACHE_TTL_SEC", "3600") or 3600)
            cache = getattr(self, "_leverage_set_cache", None)
            if not isinstance(cache, dict):
                cache = {}
                setattr(self, "_leverage_set_cache", cache)
            now = time.time()
            prev = cache.get(sym)
            if isinstance(prev, dict) and int(prev.get("lev") or 0) == int(lev) and (now - float(prev.get("ts") or 0)) < ttl:
                if self.logger:
                    self.logger.info("[EXEC][LEV][SKIP] symbol=%s leverage=%s cache=1", sym, int(lev))
                return int(lev)
        except Exception:
            cache = None
            now = 0.0

        client = getattr(self, "client", None)
        if client is None:
            return lev

        fn = getattr(client, "futures_change_leverage", None)
        if not callable(fn):
            return lev

        resp = fn(symbol=sym, leverage=lev)

        try:
            if isinstance(cache, dict):
                cache[sym] = {"lev": int(lev), "ts": float(now)}
        except Exception:
            pass

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][LEV][SET] symbol=%s requested=%s response=%s",
                    sym,
                    int(lev),
                    self._safe_json(resp, limit=900),
                )
        except Exception:
            pass

        try:
            if isinstance(resp, dict):
                return int(resp.get("leverage") or lev)
        except Exception:
            pass

        return lev

    # ---------------------------------------------------------
    # equity / notional
    # ---------------------------------------------------------
    def _get_futures_equity_usdt_sync(self) -> float:
        client = getattr(self, "client", None)
        if client is None:
            return 0.0

        try:
            fn = getattr(client, "futures_account_balance", None)
            if callable(fn):
                rows = fn()
                if isinstance(rows, list):
                    for r in rows:
                        if str(r.get("asset", "")).upper() == "USDT":
                            bal = self._clip_float(r.get("balance"), 0.0) or 0.0
                            cw = self._clip_float(r.get("crossWalletBalance"), None)
                            if cw is not None and cw > 0:
                                return float(cw)
                            return float(bal)
        except Exception:
            pass

        try:
            rows = _futures_v3_balance()
            for r in rows:
                if str(r.get("asset", "")).upper() == "USDT":
                    bal = self._clip_float(r.get("balance"), 0.0) or 0.0
                    cw = self._clip_float(r.get("crossWalletBalance"), None)
                    if cw is not None and cw > 0:
                        return float(cw)
                    return float(bal)
        except Exception:
            pass

        return 0.0

    async def _get_futures_equity_usdt(self) -> float:
        return float(self._get_futures_equity_usdt_sync())


    # ---------------------------------------------------------
    # position state helpers
    # ---------------------------------------------------------
    def _pos_key(self, symbol: str) -> str:
        return f"bot:positions:{str(symbol).upper()}"

    def _get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        sym = str(symbol).upper()

        try:
            pm = getattr(self, "position_manager", None)
            if pm is not None and hasattr(pm, "get_position"):
                pos = pm.get_position(sym)
                if isinstance(pos, dict):
                    return pos
        except Exception:
            pass

        try:
            if self.redis is not None:
                raw = self.redis.get(self._pos_key(sym))
                if raw:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="ignore")
                    obj = json.loads(raw)
                    if isinstance(obj, dict):
                        return obj
        except Exception:
            pass

        return None

    def _store_latest_signal(
        self,
        symbol: str,
        side: str,
        interval: str,
        score: float,
        raw: Optional[Dict[str, Any]] = None,
    ) -> None:
        sym = str(symbol).upper().strip()
        if not sym:
            return

        r = getattr(self, "redis", None) or getattr(self, "redis_client", None)
        if r is None:
            return

        try:
            payload = {
                "symbol": sym,
                "side": str(side or "").strip().lower(),
                "interval": str(interval or "").strip(),
                "score": float(score or 0.0),
                "ts": float(time.time()),
                "raw": raw if isinstance(raw, dict) else {},
            }

            serialized = json.dumps(payload, ensure_ascii=False, default=str)

            try:
                r.set(f"bot:last_signal:{sym}", serialized, ex=3600)
            except TypeError:
                r.set(f"bot:last_signal:{sym}", serialized)
                try:
                    r.expire(f"bot:last_signal:{sym}", 3600)
                except Exception:
                    pass

            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][WEAK] latest signal stored | symbol=%s side=%s interval=%s score=%.6f",
                        sym,
                        str(side or "").strip().lower(),
                        str(interval or "").strip(),
                        float(score or 0.0),
                    )
            except Exception:
                pass

        except Exception:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][WEAK] latest signal store failed | symbol=%s",
                        sym,
                    )
            except Exception:
                pass
    def _evaluate_position_signal_exit(
        self,
        symbol: str,
        pos: Dict[str, Any],
        price: float,
    ) -> Optional[Dict[str, Any]]:
        import json
        import time

        sym = str(symbol).upper().strip()
        if not sym or not isinstance(pos, dict):
            return None

        side = str(pos.get("side") or "").strip().lower()
        entry_price = float(pos.get("entry_price") or 0.0)

        if side not in ("long", "short") or entry_price <= 0:
            return None

        # ---------------------------------
        # PNL hesap
        # ---------------------------------
        if side == "long":
            pnl_pct = (price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - price) / entry_price

        # ---------------------------------
        # reverse / weak enable
        # ---------------------------------
        if not bool(getattr(self, "reverse_close_enabled", True)):
            return None

        r = getattr(self, "redis", None) or getattr(self, "redis_client", None)
        if r is None:
            return None

        # ---------------------------------
        # son sinyal oku
        # ---------------------------------
        try:
            raw = r.get(f"bot:last_signal:{sym}")
            if not raw:
                return None

            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")

            sig = json.loads(raw)
            if not isinstance(sig, dict):
                return None
        except Exception:
            return None

        sig_side = str(sig.get("side") or "").strip().lower()
        sig_score = float(sig.get("score") or 0.0)
        sig_ts = float(sig.get("ts") or 0.0)

        now_ts = time.time()

        # ---------------------------------
        # thresholdlar
        # ---------------------------------
        min_score = float(self.opposite_signal_min_score)
        max_age = float(self.opposite_signal_max_age_sec)
        confirm_need = int(self.opposite_signal_confirm_count)

        tp_arm = float(getattr(self, "tp_arm_pnl_pct", 0.02))  # %2

        opposite_side = (
            "short"
            if side == "long"
            else "long"
        )

        confirm_key = (
            f"bot:reverse_confirm:"
            f"{sym}:{side}:{opposite_side}"
        )

        last_sig_key = (
            f"bot:reverse_confirm_last_sig:"
            f"{sym}:{side}:{opposite_side}"
        )

        ttl_sec = int(max(30, max_age))

        def _reset_reverse_confirmation(
            reset_reason: str,
        ) -> None:
            try:
                r.delete(
                    confirm_key,
                    last_sig_key,
                )
            except TypeError:
                try:
                    r.delete(confirm_key)
                    r.delete(last_sig_key)
                except Exception:
                    pass
            except Exception:
                pass

            try:
                if self.logger:
                    self.logger.debug(
                        "[EXEC][REVERSE][CONFIRM-RESET] "
                        "symbol=%s position_side=%s "
                        "signal_side=%s score=%.4f "
                        "reason=%s",
                        sym,
                        side,
                        sig_side,
                        float(sig_score),
                        str(reset_reason),
                    )
            except Exception:
                pass

        # ---------------------------------
        # Consecutive confirmation rules
        # ---------------------------------
        if sig_side not in ("long", "short"):
            _reset_reverse_confirmation(
                "invalid_signal_side"
            )
            return None

        if (
            not sig_ts
            or (now_ts - sig_ts) > max_age
        ):
            _reset_reverse_confirmation(
                "stale_signal"
            )
            return None

        if sig_score < min_score:
            _reset_reverse_confirmation(
                "score_below_threshold"
            )
            return None

        opposite = (
            sig_side == opposite_side
        )

        if not opposite:
            _reset_reverse_confirmation(
                "same_side_signal"
            )
            return None

        # ---------------------------------
        # CONFIRMATION
        #
        # 1) yalnız qualifying opposite signal sayılır
        # 2) aynı signal timestamp tekrar sayılmaz
        # 3) same-side / weak / stale signal seriyi resetler
        # ---------------------------------

        same_signal = False

        try:
            last_sig_raw = r.get(last_sig_key)

            if isinstance(
                last_sig_raw,
                (bytes, bytearray),
            ):
                last_sig_raw = last_sig_raw.decode(
                    "utf-8",
                    errors="ignore",
                )

            if last_sig_raw is not None:
                last_sig_ts = float(last_sig_raw)

                same_signal = (
                    abs(
                        float(last_sig_ts)
                        - float(sig_ts)
                    )
                    <= 1e-6
                )

        except Exception:
            same_signal = False

        if same_signal:
            # Aynı signal tekrar okundu:
            # confirmation sayısını ARTIRMA.
            try:
                raw_count = r.get(confirm_key)

                if isinstance(
                    raw_count,
                    (bytes, bytearray),
                ):
                    raw_count = raw_count.decode(
                        "utf-8",
                        errors="ignore",
                    )

                confirm_count = int(
                    raw_count or 0
                )

            except Exception:
                confirm_count = 0

        else:
            # Yalnız yeni signal observation confirm ekler.
            try:
                confirm_count = int(
                    r.incr(confirm_key)
                )

                r.expire(
                    confirm_key,
                    ttl_sec,
                )

                r.set(
                    last_sig_key,
                    str(float(sig_ts)),
                    ex=ttl_sec,
                )

            except Exception:
                confirm_count = 1

        if confirm_count < confirm_need:
            return None

        # Threshold'a ulaşıldığında key'i burada silmiyoruz.
        #
        # Böylece aynı signal:
        #   - confirmation'ı tekrar artırmaz
        #   - fakat fiziksel close başarısız olursa
        #     sonraki lifecycle tick yeniden close
        #     decision üretebilir.
        try:
            r.expire(
                confirm_key,
                ttl_sec,
            )
            r.expire(
                last_sig_key,
                ttl_sec,
            )
        except Exception:
            pass

        # ---------------------------------
        # 🔥 ANA MANTIK
        # ---------------------------------

        # 1️⃣ %2+ KÂR VAR → TERS SİNYALDE ANINDA ÇIK
        if pnl_pct >= tp_arm:
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][PROFIT-REVERSE] close | symbol=%s side=%s pnl=%.4f sig=%s score=%.4f",
                        sym,
                        side,
                        pnl_pct,
                        sig_side,
                        sig_score,
                    )
            except Exception:
                pass

            return {
                "action": "close",
                "reason": "profit_reverse",
                "pnl_pct": float(pnl_pct),
                "signal_score": float(sig_score),
            }

        # 2️⃣ düşük kâr / zarar → klasik reverse close
        if pnl_pct < tp_arm:
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][REVERSE] close | symbol=%s side=%s pnl=%.4f sig=%s",
                        sym,
                        side,
                        pnl_pct,
                        sig_side,
                    )
            except Exception:
                pass

            return {
                "action": "close",
                "reason": "reverse_signal",
                "pnl_pct": float(pnl_pct),
                "signal_score": float(sig_score),
            }

        return None
    def _resolve_position_leverage(self, pos: Dict[str, Any]) -> float:
        extra = pos.get("extra") if isinstance(pos, dict) else None
        extra = extra if isinstance(extra, dict) else {}

        candidates = [
            pos.get("leverage") if isinstance(pos, dict) else None,
            pos.get("target_leverage") if isinstance(pos, dict) else None,
            extra.get("target_leverage"),
            getattr(self, "default_order_leverage", None),
            1,
        ]

        for v in candidates:
            try:
                f = float(v)
                if f > 0:
                    return f
            except Exception:
                pass

        return 1.0

    def _calc_unrealized_pnl_usdt(
        self,
        side: str,
        entry_price: float,
        price: float,
        qty: float,
    ) -> float:
        try:
            entry = float(entry_price)
            px = float(price)
            q = float(qty)
        except Exception:
            return 0.0

        if entry <= 0 or px <= 0 or q <= 0:
            return 0.0

        if str(side).lower().strip() == "long":
            return (px - entry) * q
        return (entry - px) * q

    def _evaluate_scalp_exit_pro(
        self,
        symbol: str,
        pos: Dict[str, Any],
        price: float,
        side: str,
        entry_price: float,
        highest_price: float,
        lowest_price: float,
        best_pnl_pct: float,
        last_best_ts: float,
        now_ts: float,
        reverse_meta_provider=None,
    ) -> Optional[str]:
        scalp_enabled = bool(
            getattr(
                self,
                "scalp_exit_enable",
                getattr(self, "scalp_engine_enable", True),
            )
        )
        if not scalp_enabled:
            return None

        try:
            opened_at_raw = str(pos.get("opened_at") or "").strip()
            opened_ts = 0.0
            if opened_at_raw:
                try:
                    opened_ts = datetime.fromisoformat(
                        opened_at_raw.replace("Z", "+00:00")
                    ).timestamp()
                except Exception:
                    opened_ts = 0.0

            grace_sec = float(getattr(self, "scalp_grace_sec", 15) or 15)
            if opened_ts > 0 and (float(now_ts) - float(opened_ts)) < grace_sec:
                return None
        except Exception:
            pass

        side_norm = str(side or "").strip().lower()
        sym_u = str(symbol or "").upper().strip()

        sym = sym_u
        pos_side = side_norm
        interval = str(os.getenv("INTERVAL","3m"))

        if side_norm == "long":
            pnl_pct = (float(price) - float(entry_price)) / max(float(entry_price), 1e-12)
            retrace_pct = (
                (float(highest_price) - float(price)) / max(float(highest_price), 1e-12)
                if float(highest_price) > 0
                else 0.0
            )
        else:
            pnl_pct = (float(entry_price) - float(price)) / max(float(entry_price), 1e-12)
            retrace_pct = (
                (float(price) - float(lowest_price)) / max(float(lowest_price), 1e-12)
                if float(lowest_price) > 0
                else 0.0
            )

        lev = float(self._resolve_position_leverage(pos))
        roi_pct = float(pnl_pct) * lev
        best_roi_pct = float(best_pnl_pct) * lev
        retrace_roi_pct = float(retrace_pct) * lev

        # =========================
        # EARLY SCALP TP (çok kritik)
        # =========================
        try:
            early_tp_enable = str(os.getenv("EARLY_TP_ENABLE", "1")).lower() in ("1","true","yes","on")
        except:
            early_tp_enable = True

        early_tp_roi = float(os.getenv("EARLY_TP_ROI", "0.0025") or 0.0025)

        if early_tp_enable and roi_pct >= early_tp_roi:
            if self.logger:
                self.logger.info(
                    "[EXEC][CLOSE] reason=early_tp symbol=%s roi=%.4f",
                    sym, roi_pct
                )

            return "early_tp"

        # =========================
        # FIXED ROI authority:
        # yalnız _evaluate_lifecycle_roi_exit tarafından yönetilir.

        # =========================
        # STEP TP + PROFIT LOCK
        # =========================
        try:
            step_tp_enable = str(
                os.getenv("STEP_TP_ENABLE", "0")
            ).strip().lower() in ("1", "true", "yes", "on")
        except Exception:
            step_tp_enable = False

        try:
            step_tp_step_usdt = float(os.getenv("STEP_TP_STEP_USDT", "0.10") or 0.10)
        except Exception:
            step_tp_step_usdt = 0.10

        try:
            step_tp_max_target_usdt = float(os.getenv("STEP_TP_MAX_TARGET_USDT", "0.50") or 0.50)
        except Exception:
            step_tp_max_target_usdt = 0.50

        try:
            step_tp_giveback_usdt = float(os.getenv("STEP_TP_GIVEBACK_USDT", "0.04") or 0.04)
        except Exception:
            step_tp_giveback_usdt = 0.04

        try:
            step_tp_min_lock_usdt = float(os.getenv("STEP_TP_MIN_LOCK_USDT", "0.08") or 0.08)
        except Exception:
            step_tp_min_lock_usdt = 0.08

        try:
            pos_notional = float(pos.get("notional") or 0.0)
        except Exception:
            pos_notional = 0.0

        try:
            live_pnl_usdt = float(roi_pct) * float(pos_notional)
        except Exception:
            live_pnl_usdt = 0.0

        try:
            best_pnl_usdt_step = float(best_roi_pct) * float(pos_notional)
        except Exception:
            best_pnl_usdt_step = 0.0

        if step_tp_enable and pos_notional > 0:
            try:
                current_step = int(best_pnl_usdt_step // step_tp_step_usdt)
            except Exception:
                current_step = 0

            target_usdt = min(
                float(step_tp_max_target_usdt),
                max(float(step_tp_step_usdt), float(current_step + 1) * float(step_tp_step_usdt)),
            )

            giveback_hit = (
                best_pnl_usdt_step >= float(step_tp_min_lock_usdt)
                and (best_pnl_usdt_step - live_pnl_usdt) >= float(step_tp_giveback_usdt)
            )

            max_target_hit = (
                best_pnl_usdt_step >= float(step_tp_max_target_usdt)
                and live_pnl_usdt >= float(step_tp_max_target_usdt)
            )

            if giveback_hit or max_target_hit:
                close_reason = "step_tp_giveback" if giveback_hit else "step_tp_max_target"

                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][CLOSE] reason=%s symbol=%s side=%s live_pnl=%.4f best_pnl=%.4f target=%.4f giveback=%.4f roi=%.4f best_roi=%.4f",
                            close_reason,
                            sym,
                            pos_side,
                            float(live_pnl_usdt),
                            float(best_pnl_usdt_step),
                            float(target_usdt),
                            float(step_tp_giveback_usdt),
                            float(roi_pct),
                            float(best_roi_pct),
                        )
                except Exception:
                    pass

                return str(close_reason)
        # =========================
        # ANTI REVERSAL
        # =========================
        try:
            anti_enable = str(os.getenv("ANTI_REVERSAL_ENABLE", "0")).lower() in ("1","true","yes","on")
        except:
            anti_enable = False

        anti_max_age = float(os.getenv("ANTI_REVERSAL_MAX_AGE_SEC", "180") or 180)
        anti_arm = float(os.getenv("ANTI_REVERSAL_MIN_ROI_TO_ARM", "0.0015") or 0.0015)
        anti_pullback = float(os.getenv("ANTI_REVERSAL_PULLBACK_ROI_PCT", "0.0025") or 0.0025)

        best_roi = float(pos.get("best_pnl_pct") or 0.0)

        opened_at = pos.get("opened_at")
        age = 0.0
        if isinstance(opened_at, (int, float)):
            age = time.time() - float(opened_at)

        if anti_enable and age <= anti_max_age:
            armed = best_roi >= anti_arm

            pullback_hit = armed and (best_roi - roi_pct) >= anti_pullback

            if pullback_hit:
                if self.logger:
                    self.logger.info(
                        "[EXEC][CLOSE] reason=anti_reversal symbol=%s roi=%.4f best=%.4f",
                        sym, roi_pct, best_roi
                    )

                return "anti_reversal"

        roi_hard_stop_pct = abs(
            float(self.roi_hard_stop_pct)
        )

        # ---------------------------------------------
        # EARLY-EXIT SAFETY GUARDS
        # ---------------------------------------------
        try:
            exit_min_hold_sec = float(os.getenv("EXIT_MIN_HOLD_SEC", "35") or 35)
        except Exception:
            exit_min_hold_sec = 35.0

        try:
            exit_min_best_roi_pct = float(os.getenv("EXIT_MIN_BEST_ROI_PCT", "0.0300") or 0.0300)
        except Exception:
            exit_min_best_roi_pct = 0.0300

        try:
            exit_min_live_roi_pct = float(os.getenv("EXIT_MIN_LIVE_ROI_PCT", "0.0100") or 0.0100)
        except Exception:
            exit_min_live_roi_pct = 0.0100

        try:
            exit_early_profit_protect_sec = float(
                os.getenv("EXIT_EARLY_PROFIT_PROTECT_SEC", "90") or 90
            )
        except Exception:
            exit_early_profit_protect_sec = 90.0

        scalp_profit_arm_roi_pct = float(
            getattr(self, "scalp_profit_arm_roi_pct", 0.0300) or 0.0300
        )
        scalp_fast_exit_profit_roi_pct = float(
            getattr(self, "scalp_fast_exit_profit_roi_pct", 0.0450) or 0.0450
        )
        scalp_fast_exit_pullback_roi_pct = float(
            getattr(self, "scalp_fast_exit_pullback_roi_pct", 0.0100) or 0.0100
        )
        scalp_retrace_roi_pct = float(
            getattr(self, "scalp_retrace_roi_pct", 0.0120) or 0.0120
        )
        scalp_micro_pullback_roi_pct = float(
            getattr(self, "scalp_micro_pullback_roi_pct", 0.0090) or 0.0090
        )
        scalp_deep_pullback_roi_pct = float(
            getattr(self, "scalp_deep_pullback_roi_pct", 0.0160) or 0.0160
        )
        scalp_reverse_min_score = float(
            getattr(self, "scalp_reverse_min_score", 0.58) or 0.58
        )
        scalp_stall_min_profit_roi_pct = float(
            getattr(self, "scalp_stall_min_profit_roi_pct", 0.0200) or 0.0200
        )
        scalp_stall_after_profit_sec = float(
            getattr(self, "scalp_stall_after_profit_sec", 90) or 90
        )

        # Pozisyon çok tazeyse scalp exit hiç çalışma
        try:
            held_sec = float(now_ts) - float(opened_ts or 0.0)
        except Exception:
            held_sec = 999999.0

        if opened_ts > 0 and held_sec < exit_min_hold_sec:
            return None

        # Çok küçük kârdayken erken profit-lock / retrace çıkışlarını engelle
        early_profit_protection_active = (
            float(pnl_pct) > 0.0
            and held_sec < exit_early_profit_protect_sec
            and (
                float(best_roi_pct) < exit_min_best_roi_pct
                or float(roi_pct) < exit_min_live_roi_pct
            )
        )

        profile_cfg = self._apply_exit_profile(
            symbol=symbol,
            scalp_fast_exit_pullback_roi_pct=scalp_fast_exit_pullback_roi_pct,
            scalp_retrace_roi_pct=scalp_retrace_roi_pct,
            scalp_micro_pullback_roi_pct=scalp_micro_pullback_roi_pct,
            scalp_deep_pullback_roi_pct=scalp_deep_pullback_roi_pct,
            scalp_stall_after_profit_sec=scalp_stall_after_profit_sec,
            profit_lock_retrace_roi_pct=scalp_retrace_roi_pct,
        )

        profile = profile_cfg["profile"]
        scalp_fast_exit_pullback_roi_pct = profile_cfg["scalp_fast_exit_pullback_roi_pct"]
        scalp_retrace_roi_pct = profile_cfg["scalp_retrace_roi_pct"]
        scalp_micro_pullback_roi_pct = profile_cfg["scalp_micro_pullback_roi_pct"]
        scalp_deep_pullback_roi_pct = profile_cfg["scalp_deep_pullback_roi_pct"]
        scalp_stall_after_profit_sec = profile_cfg["scalp_stall_after_profit_sec"]

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][EXIT-PROFILE] symbol=%s profile=%s fast_pb=%.6f retrace=%.6f micro_pb=%.6f deep_pb=%.6f stall_after_profit=%.2f",
                    symbol,
                    profile,
                    scalp_fast_exit_pullback_roi_pct,
                    scalp_retrace_roi_pct,
                    scalp_micro_pullback_roi_pct,
                    scalp_deep_pullback_roi_pct,
                    scalp_stall_after_profit_sec,
                )
        except Exception:
            pass

        # ------------------------------
        # EXTRA / META NORMALIZE
        # ------------------------------
        extra0: Dict[str, Any] = {}

        try:
            pos_extra = pos.get("extra")
            if isinstance(pos_extra, dict):
                extra0.update(pos_extra)
        except Exception:
            pass

        try:
            pos_meta = pos.get("meta")
            if isinstance(pos_meta, dict):
                meta_extra = pos_meta.get("extra")
                if isinstance(meta_extra, dict):
                    extra0.update(meta_extra)
                extra0.update(pos_meta)
        except Exception:
            pass

        try:
            if isinstance(pos, dict):
                extra0.update(pos)
        except Exception:
            pass

        # ------------------------------
        # TREND CONTINUATION FILTER (MTF: 1m + 5m)
        # ------------------------------
        try:
            trend_continue_enable = str(
                os.getenv("EXIT_TREND_CONTINUATION_ENABLE", "1")
            ).strip().lower() in ("1", "true", "yes", "on")
        except Exception:
            trend_continue_enable = True

        if trend_continue_enable:
            try:
                tc_min_profit = float(
                    os.getenv("EXIT_TREND_CONTINUE_MIN_PROFIT_PCT", "0.0015") or 0.0015
                )
            except Exception:
                tc_min_profit = 0.0015

            try:
                tc_whale_min = float(
                    os.getenv("EXIT_TREND_CONTINUE_MIN_WHALE_SCORE", "0.18") or 0.18
                )
            except Exception:
                tc_whale_min = 0.18

            try:
                whale_dir_tc = str(extra0.get("whale_dir") or "").strip().lower()
            except Exception:
                whale_dir_tc = ""

            try:
                whale_score_tc = float(extra0.get("whale_score") or 0.0)
            except Exception:
                whale_score_tc = 0.0

            try:
                ema_1m_tc = self._backfill_ema_metrics(
                    symbol=sym_u,
                    interval="1m",
                    extra=extra0,
                )
            except Exception:
                ema_1m_tc = {}

            try:
                ema_5m_tc = self._backfill_ema_metrics(
                    symbol=sym_u,
                    interval="3m",
                    extra=extra0,
                )
            except Exception:
                ema_5m_tc = {}

            try:
                ema7_1m_tc = float(ema_1m_tc.get("ema7") or ema_1m_tc.get("ema_fast") or 0.0)
            except Exception:
                ema7_1m_tc = 0.0

            try:
                ema25_1m_tc = float(ema_1m_tc.get("ema25") or ema_1m_tc.get("ema_slow") or 0.0)
            except Exception:
                ema25_1m_tc = 0.0

            try:
                ema99_1m_tc = float(ema_1m_tc.get("ema99") or 0.0)
            except Exception:
                ema99_1m_tc = 0.0

            try:
                ema7_5m_tc = float(ema_5m_tc.get("ema7") or ema_5m_tc.get("ema_fast") or 0.0)
            except Exception:
                ema7_5m_tc = 0.0

            try:
                ema25_5m_tc = float(ema_5m_tc.get("ema25") or ema_5m_tc.get("ema_slow") or 0.0)
            except Exception:
                ema25_5m_tc = 0.0

            try:
                ema99_5m_tc = float(ema_5m_tc.get("ema99") or 0.0)
            except Exception:
                ema99_5m_tc = 0.0

            trend_ok = False

            if side_norm == "long":
                long_1m_ok = (
                    ema7_1m_tc > 0
                    and ema25_1m_tc > 0
                    and ema7_1m_tc >= ema25_1m_tc
                )

                long_5m_ok = (
                    ema7_5m_tc > 0
                    and ema25_5m_tc > 0
                    and ema99_5m_tc > 0
                    and ema7_5m_tc >= ema25_5m_tc >= ema99_5m_tc
                )

                if long_1m_ok and long_5m_ok:
                    trend_ok = True
                elif float(best_roi_pct) > float(roi_pct):
                    trend_ok = True

                if whale_dir_tc == "short" and whale_score_tc >= tc_whale_min:
                    trend_ok = False

            elif side_norm == "short":
                short_1m_ok = (
                    ema7_1m_tc > 0
                    and ema25_1m_tc > 0
                    and ema7_1m_tc <= ema25_1m_tc
                )

                short_5m_ok = (
                    ema7_5m_tc > 0
                    and ema25_5m_tc > 0
                    and ema99_5m_tc > 0
                    and ema7_5m_tc <= ema25_5m_tc <= ema99_5m_tc
                )

                if short_1m_ok and short_5m_ok:
                    trend_ok = True
                elif float(best_roi_pct) > float(roi_pct):
                    trend_ok = True

                if whale_dir_tc == "long" and whale_score_tc >= tc_whale_min:
                    trend_ok = False

            if trend_ok and pnl_pct is not None and float(pnl_pct) >= float(tc_min_profit):
                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][EXIT-BLOCK][TREND-CONTINUE] symbol=%s side=%s pnl_pct=%.6f roi_pct=%.6f best_roi_pct=%.6f "
                            "ema7_1m=%.6f ema25_1m=%.6f ema99_1m=%.6f "
                            "ema7_5m=%.6f ema25_5m=%.6f ema99_5m=%.6f "
                            "whale_dir=%s whale_score=%.4f",
                            sym_u,
                            side_norm,
                            float(pnl_pct),
                            float(roi_pct),
                            float(best_roi_pct),
                            float(ema7_1m_tc),
                            float(ema25_1m_tc),
                            float(ema99_1m_tc),
                            float(ema7_5m_tc),
                            float(ema25_5m_tc),
                            float(ema99_5m_tc),
                            whale_dir_tc,
                            float(whale_score_tc),
                        )
                except Exception:
                    pass
                return None

        # ------------------------------
        # PROFIT-LOCK SAFETY GATE
        # ------------------------------
        try:
            profit_lock_min_best_roi_pct = float(
                os.getenv("PROFIT_LOCK_MIN_BEST_ROI_PCT", "0.040") or 0.040
            )
        except Exception:
            profit_lock_min_best_roi_pct = 0.040

        try:
            profit_lock_min_live_roi_pct = float(
                os.getenv("PROFIT_LOCK_MIN_LIVE_ROI_PCT", "0.015") or 0.015
            )
        except Exception:
            profit_lock_min_live_roi_pct = 0.015

        try:
            profit_lock_min_hold_sec = float(
                os.getenv("PROFIT_LOCK_MIN_HOLD_SEC", "60") or 60
            )
        except Exception:
            profit_lock_min_hold_sec = 60.0

        try:
            held_sec = float(now_ts) - float(opened_ts or 0.0)
        except Exception:
            held_sec = 999999.0

        profit_lock_allowed = (
            float(best_roi_pct) >= float(profit_lock_min_best_roi_pct)
            and float(roi_pct) >= float(profit_lock_min_live_roi_pct)
            and float(held_sec) >= float(profit_lock_min_hold_sec)
        )

        if float(roi_pct) <= -roi_hard_stop_pct:
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][SCALP] exit trigger | symbol=%s side=%s profile=%s reason=%s price=%.8f entry=%.8f pnl_pct=%.6f best_pnl_pct=%.6f",
                        symbol,
                        side,
                        profile,
                        "scalp_hard_stop_roi",
                        float(price),
                        float(entry_price),
                        float(pnl_pct),
                        float(best_pnl_pct),
                    )
            except Exception:
                pass
            return "scalp_hard_stop_roi"

        if (
            profit_lock_allowed
            and float(best_roi_pct) >= scalp_fast_exit_profit_roi_pct
            and float(retrace_roi_pct) >= scalp_fast_exit_pullback_roi_pct
        ):
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][SCALP] exit trigger | symbol=%s side=%s profile=%s reason=%s price=%.8f entry=%.8f pnl_pct=%.6f best_pnl_pct=%.6f",
                        symbol,
                        side,
                        profile,
                        "scalp_fast_exit_roi",
                        float(price),
                        float(entry_price),
                        float(pnl_pct),
                        float(best_pnl_pct),
                    )
            except Exception:
                pass
            return "scalp_fast_exit_roi"

        if (
            profit_lock_allowed
            and float(best_roi_pct) >= scalp_profit_arm_roi_pct
            and float(retrace_roi_pct) >= scalp_retrace_roi_pct
        ):
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][SCALP] exit trigger | symbol=%s side=%s profile=%s reason=%s price=%.8f entry=%.8f pnl_pct=%.6f best_pnl_pct=%.6f",
                        symbol,
                        side,
                        profile,
                        "scalp_profit_retrace_roi",
                        float(price),
                        float(entry_price),
                        float(pnl_pct),
                        float(best_pnl_pct),
                    )
            except Exception:
                pass
            return "scalp_profit_retrace_roi"

        if (
            profit_lock_allowed
            and float(best_roi_pct) >= scalp_profit_arm_roi_pct
            and float(retrace_roi_pct) >= scalp_micro_pullback_roi_pct
        ):
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][SCALP] exit trigger | symbol=%s side=%s profile=%s reason=%s price=%.8f entry=%.8f pnl_pct=%.6f best_pnl_pct=%.6f",
                        symbol,
                        side,
                        profile,
                        "scalp_micro_pullback_exit_roi",
                        float(price),
                        float(entry_price),
                        float(pnl_pct),
                        float(best_pnl_pct),
                    )
            except Exception:
                pass
            return "scalp_micro_pullback_exit_roi"

        if (
            profit_lock_allowed
            and float(best_roi_pct) >= max(scalp_profit_arm_roi_pct, scalp_micro_pullback_roi_pct)
            and float(retrace_roi_pct) >= scalp_deep_pullback_roi_pct
        ):
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][SCALP] exit trigger | symbol=%s side=%s profile=%s reason=%s price=%.8f entry=%.8f pnl_pct=%.6f best_pnl_pct=%.6f",
                        symbol,
                        side,
                        profile,
                        "scalp_deep_pullback_exit_roi",
                        float(price),
                        float(entry_price),
                        float(pnl_pct),
                        float(best_pnl_pct),
                    )
            except Exception:
                pass
            return "scalp_deep_pullback_exit_roi"

        try:
            reverse_meta = (
                reverse_meta_provider()
                if callable(reverse_meta_provider)
                else {}
            )
        except Exception:
            reverse_meta = {}

        if isinstance(reverse_meta, dict):
            try:
                reverse_score = float(reverse_meta.get("signal_score") or 0.0)
            except Exception:
                reverse_score = 0.0

            if (
                str(reverse_meta.get("reason") or "") == "reverse_signal"
                and float(reverse_score) >= scalp_reverse_min_score
                and float(best_roi_pct) >= scalp_profit_arm_roi_pct
            ):
                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][SCALP] exit trigger | symbol=%s side=%s profile=%s reason=%s price=%.8f entry=%.8f pnl_pct=%.6f best_pnl_pct=%.6f",
                            symbol,
                            side,
                            profile,
                            "scalp_reverse_kill_roi",
                            float(price),
                            float(entry_price),
                            float(pnl_pct),
                            float(best_pnl_pct),
                        )
                except Exception:
                    pass
                return "scalp_reverse_kill_roi"

        stalled_for = float(now_ts) - float(last_best_ts or now_ts)
        if (
            float(best_roi_pct) >= scalp_stall_min_profit_roi_pct
            and float(stalled_for) >= scalp_stall_after_profit_sec
        ):
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][SCALP] exit trigger | symbol=%s side=%s profile=%s reason=%s price=%.8f entry=%.8f pnl_pct=%.6f best_pnl_pct=%.6f",
                        symbol,
                        side,
                        profile,
                        "scalp_stall_exit_roi",
                        float(price),
                        float(entry_price),
                        float(pnl_pct),
                        float(best_pnl_pct),
                    )
            except Exception:
                pass
            return "scalp_stall_exit_roi"

        return None

    def _evaluate_scalp_exit(
        self,
        symbol: str,
        pos: Dict[str, Any],
        price: float,
        side: str,
        entry_price: float,
        best_pnl_pct: float,
        highest_price: float,
        lowest_price: float,
        now_ts: float,
        last_best_ts: float,
        reverse_meta_provider=None,
    ) -> Optional[str]:
        return self._evaluate_scalp_exit_pro(
            symbol=symbol,
            pos=pos,
            price=price,
            side=side,
            entry_price=entry_price,
            best_pnl_pct=best_pnl_pct,
            highest_price=highest_price,
            lowest_price=lowest_price,
            now_ts=now_ts,
            last_best_ts=last_best_ts,
            reverse_meta_provider=reverse_meta_provider,
        )
    def _get_latest_signal(self, symbol: str) -> Dict[str, Any]:
        sym = str(symbol).upper().strip()
        if not sym:
            return {}

        r = getattr(self, "redis", None) or getattr(self, "redis_client", None)
        if r is None:
            return {}

        try:
            raw = r.get(f"bot:last_signal:{sym}")
            if not raw:
                return {}

            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")

            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][WEAK] latest signal read failed | symbol=%s",
                        sym,
                    )
            except Exception:
                pass
            return {}


    def _get_exchange_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        sym = str(symbol).upper().strip()
        if not sym:
            return None

        try:
            rows = self._get_exchange_open_positions()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("symbol") or "").upper().strip() == sym:
                    return row
        except Exception as e:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][EXCHANGE-POS] fetch skipped | symbol=%s err=%s",
                        sym,
                        str(e)[:300],
                    )
            except Exception:
                pass

        return None
    def _get_effective_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        sym = str(symbol).upper().strip()
        if not sym:
            return None

        local_pos = self._get_position(sym)
        if isinstance(local_pos, dict):
            try:
                side = str(local_pos.get("side") or "").strip().lower()
                qty = float(local_pos.get("qty") or 0.0)
                if side in ("long", "short") and qty > 0:
                    return local_pos
            except Exception:
                pass

        ex_pos = self._get_exchange_position(sym)
        if isinstance(ex_pos, dict):
            return ex_pos

        return None

    def _set_position(self, symbol: str, pos: Dict[str, Any]) -> None:
        sym = str(symbol).upper()

        try:
            pm = getattr(self, "position_manager", None)
            if pm is not None and hasattr(pm, "set_position"):
                pm.set_position(sym, pos)
                return
        except Exception:
            pass

        try:
            if self.redis is not None:
                self.redis.set(self._pos_key(sym), json.dumps(pos, ensure_ascii=False, default=str))
        except Exception:
            pass

    def _del_position(self, symbol: str) -> None:
        sym = str(symbol).upper().strip()
        if not sym:
            return

        pm = getattr(self, "position_manager", None)

        # position_manager tarafını olabildiğince temizle
        try:
            if pm is not None:
                for method_name in (
                    "clear_position",
                    "delete_position",
                    "del_position",
                    "remove_position",
                    "close_position_state",
                ):
                    fn = getattr(pm, method_name, None)
                    if callable(fn):
                        try:
                            fn(sym)
                            break
                        except TypeError:
                            try:
                                fn(symbol=sym)
                                break
                            except Exception:
                                pass
        except Exception:
            pass

        # Redis tarafını zorla temizle
        try:
            if self.redis is not None:
                self.redis.delete(self._pos_key(sym))
        except Exception:
            try:
                if self.logger:
                    self.logger.exception("[EXEC][STATE] redis delete failed | symbol=%s", sym)
            except Exception:
                pass

        # doğrulama logu
        try:
            if self.redis is not None:
                still_exists = self.redis.get(self._pos_key(sym))
                if still_exists:
                    if self.logger:
                        self.logger.warning(
                            "[EXEC][STATE] local position delete attempted but key still exists | symbol=%s",
                            sym,
                        )
                else:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][STATE] local position removed | symbol=%s",
                            sym,
                        )
        except Exception:
            pass

    def _finalize_close_state(
        self,
        symbol: str,
        side: str,
        pos: Optional[Dict[str, Any]],
        interval: str,
        realized_pnl: float,
        close_price: float,
        reason: str,
        exchange_pos_after: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        sym = str(symbol).upper().strip()
        pos = pos if isinstance(pos, dict) else {}

        residual_qty = 0.0
        residual_side = str(side or "").strip().lower() or str(pos.get("side") or "").strip().lower()

        if isinstance(exchange_pos_after, dict):
            try:
                residual_qty = abs(float(exchange_pos_after.get("qty") or 0.0))
            except Exception:
                residual_qty = 0.0
            try:
                residual_side = str(exchange_pos_after.get("side") or residual_side).strip().lower() or residual_side
            except Exception:
                pass

        min_qty = 0.0
        min_notional = 0.0
        try:
            s_info = self._get_symbol_info(sym)
            if isinstance(s_info, dict):
                min_qty = float(s_info.get("min_qty") or 0.0)
                min_notional = float(s_info.get("min_notional") or 0.0)
        except Exception:
            min_qty = 0.0
            min_notional = 0.0

        dust_threshold = max(float(min_qty), 0.0)

        result = {
            "symbol": sym,
            "residual_qty": float(residual_qty),
            "residual_side": residual_side,
            "dust_threshold": float(dust_threshold),
            "min_notional": float(min_notional),
            "fully_closed": False,
            "dust_remaining": False,
            "partial_remaining": False,
        }

        if residual_qty <= 0.0:
            self._del_position(sym)
            self._remove_from_bridge_state(sym)

            try:
                chk_local = self._get_position(sym)
                chk_bridge = self._get_bridge_state()
                if self.logger:
                    self.logger.info(
                        "[EXEC][STATE] cleanup after close | symbol=%s local_exists=%s bridge_exists=%s",
                        sym,
                        bool(isinstance(chk_local, dict) and chk_local),
                        bool(isinstance(chk_bridge, dict) and sym in chk_bridge),
                    )
            except Exception:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][STATE] cleanup verify failed | symbol=%s",
                        sym,
                    )

            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][CLOSE] CLOSED | symbol=%s side=%s qty=%.10f close=%.6f realized_pnl=%.6f reason=%s",
                        sym,
                        residual_side or side,
                        float(pos.get("qty") or 0.0),
                        float(close_price),
                        float(realized_pnl),
                        str(reason),
                    )
            except Exception:
                pass

            result["fully_closed"] = True
            return result

        residual_pos = dict(pos) if isinstance(pos, dict) else {}
        residual_pos["symbol"] = sym
        residual_pos["side"] = residual_side
        residual_pos["qty"] = float(residual_qty)

        if isinstance(exchange_pos_after, dict):
            try:
                residual_pos["entry_price"] = float(
                    exchange_pos_after.get("entry_price")
                    or residual_pos.get("entry_price")
                    or 0.0
                )
            except Exception:
                pass

        self._set_position(sym, residual_pos)
        self._upsert_bridge_state_on_open(
            symbol=sym,
            side=residual_side,
            interval=str(interval or residual_pos.get("interval") or "1m"),
            intent_id="",
        )

        if dust_threshold > 0.0 and residual_qty <= dust_threshold:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][CLOSE] residual dust remains on exchange | symbol=%s side=%s residual_qty=%.10f dust_threshold=%.10f",
                        sym,
                        residual_side,
                        float(residual_qty),
                        float(dust_threshold),
                    )
            except Exception:
                pass

            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][STATE] partial close state updated | symbol=%s residual_qty=%.10f",
                        sym,
                        float(residual_qty),
                    )
            except Exception:
                pass

            result["dust_remaining"] = True
            return result

        try:
            if self.logger:
                self.logger.warning(
                    "[EXEC][CLOSE] residual position remains on exchange | symbol=%s side=%s residual_qty=%.10f",
                    sym,
                    residual_side,
                    float(residual_qty),
                )
        except Exception:
            pass

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][STATE] partial close state updated | symbol=%s residual_qty=%.10f",
                    sym,
                    float(residual_qty),
                )
        except Exception:
            pass

        result["partial_remaining"] = True
        return result

    def _remove_from_bridge_state(self, symbol: str) -> None:
        sym = str(symbol).upper().strip()
        if not sym or self.redis is None:
            return

        key = str(os.getenv("BRIDGE_STATE_KEY", "open_positions_state")).strip() or "open_positions_state"

        try:
            raw = self.redis.get(key)
            if not raw:
                if self.logger:
                    self.logger.info(
                        "[EXEC][STATE] bridge state already empty | key=%s symbol=%s",
                        key,
                        sym,
                    )
                return

            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")

            obj = json.loads(raw)
            if not isinstance(obj, dict):
                if self.logger:
                    self.logger.warning(
                        "[EXEC][STATE] bridge state invalid json object | key=%s symbol=%s",
                        key,
                        sym,
                    )
                return

            existed = sym in obj
            if existed:
                del obj[sym]
                self.redis.set(key, json.dumps(obj, ensure_ascii=False, default=str))

            # doğrulama
            raw2 = self.redis.get(key)
            ok_removed = True
            if raw2:
                if isinstance(raw2, (bytes, bytearray)):
                    raw2 = raw2.decode("utf-8", errors="ignore")
                obj2 = json.loads(raw2)
                if isinstance(obj2, dict) and sym in obj2:
                    ok_removed = False

            if self.logger:
                if existed and ok_removed:
                    self.logger.info(
                        "[EXEC][STATE] removed from bridge state | key=%s symbol=%s",
                        key,
                        sym,
                    )
                elif existed and not ok_removed:
                    self.logger.warning(
                        "[EXEC][STATE] bridge state delete attempted but symbol still exists | key=%s symbol=%s",
                        key,
                        sym,
                    )
                else:
                    self.logger.info(
                        "[EXEC][STATE] bridge state symbol already absent | key=%s symbol=%s",
                        key,
                        sym,
                    )
        except Exception:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][STATE] remove from bridge state failed | key=%s symbol=%s",
                        key,
                        sym,
                    )
            except Exception:
                pass

    def _get_bridge_state(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        key = str(os.getenv("BRIDGE_STATE_KEY", "open_positions_state")).strip() or "open_positions_state"

        try:
            r = getattr(self, "redis", None)
            if r is None:
                r = getattr(self, "redis_client", None)

            if r is None:
                return {}

            raw = r.get(key)
            if not raw:
                return {}

            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")

            obj = json.loads(raw)
            if not isinstance(obj, dict):
                return {}

            if symbol is None:
                return obj

            sym = str(symbol).upper().strip()
            if not sym:
                return {}

            st = obj.get(sym)
            return st if isinstance(st, dict) else {}

        except Exception:
            try:
                if self.logger:
                    if symbol is None:
                        self.logger.exception(
                            "[EXEC][STATE] get bridge state failed | key=%s",
                            key,
                        )
                    else:
                        self.logger.exception(
                            "[EXEC][STATE] bridge state read failed | symbol=%s key=%s",
                            str(symbol).upper().strip(),
                            key,
                        )
            except Exception:
                pass
            return {}

    def _upsert_bridge_state_on_open(
        self,
        symbol: str,
        side: str,
        interval: str,
        intent_id: str = "",
    ) -> None:
        sym = str(symbol).upper().strip()
        side_n = str(side or "").lower().strip()

        try:
            interval_n = str(os.getenv("INTERVAL", "1m")).strip() or "1m"
        except Exception:
            interval_n = "1m"

        if not sym or self.redis is None:
            return

        key = str(os.getenv("BRIDGE_STATE_KEY", "open_positions_state")).strip() or "open_positions_state"

        try:
            raw = self.redis.get(key)
            obj: Dict[str, Any] = {}

            if raw:
                if isinstance(raw, (bytes, bytearray)):
                    raw = raw.decode("utf-8", errors="ignore")
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        obj = parsed
                except Exception:
                    obj = {}

            obj[sym] = {
                "side": side_n,
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "intent_id": str(intent_id or "").strip(),
                "interval": interval_n,
                "expires_at": float(time.time()) + float(12 * 3600),
            }

            self.redis.set(
                key,
                json.dumps(obj, ensure_ascii=False, default=str),
            )

            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][STATE] bridge state upserted | key=%s symbol=%s side=%s interval=%s intent_id=%s",
                        key,
                        sym,
                        side_n,
                        interval_n,
                        str(intent_id or "").strip(),
                    )
            except Exception:
                pass

        except Exception:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][STATE] bridge state upsert failed | symbol=%s",
                        sym,
                    )
            except Exception:
                pass

    def sync_positions_with_exchange(self) -> Dict[str, Any]:
        summary = {
            "exchange_open": 0,
            "local_open": 0,
            "bridge_open": 0,
            "removed_local": [],
            "removed_bridge": [],
            "added_local": [],
            "added_bridge": [],
            "kept": [],
            "skipped_fresh_local": [],
            "skipped_fresh_bridge": [],
        }

        if not self.position_sync_enabled:
            return summary

        now_ts = time.time()

        def _state_ts(obj: Any) -> float:
            if not isinstance(obj, dict):
                return 0.0

            for key in ("sync_grace_until", "bridge_written_ts", "created_ts", "last_best_ts", "expires_at"):
                try:
                    v = float(obj.get(key) or 0.0)
                    if v > 0:
                        return v
                except Exception:
                    pass

            try:
                ts_utc = str(obj.get("ts_utc") or "").strip()
                if ts_utc:
                    return datetime.fromisoformat(ts_utc.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass

            try:
                opened_at = str(obj.get("opened_at") or "").strip()
                if opened_at:
                    return datetime.fromisoformat(opened_at.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass

            return 0.0

        def _fresh(obj: Any, grace_sec: float = 45.0) -> bool:
            ts = _state_ts(obj)
            if ts <= 0:
                return False

            # sync_grace_until absolute timestamp gibi de kullanılabilir
            try:
                sg = float((obj or {}).get("sync_grace_until") or 0.0)
                if sg > now_ts:
                    return True
            except Exception:
                pass

            return (now_ts - ts) < float(grace_sec)

        exchange_map = self._get_exchange_open_positions_map()
        summary["exchange_open"] = len(exchange_map)

        local_map = self._get_all_local_positions()
        summary["local_open"] = len(local_map)

        bridge_all = self._get_bridge_state()
        bridge_all = bridge_all if isinstance(bridge_all, dict) else {}
        summary["bridge_open"] = len(bridge_all)

        try:
            bot_side_mode = str(os.getenv("BOT_SIDE_MODE", "both") or "both").strip().lower()
        except Exception:
            bot_side_mode = "both"

        strict_exchange_truth = bot_side_mode in ("long", "short")

        try:
            if self.logger:
                has_state = bool(summary["exchange_open"] or summary["local_open"] or summary["bridge_open"] )
                log_fn = self.logger.info if has_state else self.logger.debug
                log_fn(
                    "[EXEC][SYNC] start | exchange_open=%s local_open=%s bridge_open=%s",
                    int(summary["exchange_open"]),
                    int(summary["local_open"]),
                    int(summary["bridge_open"]),
                )
        except Exception:
            pass

        # 1) exchange'de var ama local'de yok -> hydrate et
        for sym, ex_pos in exchange_map.items():
            # SIDE-SYNC-FILTER: long bot short'u, short bot long'u sahiplenmesin
            try:
                ex_side = str((ex_pos or {}).get("side") or "").strip().lower()
            except Exception:
                ex_side = ""

            try:
                bot_side_mode = str(os.getenv("BOT_SIDE_MODE", os.getenv("SIDE_MODE", "both")) or "both").strip().lower()
            except Exception:
                bot_side_mode = "both"

            if bot_side_mode == "long" and ex_side == "short":
                try:
                    if self.logger:
                        self.logger.info("[EXEC][SYNC][SIDE-SKIP] symbol=%s ex_side=%s bot_side=%s", str(sym).upper(), ex_side, bot_side_mode)
                except Exception:
                    pass
                continue

            if bot_side_mode == "short" and ex_side == "long":
                try:
                    if self.logger:
                        self.logger.info("[EXEC][SYNC][SIDE-SKIP] symbol=%s ex_side=%s bot_side=%s", str(sym).upper(), ex_side, bot_side_mode)
                except Exception:
                    pass
                continue

            if sym in local_map:
                # =============================================
                # EXCHANGE TRUTH RECONCILIATION
                #
                # Local state mevcut olsa bile exchange
                # entry/qty gerçeğini kontrol et.
                #
                # Özellikle MARKET open sırasında exchange
                # fill metrics geçici olarak alınamazsa local
                # entry "requested/order_price" fallback ile
                # oluşabilir.
                # =============================================
                try:
                    local_pos = local_map.get(sym)

                    if not isinstance(local_pos, dict):
                        summary["kept"].append(sym)
                        continue

                    local_side = str(
                        local_pos.get("side") or ""
                    ).strip().lower()

                    exchange_side = str(
                        ex_pos.get("side") or ""
                    ).strip().lower()

                    try:
                        local_entry = float(
                            local_pos.get("entry_price")
                            or 0.0
                        )
                    except Exception:
                        local_entry = 0.0

                    try:
                        exchange_entry = float(
                            ex_pos.get("entry_price")
                            or 0.0
                        )
                    except Exception:
                        exchange_entry = 0.0

                    try:
                        exchange_qty = abs(
                            float(
                                ex_pos.get("qty")
                                or 0.0
                            )
                        )
                    except Exception:
                        exchange_qty = 0.0

                    try:
                        local_qty = abs(
                            float(
                                local_pos.get("qty")
                                or 0.0
                            )
                        )
                    except Exception:
                        local_qty = 0.0

                    side_match = (
                        local_side in ("long", "short")
                        and exchange_side == local_side
                    )

                    entry_diff_pct = 0.0

                    if (
                        local_entry > 0
                        and exchange_entry > 0
                    ):
                        entry_diff_pct = abs(
                            exchange_entry - local_entry
                        ) / max(
                            abs(exchange_entry),
                            1e-12,
                        )

                    # Binance rounding/noise yüzünden çok küçük
                    # farklarda lifecycle state'i rebase etme.
                    entry_changed = (
                        side_match
                        and exchange_entry > 0
                        and (
                            local_entry <= 0
                            or entry_diff_pct > 1e-7
                        )
                    )

                    qty_changed = (
                        side_match
                        and exchange_qty > 0
                        and abs(
                            exchange_qty - local_qty
                        ) > 1e-12
                    )

                    if entry_changed or qty_changed:
                        reconciled = dict(local_pos)

                        if entry_changed:
                            reconciled[
                                "entry_price"
                            ] = float(exchange_entry)

                            reconciled[
                                "notional"
                            ] = float(
                                (
                                    exchange_qty
                                    if exchange_qty > 0
                                    else local_qty
                                )
                                * exchange_entry
                            )

                            # Entry-dependent lifecycle state
                            # yeni exchange truth'a göre yeniden
                            # oluşturulacak.
                            reconciled["sl_price"] = 0.0
                            reconciled["tp_price"] = 0.0

                            reconciled[
                                "best_pnl_pct"
                            ] = 0.0
                            reconciled[
                                "best_roi_pct"
                            ] = 0.0
                            reconciled[
                                "best_roi"
                            ] = 0.0

                            reconciled[
                                "highest_price"
                            ] = float(exchange_entry)
                            reconciled[
                                "lowest_price"
                            ] = float(exchange_entry)

                            reconciled[
                                "last_best_ts"
                            ] = float(now_ts)

                            reconciled[
                                "tp_runner_armed"
                            ] = False
                            reconciled[
                                "tp_runner_armed_ts"
                            ] = 0.0
                            reconciled[
                                "trailing_armed"
                            ] = False
                            reconciled[
                                "trail_stop_price"
                            ] = 0.0

                        if qty_changed:
                            reconciled["qty"] = float(
                                exchange_qty
                            )

                            if exchange_entry > 0:
                                reconciled[
                                    "notional"
                                ] = float(
                                    exchange_qty
                                    * exchange_entry
                                )

                        meta = reconciled.get("meta")

                        if not isinstance(meta, dict):
                            meta = {}

                        extra_meta = meta.get("extra")

                        if not isinstance(
                            extra_meta,
                            dict,
                        ):
                            extra_meta = {}

                        extra_meta[
                            "exchange_entry_reconciled"
                        ] = bool(entry_changed)

                        extra_meta[
                            "exchange_qty_reconciled"
                        ] = bool(qty_changed)

                        extra_meta[
                            "exchange_reconciled_ts"
                        ] = float(now_ts)

                        meta["extra"] = extra_meta
                        reconciled["meta"] = meta

                        self._set_position(
                            sym,
                            reconciled,
                        )

                        local_map[sym] = reconciled

                        if entry_changed:
                            try:
                                if self.redis is not None:
                                    self.redis.delete(
                                        "fixed_roi_best:"
                                        + str(sym).upper().strip()
                                    )
                            except Exception:
                                pass

                        try:
                            if self.logger:
                                self.logger.info(
                                    "[EXEC][SYNC][RECONCILE] "
                                    "symbol=%s side=%s "
                                    "entry_old=%.10f entry_new=%.10f "
                                    "entry_diff_pct=%.8f "
                                    "qty_old=%.10f qty_new=%.10f "
                                    "entry_changed=%s qty_changed=%s",
                                    sym,
                                    local_side,
                                    float(local_entry),
                                    float(exchange_entry),
                                    float(entry_diff_pct),
                                    float(local_qty),
                                    float(exchange_qty),
                                    bool(entry_changed),
                                    bool(qty_changed),
                                )
                        except Exception:
                            pass

                    summary["kept"].append(sym)

                except Exception as e:
                    try:
                        if self.logger:
                            self.logger.exception(
                                "[EXEC][SYNC][RECONCILE] "
                                "failed | symbol=%s err=%s",
                                sym,
                                str(e),
                            )
                    except Exception:
                        pass

                    summary["kept"].append(sym)

                continue

            try:
                bridge_st = bridge_all.get(sym, {}) if isinstance(bridge_all, dict) else {}

                hydrated = {
                    "symbol": sym,
                    "side": str(ex_pos.get("side") or "").strip().lower(),
                    "qty": float(ex_pos.get("qty") or 0.0),
                    "entry_price": float(ex_pos.get("entry_price") or 0.0),
                    "notional": float(ex_pos.get("notional") or 0.0),
                    "interval": str(bridge_st.get("interval") or "1m").strip() or "1m",
                    "opened_at": datetime.now(timezone.utc).isoformat(),

                    # >>> NEW
                    "created_ts": float(now_ts),
                    "bridge_written_ts": float(now_ts),
                    "sync_grace_until": float(now_ts + 45.0),
                    # <<< NEW

                    "sl_price": 0.0,
                    "tp_price": 0.0,
                    "trailing_pct": float(getattr(self, "default_trailing_pct", 0.03) or 0.03),
                    "stall_ttl_sec": int(self.default_stall_ttl_sec),
                    "best_pnl_pct": 0.0,
                    "last_best_ts": float(now_ts),
                    "atr_value": 0.0,
                    "highest_price": float(ex_pos.get("entry_price") or 0.0),
                    "lowest_price": float(ex_pos.get("entry_price") or 0.0),
                    "meta": {
                        "probs": {},
                        "extra": {
                            "hydrated_from_exchange": True,
                            "bridge_state": bridge_st,
                        },
                    },
                }

                self._set_position(sym, hydrated)
                self._upsert_bridge_state_on_open(
                    symbol=sym,
                    side=str(hydrated.get("side") or ""),
                    interval=str(hydrated.get("interval") or "1m"),
                    intent_id=str(bridge_st.get("intent_id") or ""),
                )

                summary["added_local"].append(sym)
                summary["added_bridge"].append(sym)

                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][SYNC] hydrated missing local position from exchange | symbol=%s side=%s qty=%.10f entry=%.10f interval=%s",
                            sym,
                            str(hydrated.get("side") or ""),
                            float(hydrated.get("qty") or 0.0),
                            float(hydrated.get("entry_price") or 0.0),
                            str(hydrated.get("interval") or ""),
                        )
                except Exception:
                    pass

            except Exception:
                try:
                    if self.logger:
                        self.logger.exception("[EXEC][SYNC] hydrate failed | symbol=%s", sym)
                except Exception:
                    pass

        # local map'i refresh et
        refreshed_local_map = self._get_all_local_positions()
        refreshed_bridge_all = self._get_bridge_state()
        refreshed_bridge_all = refreshed_bridge_all if isinstance(refreshed_bridge_all, dict) else {}

        # 2) local'de var ama exchange'de yok
        # strict_exchange_truth aktifse fresh olsa bile local phantom state tutulmaz
        for sym, pos in refreshed_local_map.items():
            if sym not in exchange_map:
                is_fresh_local = _fresh(pos, grace_sec=90.0)

                if is_fresh_local and not strict_exchange_truth:
                    summary["skipped_fresh_local"].append(sym)
                    try:
                        if self.logger:
                            self.logger.info(
                                "[EXEC][SYNC] skip fresh local-only state | symbol=%s",
                                sym,
                            )
                    except Exception:
                        pass
                    continue

                try:
                    if self.position_sync_remove_orphans:
                        self._del_position(sym)
                        summary["removed_local"].append(sym)

                        try:
                            if self.logger:
                                self.logger.info(
                                    "[EXEC][SYNC] removed orphan local position | symbol=%s fresh=%s strict_exchange_truth=%s",
                                    sym,
                                    bool(is_fresh_local),
                                    bool(strict_exchange_truth),
                                )
                        except Exception:
                            pass

                    if sym in refreshed_bridge_all and not _fresh(refreshed_bridge_all.get(sym, {}), grace_sec=45.0):
                        self._remove_from_bridge_state(sym)
                        summary["removed_bridge"].append(sym)

                except Exception:
                    try:
                        if self.logger:
                            self.logger.exception(
                                "[EXEC][SYNC] failed removing orphan state | symbol=%s",
                                sym,
                            )
                    except Exception:
                        pass
            else:
                if sym not in summary["kept"]:
                    summary["kept"].append(sym)

        # 3) bridge'de var ama ne exchange'de ne local'de yok -> fresh ise dokunma
        final_local_map = self._get_all_local_positions()
        final_bridge_all = self._get_bridge_state()
        final_bridge_all = final_bridge_all if isinstance(final_bridge_all, dict) else {}

        for sym, bst in final_bridge_all.items():
            if sym not in exchange_map and sym not in final_local_map:
                try:
                    created_ts = float(bst.get("created_ts") or 0.0)
                except Exception:
                    created_ts = 0.0

                if created_ts > 0 and (time.time() - created_ts) < 5.0:
                    summary["skipped_fresh_bridge"].append(sym)
                    try:
                        if self.logger:
                            self.logger.info(
                                "[EXEC][SYNC] skip very-fresh bridge-only state | symbol=%s",
                                sym,
                            )
                    except Exception:
                        pass
                    continue

                final_local_map[sym] = bst
                summary["added_local"].append(sym)
                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][SYNC] promote bridge-only state to local | symbol=%s",
                            sym,
                        )
                except Exception:
                    pass
                try:
                    self._remove_from_bridge_state(sym)
                    summary["removed_bridge"].append(sym)
                    try:
                        if self.logger:
                            self.logger.info(
                                "[EXEC][SYNC] removed stale bridge-only state | symbol=%s",
                                sym,
                            )
                    except Exception:
                        pass
                except Exception:
                    try:
                        if self.logger:
                            self.logger.exception(
                                "[EXEC][SYNC] failed removing stale bridge-only state | symbol=%s",
                                sym,
                            )
                    except Exception:
                        pass

        try:
            # summary değerlerini tekrar hesapla ki "done" logu güncel durumu göstersin
            summary["exchange_open"] = len(self._get_exchange_open_positions_map())
            summary["local_open"] = len(self._get_all_local_positions())
            _bridge_now = self._get_bridge_state()
            _bridge_now = _bridge_now if isinstance(_bridge_now, dict) else {}
            summary["bridge_open"] = len(_bridge_now)
        except Exception:
            pass

        try:
            self._last_position_sync_ts = float(time.time())
        except Exception:
            pass

        try:
            if self.logger:
                has_activity = bool(
                    summary["exchange_open"] or summary["local_open"] or summary["bridge_open"]
                    or summary["removed_local"] or summary["removed_bridge"]
                    or summary["added_local"] or summary["added_bridge"]
                    or summary["kept"] or summary["skipped_fresh_local"]
                    or summary["skipped_fresh_bridge"]
                )
                log_fn = self.logger.info if has_activity else self.logger.debug
                log_fn(
                    "[EXEC][SYNC] done | exchange_open=%s local_open=%s bridge_open=%s removed_local=%s removed_bridge=%s added_local=%s added_bridge=%s kept=%s skipped_fresh_local=%s skipped_fresh_bridge=%s",
                    int(summary["exchange_open"]),
                    int(summary["local_open"]),
                    int(summary["bridge_open"]),
                    summary["removed_local"],
                    summary["removed_bridge"],
                    summary["added_local"],
                    summary["added_bridge"],
                    summary["kept"],
                    summary["skipped_fresh_local"],
                    summary["skipped_fresh_bridge"],
                )
        except Exception:
            pass

        return summary

    async def _position_sync_loop(self) -> None:
        while True:
            try:
                self.sync_positions_with_exchange()
            except Exception:
                try:
                    if self.logger:
                        self.logger.exception("[EXEC][SYNC] periodic sync failed")
                except Exception:
                    pass

            try:
                await asyncio.sleep(max(30, int(self.position_sync_interval_sec)))
            except Exception:
                await asyncio.sleep(300)

    def _execute_lifecycle_close(
        self,
        *,
        symbol: str,
        price: float,
        reason: str,
        interval: str,
        side: str = "",
        entry_price: float = 0.0,
        pnl_pct: float = 0.0,
    ) -> bool:
        sym_u = str(symbol or "").upper().strip()
        reason0 = str(reason or "").strip()

        if not sym_u or not reason0:
            return False

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][LIFECYCLE][CLOSE-TRIGGER] "
                    "symbol=%s side=%s reason=%s "
                    "price=%.6f entry=%.6f pnl_pct=%.6f",
                    sym_u,
                    str(side or ""),
                    reason0,
                    float(price),
                    float(entry_price or 0.0),
                    float(pnl_pct or 0.0),
                )
        except Exception:
            pass

        try:
            close_result = self.close_position(
                symbol=sym_u,
                price=float(price),
                reason=reason0,
                interval=str(interval or ""),
            )

            if not isinstance(close_result, dict):
                try:
                    if self.logger:
                        self.logger.warning(
                            "[EXEC][LIFECYCLE][CLOSE-NOT-CONFIRMED] "
                            "symbol=%s reason=%s result=%s",
                            sym_u,
                            reason0,
                            str(close_result),
                        )
                except Exception:
                    pass

                return False

            # Başka bir close zaten devam ediyorsa yeni fiziksel
            # emir göndermedik. Current cycle güvenli biçimde
            # durabilir; inflight close exchange sonucunu yönetecek.
            if bool(close_result.get("close_inflight")):
                return True

            # Outcome telemetry tek otorite olarak close_position()
            # gateway'inde üretilir.
            return True

        except Exception:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][LIFECYCLE][CLOSE-FAIL] "
                        "symbol=%s reason=%s",
                        sym_u,
                        reason0,
                    )
            except Exception:
                pass

            return False


    def _evaluate_lifecycle_roi_exit(
        self,
        *,
        symbol: str,
        pos: Dict[str, Any],
        price: float,
    ) -> Optional[str]:
        sym_u = str(symbol or "").upper().strip()

        if not sym_u or not isinstance(pos, dict):
            return None

        side = str(pos.get("side") or "").strip().lower()

        try:
            entry_price = float(pos.get("entry_price") or 0.0)
            px = float(price)
        except Exception:
            return None

        if (
            side not in ("long", "short")
            or entry_price <= 0
            or px <= 0
        ):
            return None

        lev = float(self._resolve_position_leverage(pos))

        if side == "long":
            pnl_pct = (
                (px - entry_price)
                / max(entry_price, 1e-12)
            )
        else:
            pnl_pct = (
                (entry_price - px)
                / max(entry_price, 1e-12)
            )

        roi_pct = float(pnl_pct) * float(lev)

        try:
            old_best_roi = float(
                pos.get("best_roi_pct")
                or pos.get("best_roi")
                or 0.0
            )
        except Exception:
            old_best_roi = 0.0

        fixed_roi_best_key = (
            "fixed_roi_best:"
            + sym_u
        )

        try:
            if self.redis is not None:
                redis_best = self.redis.get(
                    fixed_roi_best_key
                )

                if redis_best is not None:
                    old_best_roi = max(
                        float(old_best_roi),
                        float(redis_best),
                    )
        except Exception:
            pass

        best_roi_pct = max(
            float(old_best_roi),
            float(roi_pct),
            0.0,
        )

        try:
            if self.redis is not None:
                self.redis.set(
                    fixed_roi_best_key,
                    str(float(best_roi_pct)),
                    ex=86400,
                )
        except Exception:
            pass

        try:
            # ROI evaluator yalnız leveraged ROI state'inin
            # sahibidir.
            #
            # best_pnl_pct / last_best_ts / highest_price /
            # lowest_price canonical position lifecycle
            # state tracker tarafından birlikte yönetilir.
            pos["best_roi_pct"] = float(best_roi_pct)
            pos["best_roi"] = float(best_roi_pct)

            self._set_position(sym_u, pos)
        except Exception:
            pass

        try:
            fixed_roi_tp_enable = str(
                os.getenv(
                    "FIXED_ROI_TP_ENABLE",
                    "0",
                )
            ).strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        except Exception:
            fixed_roi_tp_enable = False

        try:
            fixed_roi_tp_pct = float(
                os.getenv(
                    "FIXED_ROI_TP_PCT",
                    "0.0050",
                )
                or 0.0050
            )
        except Exception:
            fixed_roi_tp_pct = 0.0050

        try:
            fixed_roi_tp_giveback = float(
                os.getenv(
                    "FIXED_ROI_TP_GIVEBACK",
                    "0.0010",
                )
                or 0.0010
            )
        except Exception:
            fixed_roi_tp_giveback = 0.0010

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][ROI-LIFECYCLE] "
                    "symbol=%s side=%s roi=%.6f "
                    "best_roi=%.6f tp=%.6f "
                    "giveback=%.6f price=%.6f "
                    "entry=%.6f lev=%.2f",
                    sym_u,
                    side,
                    float(roi_pct),
                    float(best_roi_pct),
                    float(fixed_roi_tp_pct),
                    float(fixed_roi_tp_giveback),
                    float(px),
                    float(entry_price),
                    float(lev),
                )
        except Exception:
            pass

        try:
            roi_hard_stop = float(
                self.roi_hard_stop_pct
            )
        except Exception:
            roi_hard_stop = -1.0

        if float(roi_pct) <= float(roi_hard_stop):
            return "roi_hard_stop_lifecycle"

        direct_tp_hit = (
            fixed_roi_tp_enable
            and float(fixed_roi_tp_giveback) <= 0.0
            and float(roi_pct)
            >= float(fixed_roi_tp_pct)
        )

        giveback_tp_hit = (
            fixed_roi_tp_enable
            and float(fixed_roi_tp_giveback) > 0.0
            and float(best_roi_pct)
            >= float(fixed_roi_tp_pct)
            and float(roi_pct)
            <= (
                float(best_roi_pct)
                - float(fixed_roi_tp_giveback)
            )
        )

        if direct_tp_hit:
            return "fixed_roi_tp_lifecycle"

        if giveback_tp_hit:
            return "fixed_roi_tp_lifecycle_lock"

        return None

    def _run_position_lifecycle_locked(
        self,
        *,
        symbol: str,
        price: float,
        interval: str,
    ) -> bool:
        """
        Canonical locked lifecycle execution.

        Order:
            1. fresh position
            2. ROI lifecycle
            3. general lifecycle
            4. single close executor
        """
        sym_u = str(symbol or "").upper().strip()

        if not sym_u:
            return False

        lock = self._get_lifecycle_symbol_lock(sym_u)

        try:
            acquired = bool(
                lock.acquire(blocking=False)
            )
        except Exception:
            acquired = False

        if not acquired:
            try:
                if self.logger:
                    self.logger.debug(
                        "[EXEC][LIFECYCLE]"
                        "[SKIP-INFLIGHT] symbol=%s",
                        sym_u,
                    )
            except Exception:
                pass

            return False

        try:
            # -----------------------------------------
            # Fresh position under lifecycle lock
            # -----------------------------------------
            pos = self._get_position(sym_u)

            if not isinstance(pos, dict):
                return False

            side = str(
                pos.get("side") or ""
            ).strip().lower()

            qty = float(
                pos.get("qty") or 0.0
            )

            entry_price = float(
                pos.get("entry_price") or 0.0
            )

            if (
                side not in ("long", "short")
                or qty <= 0
                or entry_price <= 0
                or float(price) <= 0
            ):
                return False

            # =========================================
            # PRIORITY 1 — ROI LIFECYCLE
            # =========================================
            roi_reason = self._evaluate_lifecycle_roi_exit(
                symbol=sym_u,
                pos=pos,
                price=float(price),
            )

            if roi_reason is not None:
                return bool(
                    self._execute_lifecycle_close(
                        symbol=sym_u,
                        price=float(price),
                        reason=str(roi_reason),
                        interval=str(interval or ""),
                        side=side,
                        entry_price=float(entry_price),
                    )
                )

            # =========================================
            # PRIORITY 2 — GENERAL LIFECYCLE
            # =========================================
            decision = (
                self._evaluate_position_lifecycle_exit(
                    symbol=sym_u,
                    price=float(price),
                    interval=str(interval or ""),
                )
            )

            if not isinstance(decision, dict):
                return False

            if not bool(
                decision.get("should_close")
            ):
                return False

            return bool(
                self._execute_lifecycle_close(
                    symbol=str(
                        decision.get("symbol")
                        or sym_u
                    ),
                    price=float(
                        decision.get("price")
                        or price
                    ),
                    reason=str(
                        decision.get("reason")
                        or "lifecycle_exit"
                    ),
                    interval=str(
                        decision.get("interval")
                        or interval
                        or ""
                    ),
                    side=str(
                        decision.get("side")
                        or side
                    ),
                    entry_price=float(
                        decision.get("entry_price")
                        or entry_price
                    ),
                    pnl_pct=float(
                        decision.get("pnl_pct")
                        or 0.0
                    ),
                )
            )

        except Exception:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][LIFECYCLE] "
                        "locked evaluation failed | "
                        "symbol=%s",
                        sym_u,
                    )
            except Exception:
                pass

            return False

        finally:
            try:
                lock.release()
            except Exception:
                pass


    async def _position_lifecycle_loop(self) -> None:
        interval_sec = max(
            1,
            int(getattr(self, "position_lifecycle_interval_sec", 15)),
        )

        while True:
            try:
                self._check_lifecycle_freeze()
                # Heartbeat tracks the lifecycle loop itself, not only active positions.
                # This prevents false FREEZE-WARN spam while the portfolio is empty.
                self._mark_lifecycle_heartbeat()

                positions = self._get_all_local_positions()
                self._last_lifecycle_active_count = int(len(positions))

                # Empty portfolio normally relies on the dedicated periodic sync loop.
                # Lifecycle only performs a fallback reconciliation when that sync has
                # been stale for >= 2 intervals (minimum 60s). This avoids duplicate
                # exchange REST work every lifecycle tick while preserving self-heal.
                if not positions and bool(getattr(self, "position_sync_enabled", True)):
                    now_sync = float(time.time())
                    last_sync = float(getattr(self, "_last_position_sync_ts", 0.0) or 0.0)
                    fallback_after = max(60.0, 2.0 * max(30.0, float(getattr(self, "position_sync_interval_sec", 30) or 30)))
                    if last_sync <= 0.0 or (now_sync - last_sync) >= fallback_after:
                        try:
                            sync_summary = self.sync_positions_with_exchange()
                            positions = self._get_all_local_positions()
                            if self.logger:
                                log_fn = self.logger.info if positions else self.logger.debug
                                log_fn(
                                    "[EXEC][LIFECYCLE] fallback sync refresh | positions=%s summary=%s",
                                    len(positions),
                                    sync_summary,
                                )
                        except Exception as e:
                            try:
                                if self.logger:
                                    self.logger.exception(
                                        "[EXEC][LIFECYCLE] fallback sync-on-empty failed | err=%s",
                                        str(e),
                                    )
                            except Exception:
                                pass

                try:
                    if self.logger:
                        log_fn = self.logger.info if positions else self.logger.debug
                        log_fn(
                            "[EXEC][LIFECYCLE] tick | positions=%s symbols=%s",
                            len(positions),
                            list(positions.keys()),
                        )
                except Exception:
                    pass

                for sym, pos in positions.items():
                    try:
                        sym_u = str(sym).upper().strip()
                        self._mark_lifecycle_heartbeat(sym_u)

                        side = str(pos.get("side") or "").strip().lower()
                        qty = float(pos.get("qty") or 0.0)
                        interval = str(os.getenv("INTERVAL", "3m")).strip() or "3m"
                        entry_price = float(pos.get("entry_price") or 0.0)

                        if side not in ("long", "short") or qty <= 0 or entry_price <= 0:
                            try:
                                if self.logger:
                                    self.logger.info(
                                        "[EXEC][LIFECYCLE] skip invalid position | symbol=%s side=%s qty=%.10f entry=%.6f",
                                        sym_u,
                                        side,
                                        qty,
                                        entry_price,
                                    )
                            except Exception:
                                pass
                            continue

                        px = None
                        price_source = ""

                        try:
                            px = self._resolve_price(symbol=sym_u)
                            if px is not None and px > 0:
                                price_source = "cache"
                        except Exception:
                            px = None

                        if px is None or px <= 0:
                            try:
                                client = getattr(self, "client", None)

                                fn = (
                                    getattr(client, "futures_mark_price", None)
                                    if client is not None
                                    else None
                                )

                                if callable(fn):
                                    mp = fn(symbol=sym_u)

                                    if isinstance(mp, dict):
                                        px = self._clip_float(
                                            mp.get("markPrice"),
                                            None,
                                        )

                                        if px is not None and px > 0:
                                            price_source = "mark_price"
                            except Exception:
                                px = None

                        if px is None or px <= 0:
                            try:
                                if self.logger:
                                    self.logger.info(
                                        "[EXEC][LIFECYCLE] skip no price | symbol=%s side=%s qty=%.10f interval=%s entry=%.6f",
                                        sym_u,
                                        side,
                                        qty,
                                        interval,
                                        entry_price,
                                    )
                            except Exception:
                                pass
                            continue

                        try:
                            if self.logger:
                                self.logger.info(
                                    "[EXEC][LIFECYCLE] check | symbol=%s side=%s qty=%.10f entry=%.6f price=%.6f interval=%s src=%s",
                                    sym_u,
                                    side,
                                    qty,
                                    entry_price,
                                    float(px),
                                    interval,
                                    price_source or "-",
                                )
                        except Exception:
                            pass

                        self._run_position_lifecycle_locked(
                            symbol=sym_u,
                            price=float(px),
                            interval=str(interval or ""),
                        )


                    except Exception as e:
                        try:
                            if self.logger:
                                self.logger.exception(
                                    "[EXEC][LIFECYCLE] CRASH(symbol) | symbol=%s err=%s",
                                    str(sym),
                                    str(e),
                                )
                        except Exception:
                            pass
                        continue

            except Exception as e:
                try:
                    if self.logger:
                        self.logger.exception(
                            "[EXEC][LIFECYCLE] CRASH(loop) | err=%s",
                            str(e),
                        )
                except Exception:
                    pass

                await asyncio.sleep(1)

            try:
                await asyncio.sleep(interval_sec)
            except Exception:
                await asyncio.sleep(1)

    def _get_exchange_residual_qty(self, symbol: str, side: str) -> float:
        sym = str(symbol).upper().strip()
        side0 = str(side or "").strip().lower()

        if side0 not in ("long", "short"):
            return 0.0

        ex_pos = self._get_exchange_position(sym)
        if not isinstance(ex_pos, dict):
            return 0.0

        ex_side = str(ex_pos.get("side") or "").strip().lower()
        ex_qty = float(ex_pos.get("qty") or 0.0)

        if ex_side != side0:
            return 0.0

        return float(ex_qty)
    def _iter_local_positions(self) -> List[Tuple[str, Dict[str, Any]]]:
        out: List[Tuple[str, Dict[str, Any]]] = []
        try:
            mp = self._get_all_local_positions()
            for sym, pos in mp.items():
                if isinstance(pos, dict):
                    out.append((str(sym).upper().strip(), pos))
        except Exception:
            pass
        return out

    @staticmethod
    def _calc_pnl_pct(side: str, entry_price: float, current_price: float) -> float:
        ep = float(entry_price or 0.0)
        cp = float(current_price or 0.0)
        if ep <= 0 or cp <= 0:
            return 0.0
        s = str(side or "").strip().lower()
        if s == "long":
            return (cp / ep) - 1.0
        if s == "short":
            return (ep / cp) - 1.0
        return 0.0



    # ---------------------------------------------------------
    # position dict / pnl / notify
    # ---------------------------------------------------------
    def _create_position_dict(
        self,
        signal: str,
        symbol: str,
        price: float,
        qty: float,
        notional: float,
        interval: str,
        probs: Dict[str, float],
        extra: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        opened_at = self._utc_now_iso()
        now_ts = time.time()

        trail_pct = self._clip_float(extra.get("trail_pct"), 0.03) or 0.03
        stall_ttl = int(
            extra.get("stall_ttl_sec")
            or self.default_stall_ttl_sec
        )

        sl_price = 0.0
        tp_price = 0.0
        atr_value = 0.0
        bias = self._whale_bias(str(signal), extra)
        sl_mult_adj = 1.0
        tp_mult_adj = 1.0

        try:
            ema7_v = float(extra.get("ema7") or extra.get("ema_fast") or 0.0)
        except Exception:
            ema7_v = 0.0

        try:
            ema25_v = float(extra.get("ema25") or extra.get("ema_slow") or 0.0)
        except Exception:
            ema25_v = 0.0

        try:
            ema99_v = float(extra.get("ema99") or 0.0)
        except Exception:
            ema99_v = 0.0

        if ema7_v <= 0 or ema25_v <= 0 or ema99_v <= 0:
            try:
                ema_fill = self._backfill_ema_metrics(
                    symbol=str(symbol).upper(),
                    interval=str(interval or "3m"),
                    extra=extra,
                )
            except Exception:
                ema_fill = {}

            ema7_v = float(ema_fill.get("ema7") or ema7_v or 0.0)
            ema25_v = float(ema_fill.get("ema25") or ema25_v or 0.0)
            ema99_v = float(ema_fill.get("ema99") or ema99_v or 0.0)

        pos: Dict[str, Any] = {
            "symbol": str(symbol).upper(),
            "side": str(signal),
            "qty": float(qty),
            "entry_price": float(price),
            "notional": float(notional),
            "interval": str(interval or ""),
            "opened_at": opened_at,
            "sl_price": float(sl_price),
            "tp_price": float(tp_price),
            "trailing_pct": float(trail_pct),
            "stall_ttl_sec": int(stall_ttl),
            "best_pnl_pct": 0.0,
            "last_best_ts": float(now_ts),
            "atr_value": float(atr_value),
            "highest_price": float(price),
            "lowest_price": float(price),

            # ------------------------------
            # PERSIST LEVERAGE STATE
            # ------------------------------
            "target_leverage": int(extra.get("target_leverage") or 0),
            "applied_leverage": int(
                extra.get("applied_leverage")
                or extra.get("target_leverage")
                or 0
            ),
            "leverage": int(
                extra.get("leverage")
                or extra.get("applied_leverage")
                or extra.get("target_leverage")
                or 0
            ),

            # ------------------------------
            # PERSIST EMA STATE
            # ------------------------------
            "ema7": float(ema7_v),
            "ema25": float(ema25_v),
            "ema99": float(ema99_v),
            "ema_fast": float(ema7_v),
            "ema_slow": float(ema25_v),

            "meta": {
                "probs": dict(probs or {}),
                "extra": dict(extra or {}),
                "whale_bias_on_open": str(bias),
                "sl_mult_adj": float(sl_mult_adj),
                "tp_mult_adj": float(tp_mult_adj),
            },
        }
        return pos, opened_at

    @staticmethod

    def _calc_pnl(side: str, entry_price: float, exit_price: float, qty: float) -> float:
        if qty <= 0:
            return 0.0
        if side == "long":
            return (float(exit_price) - float(entry_price)) * float(qty)
        if side == "short":
            return (float(entry_price) - float(exit_price)) * float(qty)
        return 0.0

    def _notify_position_open(
        self,
        symbol: str,
        interval: str,
        side: str,
        qty: float,
        price: float,
        extra: Dict[str, Any],
    ) -> None:
        bot = getattr(self, "telegram_bot", None)
        if bot is None:
            return

        text = (
            "🚀 POSITION OPENED\n"
            f"symbol={str(symbol).upper()} side={str(side)} qty={float(qty)}\n"
            f"price={float(price)} interval={str(interval or '')}"
        )

        try:
            fn = getattr(bot, "send_message", None)
            if callable(fn):
                out = fn(text)
                self._fire_and_forget(out, label="tg_open")
        except Exception:
            pass

    def _notify_position_close(
        self,
        symbol: str,
        interval: str,
        side: str,
        qty: float,
        price: float,
        realized_pnl: float,
        daily_realized_pnl: float,
    ) -> None:
        bot = getattr(self, "telegram_bot", None)
        if bot is None:
            return

        text = (
            "✅ POSITION CLOSED\n"
            f"symbol={str(symbol).upper()} side={str(side)} qty={float(qty)}\n"
            f"price={float(price)} interval={str(interval or '')}\n"
            f"realized_pnl={float(realized_pnl):.4f} daily_realized_pnl={float(daily_realized_pnl):.4f}"
        )

        try:
            fn = getattr(bot, "send_message", None)
            if callable(fn):
                out = fn(text)
                self._fire_and_forget(out, label="tg_close")
        except Exception:
            pass

    # ---------------------------------------------------------
    # verify / poll
    # ---------------------------------------------------------
    def _verify_position_sync(
        self,
        symbol: str,
        side: Optional[str] = None,
    ) -> Dict[str, Any]:
        sym = str(symbol).upper().strip()
        side_norm = str(side or "").strip().lower()

        if side_norm not in ("", "long", "short"):
            return {
                "verify": "skip",
                "symbol": sym,
                "reason": "invalid_side",
            }

        client = getattr(self, "client", None)
        if client is None:
            return {
                "verify": "skip",
                "symbol": sym,
                "reason": "client_none",
            }

        try:
            rows: Any = None
            fn = getattr(
                client,
                "futures_position_information",
                None,
            )
            if callable(fn):
                try:
                    rows = fn(symbol=sym)
                except Exception:
                    rows = None

            if rows is None:
                rows = _futures_v3_position_risk(sym)

            if not isinstance(rows, list):
                rows = [rows]

            for row in rows:
                if not isinstance(row, dict):
                    continue

                amt = (
                    self._clip_float(
                        row.get("positionAmt"),
                        0.0,
                    )
                    or 0.0
                )

                if abs(float(amt)) <= 0:
                    continue

                position_side = str(
                    row.get("positionSide")
                    or "BOTH"
                ).upper().strip()

                if side_norm == "long":
                    side_match = (
                        position_side == "LONG"
                        or (
                            position_side == "BOTH"
                            and float(amt) > 0
                        )
                    )
                elif side_norm == "short":
                    side_match = (
                        position_side == "SHORT"
                        or (
                            position_side == "BOTH"
                            and float(amt) < 0
                        )
                    )
                else:
                    side_match = True

                if not side_match:
                    continue

                return {
                    "verify": "ok",
                    "symbol": sym,
                    "side": side_norm or None,
                    "positionSide": position_side,
                    "positionAmt": float(amt),
                    "entryPrice": (
                        self._clip_float(
                            row.get("entryPrice"),
                            0.0,
                        )
                        or 0.0
                    ),
                    "unrealized": (
                        self._clip_float(
                            row.get("unRealizedProfit"),
                            0.0,
                        )
                        or 0.0
                    ),
                    "leverage": (
                        self._clip_float(
                            row.get("leverage"),
                            0.0,
                        )
                        or 0.0
                    ),
                }

            return {
                "verify": "ok",
                "symbol": sym,
                "side": side_norm or None,
                "positionAmt": 0.0,
            }

        except Exception as e:
            return {
                "verify": "skip",
                "symbol": sym,
                "side": side_norm or None,
                "reason": "position_verify_failed",
                "err": str(e)[:300],
            }

    def _poll_order_status(
        self,
        symbol: str,
        order_id: Any = None,
        client_order_id: str = "",
        max_wait_s: float = 2.0,
    ) -> Dict[str, Any]:
        if self.dry_run:
            return {"poll": "skip", "reason": "dry_run"}

        sym = str(symbol).upper().strip()
        if not sym:
            return {"poll": "skip", "reason": "empty_symbol"}

        client = getattr(self, "client", None)
        if client is None:
            return {"poll": "skip", "reason": "client_none"}

        fn = getattr(client, "futures_get_order", None)
        if not callable(fn):
            return {"poll": "skip", "reason": "fn_missing"}

        if order_id is None and not str(client_order_id or "").strip():
            return {"poll": "skip", "reason": "no_order_ref"}

        started = time.time()
        t_end = started + max(0.2, float(max_wait_s or 2.0))
        last: Any = None
        last_err = ""

        while time.time() < t_end:
            try:
                payload: Dict[str, Any] = {"symbol": sym}
                if order_id is not None:
                    payload["orderId"] = order_id
                else:
                    payload["origClientOrderId"] = str(client_order_id).strip()

                last = fn(**payload)

                if isinstance(last, dict):
                    status = str(last.get("status", "")).upper().strip()

                    if status in ("FILLED", "CANCELED", "REJECTED", "EXPIRED"):
                        return {
                            "poll": "ok",
                            "result": self._summarize_order(last),
                            "terminal_status": status,
                            "waited_sec": round(time.time() - started, 3),
                        }

                    if status in ("NEW", "PARTIALLY_FILLED", "PENDING_NEW"):
                        time.sleep(0.2)
                        continue

                    # tanınmayan ama dict döndü
                    return {
                        "poll": "ok",
                        "result": self._summarize_order(last),
                        "terminal_status": status or "UNKNOWN",
                        "waited_sec": round(time.time() - started, 3),
                    }

                time.sleep(0.2)

            except Exception as e:
                last_err = str(e)[:300]
                time.sleep(0.2)

        if isinstance(last, dict):
            return {
                "poll": "timeout",
                "result": self._summarize_order(last),
                "terminal_status": str(last.get("status", "")).upper().strip(),
                "waited_sec": round(time.time() - started, 3),
                "err": last_err,
            }

        if last_err:
            return {
                "poll": "error",
                "err": last_err,
                "waited_sec": round(time.time() - started, 3),
            }

        return {
            "poll": "timeout",
            "reason": "no_terminal_status",
            "waited_sec": round(time.time() - started, 3),
        }
    # ---------------------------------------------------------
    # exchange order functions
    # ---------------------------------------------------------
    def _exchange_open_market(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        reduce_only: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        sym = str(symbol).upper()
        extra0 = extra if isinstance(extra, dict) else {}

        if self.dry_run:
            return {
                "status": "dry_run",
                "symbol": sym,
                "side": str(side),
                "qty": float(qty),
                "reduceOnly": bool(reduce_only),
            }

        client = getattr(self, "client", None)
        if client is None:
            raise RuntimeError("client is None (cannot place order)")

        s = str(side or "").strip().lower()
        if s == "long":
            order_side = "BUY"
            side0 = "long"
        elif s == "short":
            order_side = "SELL"
            side0 = "short"
        else:
            raise ValueError(f"bad side={side}")

        try:
            signal_score = float(
                extra0.get("signal_score")
                or extra0.get("score")
                or extra0.get("_score_total_final")
                or extra0.get("_score_selected")
                or extra0.get("score_total")
                or 0.0
            )
        except Exception:
            signal_score = 0.0

        try:
            whale_score = float(extra0.get("whale_score") or 0.0)
        except Exception:
            whale_score = 0.0

        whale_dir = str(extra0.get("whale_dir") or "none").strip().lower()
        if whale_dir in ("buy", "bull", "up"):
            whale_dir = "long"
        elif whale_dir in ("sell", "bear", "down"):
            whale_dir = "short"
        elif whale_dir not in ("long", "short"):
            whale_dir = "none"

        whale_action = str(extra0.get("whale_action") or "").strip().lower()

        raw_q = self._round_qty(float(qty))

        price_for_norm = self._clip_float(price, None)
        if price_for_norm is None or price_for_norm <= 0:
            price_for_norm = self._resolve_price(symbol=sym)

        if price_for_norm is None or price_for_norm <= 0:
            try:
                fn_mp = getattr(client, "futures_mark_price", None)
                if callable(fn_mp):
                    mp = fn_mp(symbol=sym)
                    if isinstance(mp, dict):
                        price_for_norm = self._clip_float(mp.get("markPrice"), None)
            except Exception:
                price_for_norm = None

        if price_for_norm is None or price_for_norm <= 0:
            raise RuntimeError(f"price_for_norm <= 0 for {sym}")

        symbol_info = self._get_symbol_info(sym)
        if not symbol_info:
            raise RuntimeError(f"symbol_info not found for {sym}")

        q, qmeta = self._normalize_order_qty(
            symbol=sym,
            raw_qty=float(raw_q),
            price=float(price_for_norm),
            symbol_info=symbol_info,
        )

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][QTY][NORMALIZE] symbol=%s raw_qty=%.10f norm_qty=%.10f price=%.6f step=%.10f min_qty=%.10f min_notional=%.6f reject=%s",
                    sym,
                    float(raw_q),
                    float(q),
                    float(price_for_norm),
                    float(qmeta.get("step_size", 0.0) or 0.0),
                    float(qmeta.get("min_qty", 0.0) or 0.0),
                    float(qmeta.get("min_notional", 0.0) or 0.0),
                    str(qmeta.get("reject_reason", "") or "-"),
                )
        except Exception:
            pass

        try:
            if self.logger:
                self.logger.info("[EXEC][QTY][DECISION] %s", self._safe_json(qmeta, limit=900))
        except Exception:
            pass

        if q <= 0:
            raise ValueError(
                f"qty invalid after normalization: {self._safe_json(qmeta, limit=900)}"
            )

        position_side = self._side_to_position_side(side0)

        target_leverage = self._resolve_target_leverage(extra0)

        target_leverage = int(
            max(
                1,
                min(
                    int(target_leverage),
                    int(self.max_leverage),
                ),
            )
        )
        applied_leverage = int(target_leverage)

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][ORDER][PREP] symbol=%s side=%s reduce_only=%s signal_score=%.4f whale_score=%.4f whale_dir=%s whale_action=%s lev_target=%s",
                    sym,
                    side0,
                    bool(reduce_only),
                    float(signal_score),
                    float(whale_score),
                    whale_dir,
                    whale_action or "-",
                    int(target_leverage),
                )
        except Exception:
            pass

        try:
            if not reduce_only:
                applied_leverage = self._set_symbol_leverage(
                    sym,
                    int(target_leverage),
                )
            else:
                applied_leverage = int(target_leverage)
        except Exception as e:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][LEV][FAIL] symbol=%s target=%s reduce_only=%s err=%s",
                        sym,
                        int(target_leverage),
                        bool(reduce_only),
                        str(e),
                    )
            except Exception:
                pass
            applied_leverage = int(target_leverage)

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][LEV] symbol=%s side=%s reduce_only=%s target=%s applied=%s positionSide=%s",
                    sym,
                    side0,
                    bool(reduce_only),
                    int(target_leverage),
                    int(applied_leverage),
                    position_side,
                )
        except Exception:
            pass

        tag = "close" if reduce_only else "open"
        client_oid = self._make_client_order_id(sym, tag)

        payload: Dict[str, Any] = {
            "symbol": sym,
            "side": order_side,
            "type": "MARKET",
            "quantity": float(q),
            "newClientOrderId": client_oid,
        }

        if position_side in ("LONG", "SHORT"):
            payload["positionSide"] = position_side

        if reduce_only and not bool(getattr(self, "hedge_mode_enabled", True)):
            payload["reduceOnly"] = True

        used = "futures_create_order"
        t0 = self._now_ms()

        attempts = int(
            os.getenv(
                "ORDER_RETRY_ATTEMPTS",
                "3",
            )
        )

        base_sleep = float(
            os.getenv(
                "ORDER_RETRY_SLEEP_S",
                "0.6",
            )
        )

        try:
            # =========================================
            # FUTURES-ONLY FAIL-CLOSED TRANSPORT
            # =========================================
            fn = getattr(
                client,
                "futures_create_order",
                None,
            )

            if not callable(fn):
                try:
                    if self.logger:
                        self.logger.error(
                            "[EXEC][OPEN-BLOCK] "
                            "futures_create_order unavailable | "
                            "symbol=%s side=%s",
                            sym,
                            side0,
                        )
                except Exception:
                    pass

                raise RuntimeError(
                    "futures_create_order unavailable "
                    f"for futures open: {sym}"
                )

            resp = self._call_with_retry(
                fn,
                payload,
                attempts=attempts,
                base_sleep=base_sleep,
            )
        except Exception as e:
            dt = self._now_ms() - t0
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][ORDER] %s FAIL | fn=%s symbol=%s side=%s qty=%.10f "
                        "reduceOnly=%s lev=%s dt_ms=%d client_oid=%s "
                        "signal_score=%.4f whale_score=%.4f whale_dir=%s payload=%s err=%s",
                        ("CLOSE" if reduce_only else "OPEN"),
                        used,
                        sym,
                        order_side,
                        float(q),
                        bool(reduce_only),
                        int(applied_leverage),
                        int(dt),
                        client_oid,
                        float(signal_score),
                        float(whale_score),
                        whale_dir,
                        self._safe_json(payload, limit=900),
                        str(e)[:300],
                    )
            except Exception:
                pass
            raise

        dt = self._now_ms() - t0

        summ = self._summarize_order(resp)
        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][ORDER] %s OK | fn=%s symbol=%s side=%s qty=%.10f "
                    "reduceOnly=%s lev=%s dt_ms=%d summary=%s",
                    ("CLOSE" if reduce_only else "OPEN"),
                    used,
                    sym,
                    order_side,
                    float(q),
                    bool(reduce_only),
                    int(applied_leverage),
                    int(dt),
                    self._safe_json(summ, limit=900),
                )
        except Exception:
            pass

        response_status = str(
            resp.get("status") or ""
        ).upper().strip() if isinstance(resp, dict) else ""

        if response_status in (
            "CANCELED",
            "REJECTED",
            "EXPIRED",
        ):
            raise RuntimeError(
                f"order response failure: "
                f"symbol={sym} status={response_status}"
            )

        execution_confirmed = response_status == "FILLED"
        confirmation_source = (
            "response"
            if execution_confirmed
            else ""
        )
        position_verify = None

        if self.order_poll_status and not execution_confirmed:
            oid = None
            coid = ""

            if isinstance(resp, dict):
                oid = resp.get("orderId")
                coid = str(
                    resp.get("clientOrderId")
                    or resp.get("newClientOrderId")
                    or client_oid
                    or ""
                )

            pol = self._poll_order_status(
                sym,
                order_id=oid,
                client_order_id=coid,
                max_wait_s=self.order_poll_wait_s,
            )

            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][ORDER][POLL] %s",
                        self._safe_json(pol, limit=900),
                    )
            except Exception:
                pass

            terminal_status = str(
                pol.get("terminal_status") or ""
            ).upper().strip() if isinstance(pol, dict) else ""

            if terminal_status in (
                "CANCELED",
                "REJECTED",
                "EXPIRED",
            ):
                raise RuntimeError(
                    f"order terminal failure: "
                    f"symbol={sym} status={terminal_status}"
                )

            if terminal_status == "FILLED":
                execution_confirmed = True
                confirmation_source = "poll"

                try:
                    if (
                        isinstance(pol, dict)
                        and isinstance(pol.get("result"), dict)
                    ):
                        resp = dict(resp or {})
                        resp["_poll_result"] = dict(
                            pol["result"]
                        )

                        avg_price = self._clip_float(
                            pol["result"].get("avgPrice"),
                            None,
                        )
                        executed_qty = self._clip_float(
                            pol["result"].get("executedQty"),
                            None,
                        )
                        cum_quote = self._clip_float(
                            pol["result"].get("cumQuote"),
                            None,
                        )

                        if (
                            avg_price is not None
                            and float(avg_price) > 0
                        ):
                            resp["avgPrice"] = float(
                                avg_price
                            )

                        if (
                            executed_qty is not None
                            and float(executed_qty) > 0
                        ):
                            resp["executedQty"] = float(
                                executed_qty
                            )

                        if (
                            cum_quote is not None
                            and float(cum_quote) > 0
                        ):
                            resp["cumQuote"] = float(
                                cum_quote
                            )
                except Exception:
                    pass

        if not execution_confirmed:
            position_verify = self._verify_position_sync(
                sym,
                side0,
            )

            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][ORDER][VERIFY-FALLBACK] %s",
                        self._safe_json(
                            position_verify,
                            limit=900,
                        ),
                    )
            except Exception:
                pass

            verified_amt = (
                self._clip_float(
                    position_verify.get("positionAmt"),
                    0.0,
                )
                if isinstance(position_verify, dict)
                else 0.0
            ) or 0.0

            if (
                isinstance(position_verify, dict)
                and position_verify.get("verify") == "ok"
                and abs(float(verified_amt)) > 0
            ):
                execution_confirmed = True
                confirmation_source = "position"

        if not execution_confirmed:
            raise RuntimeError(
                f"order execution unconfirmed: "
                f"symbol={sym} side={side0} "
                f"response_status={response_status or '-'}"
            )

        if self.order_verify_position and position_verify is None:
            try:
                position_verify = self._verify_position_sync(
                    sym,
                    side0,
                )
                if self.logger:
                    self.logger.info(
                        "[EXEC][VERIFY] %s",
                        self._safe_json(
                            position_verify,
                            limit=900,
                        ),
                    )
            except Exception:
                position_verify = None

        if isinstance(resp, dict):
            resp["_execution_confirmed"] = True
            resp["_confirmation_source"] = confirmation_source
            resp["_target_leverage"] = int(
                target_leverage
            )
            resp["_applied_leverage"] = int(
                applied_leverage
            )

            if isinstance(position_verify, dict):
                resp["_position_verify"] = position_verify

        return resp

    # ---------------------------------------------------------
    # close helpers
    # ---------------------------------------------------------
    def _get_close_symbol_lock(
        self,
        symbol: str,
    ) -> threading.Lock:
        """
        Her symbol için tek fiziksel close işlemi sağlar.

        Registry kendi guard'ı altında oluşturulur.
        """
        sym = str(symbol or "").upper().strip()

        guard = getattr(
            self,
            "_close_symbol_locks_guard",
            None,
        )

        if guard is None:
            guard = threading.RLock()
            self._close_symbol_locks_guard = guard

        with guard:
            locks = getattr(
                self,
                "_close_symbol_locks",
                None,
            )

            if not isinstance(locks, dict):
                locks = {}
                self._close_symbol_locks = locks

            lock = locks.get(sym)

            if lock is None:
                lock = threading.Lock()
                locks[sym] = lock

            return lock


    def _close_position(
        self,
        symbol: str,
        price: float = 0.0,
        reason: str = "manual",
        interval: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Single physical close gateway.

        Aynı symbol için eşzamanlı ikinci MARKET close
        emrinin exchange'e gitmesini engeller.
        """
        sym = str(symbol or "").upper().strip()

        if not sym:
            return None

        lock = self._get_close_symbol_lock(sym)

        acquired = False

        try:
            acquired = bool(
                lock.acquire(blocking=False)
            )
        except Exception:
            acquired = False

        if not acquired:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][CLOSE-BLOCK][INFLIGHT] "
                        "physical close already in progress | "
                        "symbol=%s reason=%s",
                        sym,
                        str(reason or ""),
                    )
            except Exception:
                pass

            return {
                "symbol": sym,
                "status": "close_inflight",
                "reason": str(reason or ""),
                "close_inflight": True,
            }

        try:
            return self._close_position_unlocked(
                symbol=sym,
                price=float(price or 0.0),
                reason=str(reason or "manual"),
                interval=str(interval or ""),
            )

        finally:
            try:
                lock.release()
            except Exception:
                pass


    def _close_position_unlocked(
        self,
        symbol: str,
        price: float = 0.0,
        reason: str = "manual",
        interval: str = "",
    ) -> Optional[Dict[str, Any]]:
        sym = str(symbol).upper().strip()
        if not sym:
            return None

        pos = self._get_position(sym)
        if not isinstance(pos, dict) or not pos:
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][CLOSE-BLOCK] no open position found | symbol=%s reason=%s interval=%s",
                        sym,
                        str(reason),
                        str(interval or ""),
                    )
            except Exception:
                pass

            try:
                self._del_position(sym)
                self._remove_from_bridge_state(sym)
                if self.logger:
                    self.logger.info(
                        "[EXEC][STATE] cleanup on missing position executed | symbol=%s",
                        sym,
                    )
            except Exception:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][STATE] cleanup on missing position failed | symbol=%s",
                        sym,
                    )
            return None

        side = str(pos.get("side") or "").strip().lower()
        qty = float(pos.get("qty") or 0.0)
        entry_price = float(pos.get("entry_price") or 0.0)

        if side not in ("long", "short") or qty <= 0:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][CLOSE-BLOCK] invalid local position | symbol=%s side=%s qty=%.10f",
                        sym,
                        side,
                        float(qty),
                    )
            except Exception:
                pass
            return None

        close_price = self._resolve_price(symbol=sym, price=price)
        if close_price is None or float(close_price) <= 0:
            close_price = float(entry_price or 0.0)

        exchange_pos_before = self._get_exchange_position(symbol=sym)
        exchange_has_position = isinstance(exchange_pos_before, dict)

        if exchange_has_position:
            try:
                qty = abs(float(exchange_pos_before.get("qty") or qty or 0.0))
            except Exception:
                pass
            try:
                ex_side = str(exchange_pos_before.get("side") or side).strip().lower()
                if ex_side in ("long", "short"):
                    side = ex_side
            except Exception:
                pass
            try:
                ex_entry = float(exchange_pos_before.get("entry_price") or entry_price or 0.0)
                if ex_entry > 0:
                    entry_price = ex_entry
            except Exception:
                pass

        qty_meta = self._normalize_close_quantity(
            symbol=sym,
            qty=float(qty),
            price=float(close_price or 0.0),
        )

        norm_qty = float(qty_meta.get("norm_qty") or 0.0)
        step = float(qty_meta.get("step") or 0.0)
        min_qty = float(qty_meta.get("min_qty") or 0.0)
        min_notional = float(qty_meta.get("min_notional") or 0.0)
        reject = str(qty_meta.get("reject_reason") or "-")

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][CLOSE][QTY] symbol=%s raw_qty=%.10f norm_qty=%.10f price=%.6f step=%.10f min_qty=%.10f min_notional=%.6f reject=%s",
                    sym,
                    float(qty),
                    float(norm_qty),
                    float(close_price or 0.0),
                    float(step),
                    float(min_qty),
                    float(min_notional),
                    reject,
                )
        except Exception:
            pass

        if norm_qty <= 0:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][CLOSE-BLOCK] normalized qty invalid | symbol=%s raw_qty=%.10f norm_qty=%.10f reject=%s",
                        sym,
                        float(qty),
                        float(norm_qty),
                        reject,
                    )
            except Exception:
                pass
            return None

        realized_pnl = 0.0
        if entry_price > 0 and norm_qty > 0:
            if side == "long":
                realized_pnl = (float(close_price) - float(entry_price)) * float(norm_qty)
            else:
                realized_pnl = (float(entry_price) - float(close_price)) * float(norm_qty)

        def _risk_on_close(_close_price: float, _realized_pnl: float) -> None:
            try:
                rm = getattr(self, "risk_manager", None)
                if rm is not None and hasattr(rm, "on_position_close"):
                    rm.on_position_close(
                        symbol=sym,
                        side=side,
                        qty=float(norm_qty),
                        notional=float(pos.get("notional") or (norm_qty * entry_price)),
                        price=float(_close_price),
                        interval=str(interval or pos.get("interval") or ""),
                        realized_pnl=float(_realized_pnl),
                        meta={
                            "reason": str(reason),
                            "entry_price": float(entry_price),
                            "closed_side": side,
                            "interval": str(interval or pos.get("interval") or ""),
                            "qty": float(norm_qty),
                            "notional": float(pos.get("notional") or (norm_qty * entry_price)),
                            "probs": dict(
                                pos.get("meta", {}).get("probs", {})
                                if isinstance(pos.get("meta"), dict)
                                else {}
                            ),
                            "extra": dict(
                                pos.get("meta", {}).get("extra", {})
                                if isinstance(pos.get("meta"), dict)
                                else {}
                            ),
                        },
                    )
            except Exception:
                if self.logger:
                    self.logger.exception("[RISK] on_position_close failed")

        def _cleanup_closed_state() -> None:
            self._del_position(sym)
            self._remove_from_bridge_state(sym)

            try:
                chk_local = self._get_position(sym)
                chk_bridge_all = self._get_bridge_state()
                if self.logger:
                    self.logger.info(
                        "[EXEC][STATE] cleanup after close | symbol=%s local_exists=%s bridge_exists=%s",
                        sym,
                        bool(isinstance(chk_local, dict) and chk_local),
                        bool(isinstance(chk_bridge_all, dict) and sym in chk_bridge_all),
                    )
            except Exception:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][STATE] cleanup verify failed | symbol=%s",
                        sym,
                    )

        if bool(getattr(self, "dry_run", False)):
            _risk_on_close(float(close_price), float(realized_pnl))
            _cleanup_closed_state()

            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC] DRY_RUN=True close emri gönderilmeyecek | symbol=%s side=%s qty=%.10f reason=%s",
                        sym,
                        side,
                        float(norm_qty),
                        str(reason),
                    )
            except Exception:
                pass

            return {
                "symbol": sym,
                "side": side,
                "qty": float(norm_qty),
                "close_price": float(close_price),
                "entry_price": float(entry_price),
                "realized_pnl": float(realized_pnl),
                "reason": str(reason),
                "dry_run": True,
                "residual_qty": 0.0,
                "residual_side": "",
            }

        if not exchange_has_position:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][CLOSE] exchange position already missing | symbol=%s side=%s reason=%s -> local cleanup only",
                        sym,
                        side,
                        str(reason),
                    )
            except Exception:
                pass

            _risk_on_close(float(close_price), float(realized_pnl))
            _cleanup_closed_state()

            return {
                "symbol": sym,
                "side": side,
                "qty": float(norm_qty),
                "close_price": float(close_price),
                "entry_price": float(entry_price),
                "realized_pnl": float(realized_pnl),
                "reason": str(reason),
                "order": {},
                "residual_qty": 0.0,
                "residual_side": "",
                "exchange_missing_cleanup": True,
            }

        client = getattr(self, "client", None)
        fn = getattr(client, "futures_create_order", None) if client is not None else None
        if not callable(fn):
            try:
                if self.logger:
                    self.logger.error(
                        "[EXEC][CLOSE-BLOCK] futures_create_order unavailable | symbol=%s",
                        sym,
                    )
            except Exception:
                pass
            return None

        order_side = "SELL" if side == "long" else "BUY"
        position_side = "LONG" if side == "long" else "SHORT"

        started_ms = int(time.time() * 1000)
        order_resp: Dict[str, Any] = {}

        close_kwargs = self._build_close_order_kwargs(
            symbol=sym,
            side=order_side,
            qty=float(self._fmt_qty(sym, norm_qty)),
            position_side=position_side,
            reduce_only=False,
        )
        close_kwargs["newClientOrderId"] = f"b1_close_{sym}_{uuid.uuid4().hex[:12]}"

        try:
            order_resp = fn(**close_kwargs) or {}
        except Exception as e:
            if bool(int(os.getenv("CLOSE_REDUCEONLY_RETRY_ENABLE", "1"))) and self._is_reduceonly_retryable_error(e):
                try:
                    if self.logger:
                        self.logger.warning(
                            "[EXEC][CLOSE] retry without reduceOnly | symbol=%s",
                            sym,
                        )
                except Exception:
                    pass

                try:
                    close_kwargs.pop("reduceOnly", None)
                    order_resp = fn(**close_kwargs) or {}
                except Exception as retry_exc:
                    try:
                        if self.logger:
                            self.logger.exception(
                                "[EXEC][CLOSE-BLOCK] close order failed after retry | symbol=%s side=%s qty=%.10f err=%s",
                                sym,
                                side,
                                float(norm_qty),
                                str(retry_exc),
                            )
                    except Exception:
                        pass
                    return None
            else:
                try:
                    if self.logger:
                        self.logger.exception(
                            "[EXEC][CLOSE-BLOCK] close order failed | symbol=%s side=%s qty=%.10f err=%s",
                            sym,
                            side,
                            float(norm_qty),
                            str(e),
                        )
                except Exception:
                    pass
                return None

        dt_ms = int(time.time() * 1000) - started_ms
        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][ORDER] CLOSE OK | fn=futures_create_order symbol=%s side=%s posSide=%s qty=%.10f dt_ms=%s summary=%s",
                    sym,
                    order_side,
                    position_side,
                    float(norm_qty),
                    int(dt_ms),
                    self._safe_json(order_resp, limit=900),
                )
        except Exception:
            pass

        poll_result = self._poll_order_status(
            symbol=sym,
            order_id=order_resp.get("orderId") if isinstance(order_resp, dict) else None,
            client_order_id=str(order_resp.get("clientOrderId") or "") if isinstance(order_resp, dict) else "",
            max_wait_s=5.0,
        )
        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][CLOSE][POLL] %s",
                    self._safe_json(poll_result, limit=900),
                )
        except Exception:
            pass

        filled = {}
        if isinstance(poll_result, dict):
            filled = poll_result.get("result") if isinstance(poll_result.get("result"), dict) else {}
        if not filled:
            filled = order_resp if isinstance(order_resp, dict) else {}

        try:
            avg_price = float(filled.get("avgPrice") or 0.0)
        except Exception:
            avg_price = 0.0
        if avg_price > 0:
            close_price = avg_price

        realized_pnl = 0.0
        if entry_price > 0 and norm_qty > 0:
            if side == "long":
                realized_pnl = (float(close_price) - float(entry_price)) * float(norm_qty)
            else:
                realized_pnl = (float(entry_price) - float(close_price)) * float(norm_qty)

        _risk_on_close(float(close_price), float(realized_pnl))

        exchange_pos_after = self._get_exchange_position(symbol=sym)
        residual_qty = 0.0
        residual_side = side

        if isinstance(exchange_pos_after, dict):
            try:
                residual_qty = abs(float(exchange_pos_after.get("qty") or 0.0))
            except Exception:
                residual_qty = 0.0
            try:
                residual_side = str(exchange_pos_after.get("side") or side).strip().lower() or side
            except Exception:
                residual_side = side

        dust_threshold = max(float(min_qty or 0.0), 0.0)

        if residual_qty <= 0.0:
            _cleanup_closed_state()

            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][CLOSE] CLOSED | symbol=%s side=%s qty=%.10f entry=%.6f close=%.6f realized_pnl=%.6f reason=%s",
                        sym,
                        side,
                        float(norm_qty),
                        float(entry_price),
                        float(close_price),
                        float(realized_pnl),
                        str(reason),
                    )
            except Exception:
                pass
        else:
            residual_pos = dict(pos) if isinstance(pos, dict) else {}
            residual_pos["symbol"] = sym
            residual_pos["side"] = residual_side
            residual_pos["qty"] = float(residual_qty)
            residual_pos["last_price"] = float(close_price)

            if isinstance(exchange_pos_after, dict):
                try:
                    residual_entry = float(
                        exchange_pos_after.get("entry_price")
                        or residual_pos.get("entry_price")
                        or 0.0
                    )
                    if residual_entry > 0:
                        residual_pos["entry_price"] = residual_entry
                except Exception:
                    pass

            self._set_position(sym, residual_pos)
            self._upsert_bridge_state_on_open(
                symbol=sym,
                side=residual_side,
                interval=str(interval or residual_pos.get("interval") or "1m"),
                intent_id="",
            )

            try:
                chk_local = self._get_position(sym)
                chk_bridge_all = self._get_bridge_state()
                if self.logger:
                    self.logger.info(
                        "[EXEC][STATE] partial close state updated | symbol=%s residual_qty=%.10f local_exists=%s bridge_exists=%s",
                        sym,
                        float(residual_qty),
                        bool(isinstance(chk_local, dict) and chk_local),
                        bool(isinstance(chk_bridge_all, dict) and sym in chk_bridge_all),
                    )
            except Exception:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][STATE] partial close verify failed | symbol=%s",
                        sym,
                    )

            try:
                if self.logger:
                    if dust_threshold > 0.0 and residual_qty <= dust_threshold:
                        self.logger.warning(
                            "[EXEC][CLOSE] residual dust remains on exchange | symbol=%s side=%s residual_qty=%.10f dust_threshold=%.10f",
                            sym,
                            residual_side,
                            float(residual_qty),
                            float(dust_threshold),
                        )
                    else:
                        self.logger.warning(
                            "[EXEC][CLOSE] residual position remains on exchange | symbol=%s side=%s residual_qty=%.10f",
                            sym,
                            residual_side,
                            float(residual_qty),
                        )
            except Exception:
                pass

        return {
            "symbol": sym,
            "side": side,
            "qty": float(norm_qty),
            "close_price": float(close_price),
            "entry_price": float(entry_price),
            "realized_pnl": float(realized_pnl),
            "reason": str(reason),
            "order": filled if isinstance(filled, dict) else {},
            "residual_qty": float(residual_qty),
            "residual_side": str(residual_side),
        }

    def close_position(
        self,
        symbol: str,
        price: Optional[float] = None,
        reason: str = "manual",
        interval: str = "",
        intent_id: Optional[str] = None,
        **_ignored: Any,
    ) -> Optional[Dict[str, Any]]:
        sym = str(symbol).upper().strip()
        if not sym:
            return None

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][CLOSE] request | symbol=%s reason=%s interval=%s intent_id=%s input_price=%s",
                    sym,
                    str(reason or "manual"),
                    str(interval or ""),
                    str(intent_id or ""),
                    str(price),
                )
        except Exception:
            pass

        p = self._resolve_price(symbol=sym, price=price)
        if p is None:
            p = 0.0

        pos_snapshot = self._get_position(sym)
        pos_snapshot = dict(pos_snapshot) if isinstance(pos_snapshot, dict) else {}

        close_result = self._close_position(
            symbol=sym,
            price=float(p),
            reason=str(reason or "manual"),
            interval=str(interval or ""),
        )

        # Single outcome telemetry authority for every physical close path.
        # Fail-open by design: telemetry cannot affect close semantics.
        try:
            if (
                isinstance(close_result, dict)
                and not bool(close_result.get("close_inflight"))
                and _emit_okx_oi_outcome_shadow is not None
                and self.redis is not None
            ):
                close_side = str(
                    close_result.get("side")
                    or pos_snapshot.get("side")
                    or ""
                ).strip().lower()
                close_order = (
                    close_result.get("order")
                    if isinstance(close_result.get("order"), dict)
                    else {}
                )
                close_fill_price = float(
                    close_result.get("close_price")
                    or p
                    or 0.0
                )
                entry_fill_price = float(
                    close_result.get("entry_price")
                    or pos_snapshot.get("entry_price")
                    or 0.0
                )
                qty_closed = float(
                    close_result.get("qty")
                    or pos_snapshot.get("qty")
                    or 0.0
                )
                leverage_now = float(
                    self._resolve_position_leverage(pos_snapshot)
                    if pos_snapshot
                    else 1.0
                )
                gross_return = 0.0
                if entry_fill_price > 0 and close_fill_price > 0:
                    if close_side == "long":
                        gross_return = (
                            close_fill_price - entry_fill_price
                        ) / entry_fill_price
                    elif close_side == "short":
                        gross_return = (
                            entry_fill_price - close_fill_price
                        ) / entry_fill_price

                _emit_okx_oi_outcome_shadow(
                    self.redis,
                    symbol=sym,
                    side=close_side,
                    entry_price=entry_fill_price,
                    close_price=close_fill_price,
                    pnl_pct=float(gross_return),
                    reason=str(reason or "manual"),
                    qty=qty_closed,
                    leverage=leverage_now,
                    realized_pnl_usdt=float(close_result.get("realized_pnl") or 0.0),
                    close_order_id=str(close_order.get("orderId") or ""),
                    close_client_order_id=str(close_order.get("clientOrderId") or ""),
                )
        except Exception:
            pass

        return close_result

    # ---------------------------------------------------------
    # monitoring stubs
    # ---------------------------------------------------------
    def _get_latest_signal_for_symbol(self, symbol: str) -> Dict[str, Any]:
        sym = str(symbol).upper().strip()
        if not sym:
            return {}

        r = getattr(self, "redis", None) or getattr(self, "redis_client", None)
        if r is None:
            return {}

        try:
            key = f"bot:last_signal:{sym}"
            raw = r.get(key)
            if not raw:
                return {}

            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")

            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][WEAK] latest signal read failed | symbol=%s",
                        sym,
                    )
            except Exception:
                pass
            return {}


    def _mark_lifecycle_heartbeat(self, symbol: str = "") -> None:
        try:
            self._last_lifecycle_ts = float(time.time())
            if symbol:
                self._last_lifecycle_symbol = str(symbol).upper().strip()
        except Exception:
            pass

    def _check_lifecycle_freeze(self) -> None:
        try:
            force_every = float(
                os.getenv("FORCE_LIFECYCLE_EVERY_SEC", "10") or 10
            )
        except Exception:
            force_every = 10.0

        last_ts = float(getattr(self, "_last_lifecycle_ts", 0.0) or 0.0)
        now_ts = float(time.time())

        if last_ts <= 0:
            self._last_lifecycle_ts = now_ts
            return

        if (now_ts - last_ts) >= force_every:
            # With no active position this is only event-loop/scanner latency, not
            # a lifecycle risk freeze. Preserve the warning unchanged when a
            # position is actually being managed.
            active_count = int(getattr(self, "_last_lifecycle_active_count", 0) or 0)
            if active_count > 0:
                try:
                    if self.logger:
                        self.logger.warning(
                            "[EXEC][LIFECYCLE][FREEZE-WARN] last_seen_sec=%.1f last_symbol=%s active_positions=%s",
                            float(now_ts - last_ts),
                            str(getattr(self, "_last_lifecycle_symbol", "") or "-"),
                            active_count,
                        )
                except Exception:
                    pass

            self._last_lifecycle_ts = now_ts

    def _evaluate_position_lifecycle_exit(
        self,
        symbol: str,
        price: float,
        interval: str,
    ) -> Optional[Dict[str, Any]]:
        sym = str(symbol).upper().strip()
        pos = self._get_position(sym)
        if not isinstance(pos, dict):
            return

        side = str(pos.get("side") or "").strip().lower()
        qty = float(pos.get("qty") or 0.0)
        entry_price = float(pos.get("entry_price") or 0.0)

        if side not in ("long", "short") or qty <= 0 or price <= 0 or entry_price <= 0:
            return

        now_ts = time.time()

        highest_price = float(pos.get("highest_price") or entry_price)
        lowest_price = float(pos.get("lowest_price") or entry_price)
        best_pnl_pct = float(pos.get("best_pnl_pct") or 0.0)
        last_best_ts = float(pos.get("last_best_ts") or now_ts)

        trailing_pct = float(pos.get("trailing_pct") or 0.0)
        stall_ttl_sec = int(pos.get("stall_ttl_sec") or 0)

        sl_price = float(pos.get("sl_price") or 0.0)
        tp_price = float(pos.get("tp_price") or 0.0)

        sl_pct = float(getattr(self, "default_sl_pct", 0.0) or 0.0)
        tp_pct = float(getattr(self, "default_tp_pct", 0.0) or 0.0)
        trailing_activation_pct = float(
            getattr(self, "trailing_activation_pct", 0.0) or 0.0
        )

        tp_runner_enable = bool(getattr(self, "tp_runner_enable", True))
        tp_arm_pnl_pct = float(getattr(self, "tp_arm_pnl_pct", 0.02) or 0.02)
        tp_runner_pullback_pct = float(
            getattr(self, "tp_runner_pullback_pct", 0.006) or 0.006
        )

        hard_stop_enable = bool(getattr(self, "hard_stop_enable", True))
        hard_stop_loss_pct = float(getattr(self, "hard_stop_loss_pct", 0.04) or 0.04)

        profit_protect_enable = bool(getattr(self, "profit_protect_enable", True))
        profit_protect_arm_pct = float(
            getattr(self, "profit_protect_arm_pct", 0.02) or 0.02
        )
        profit_protect_pullback_pct = float(
            getattr(self, "profit_protect_pullback_pct", 0.004) or 0.004
        )
        profit_protect_reverse_score = float(
            getattr(self, "profit_protect_reverse_score", 0.55) or 0.55
        )

        tp_runner_armed = bool(pos.get("tp_runner_armed", False))
        tp_runner_armed_ts = float(pos.get("tp_runner_armed_ts") or 0.0)

        close_reason = None
        trailing_armed = False
        trail_stop_price = 0.0
        pnl_pct = 0.0

        # =====================================================
        # REVERSE SIGNAL — SINGLE EVALUATION PER LIFECYCLE TICK
        #
        # Reverse evaluator Redis confirmation state'i
        # değiştirebildiği için aynı lifecycle tick içinde
        # birden fazla kez çalıştırılmaz.
        #
        # Lazy evaluation:
        # yalnız gerçekten ihtiyaç duyulduğunda ilk kez çalışır.
        # =====================================================
        reverse_eval_done = False
        reverse_meta_cache: Dict[str, Any] = {}

        def _reverse_meta_once() -> Dict[str, Any]:
            nonlocal reverse_eval_done
            nonlocal reverse_meta_cache

            if reverse_eval_done:
                return reverse_meta_cache

            reverse_eval_done = True

            try:
                result = self._evaluate_position_signal_exit(
                    symbol=sym,
                    pos=pos,
                    price=float(price),
                )

                reverse_meta_cache = (
                    dict(result)
                    if isinstance(result, dict)
                    else {}
                )
            except Exception:
                reverse_meta_cache = {}

                try:
                    if self.logger:
                        self.logger.exception(
                            "[EXEC][REVERSE] "
                            "lifecycle evaluation failed | "
                            "symbol=%s",
                            sym,
                        )
                except Exception:
                    pass

            return reverse_meta_cache

        if sl_price <= 0 and sl_pct > 0:
            sl_price = (
                entry_price * (1 - sl_pct)
                if side == "long"
                else entry_price * (1 + sl_pct)
            )

        if tp_price <= 0 and tp_pct > 0:
            tp_price = (
                entry_price * (1 + tp_pct)
                if side == "long"
                else entry_price * (1 - tp_pct)
            )

        if side == "long":
            highest_price = max(highest_price, price)
            pnl_pct = (price - entry_price) / max(entry_price, 1e-12)

            if pnl_pct > best_pnl_pct:
                best_pnl_pct = pnl_pct
                last_best_ts = now_ts

            if tp_runner_enable and best_pnl_pct >= tp_arm_pnl_pct:
                tp_runner_armed = True
                if tp_runner_armed_ts <= 0:
                    tp_runner_armed_ts = now_ts

            trailing_armed = (
                trailing_pct > 0
                and highest_price > entry_price
                and (
                    trailing_activation_pct <= 0
                    or best_pnl_pct >= trailing_activation_pct
                )
            )
            trail_stop_price = highest_price * (1 - trailing_pct) if trailing_armed else 0.0

            protect_armed = (
                profit_protect_enable and best_pnl_pct >= profit_protect_arm_pct
            )

            # =========================================
            # LONG EXIT PRIORITY
            #
            # 1. Safety
            # 2. Profit protection
            # 3. Profit capture
            # =========================================

            if close_reason is None:
                if (
                    hard_stop_enable
                    and pnl_pct <= -abs(hard_stop_loss_pct)
                ):
                    close_reason = "hard_stop_hit"

                elif sl_price > 0 and price <= sl_price:
                    dyn = str(os.getenv("LONG_DYNAMIC_STOP_ENABLE", "0") or "0").strip().lower() in ("1", "true", "yes", "on")
                    confirm_sec = float(os.getenv("LONG_DYNAMIC_STOP_CONFIRM_SEC", "60") or 60)
                    cat_pct = float(os.getenv("LONG_DYNAMIC_STOP_CATASTROPHIC_PCT", "0.045") or 0.045)
                    cat_price = float(entry_price) * (1.0 - max(0.0, cat_pct))
                    pending_ts = float(pos.get("dynamic_stop_pending_ts") or 0.0)
                    if dyn and cat_pct > 0 and price <= cat_price:
                        close_reason = "dynamic_stop_catastrophic"
                    elif dyn and pending_ts <= 0:
                        pos["dynamic_stop_pending_ts"] = float(now_ts)
                        pos["dynamic_stop_pending_price"] = float(price)
                    elif dyn and (now_ts - pending_ts) >= max(0.0, confirm_sec):
                        close_reason = "dynamic_stop_confirmed"
                    elif not dyn:
                        close_reason = "sl_hit"

            if sl_price > 0 and price > sl_price and float(pos.get("dynamic_stop_pending_ts") or 0.0) > 0:
                pos["dynamic_stop_pending_ts"] = 0.0
                pos["dynamic_stop_pending_price"] = 0.0

            if close_reason is None and protect_armed:
                pullback = (
                    (highest_price - price)
                    / max(highest_price, 1e-12)
                    if highest_price > 0
                    else 0.0
                )

                reverse_meta = _reverse_meta_once()

                reverse_hit = (
                    isinstance(reverse_meta, dict)
                    and reverse_meta.get("reason")
                    == "reverse_signal"
                    and float(
                        reverse_meta.get(
                            "signal_score",
                            0.0,
                        )
                    )
                    >= profit_protect_reverse_score
                )

                if reverse_hit:
                    close_reason = (
                        "profit_protect_reverse"
                    )

                elif (
                    pullback
                    >= profit_protect_pullback_pct
                ):
                    close_reason = (
                        "profit_protect_pullback"
                    )

            if close_reason is None:
                if (
                    trailing_armed
                    and price <= trail_stop_price
                ):
                    close_reason = "trailing_hit"

                elif (
                    tp_runner_armed
                    and (
                        best_pnl_pct - pnl_pct
                    )
                    >= tp_runner_pullback_pct
                ):
                    close_reason = "tp_runner_exit"

                elif (
                    tp_price > 0
                    and price >= tp_price
                ):
                    close_reason = "tp_hit"
        else:
            lowest_price = min(lowest_price, price)
            pnl_pct = (entry_price - price) / max(entry_price, 1e-12)

            if pnl_pct > best_pnl_pct:
                best_pnl_pct = pnl_pct
                last_best_ts = now_ts

            trailing_armed = (
                trailing_pct > 0
                and lowest_price < entry_price
                and (
                    trailing_activation_pct <= 0
                    or best_pnl_pct >= trailing_activation_pct
                )
            )

            trail_stop_price = (
                lowest_price * (1 + trailing_pct)
                if trailing_armed
                else 0.0
            )

            protect_armed = (
                profit_protect_enable and best_pnl_pct >= profit_protect_arm_pct
            )

            # =========================================
            # SHORT EXIT PRIORITY
            #
            # 1. Safety
            # 2. Profit protection
            # 3. Profit capture
            # =========================================

            if close_reason is None:
                if (
                    hard_stop_enable
                    and pnl_pct <= -abs(hard_stop_loss_pct)
                ):
                    close_reason = "hard_stop_hit"

                elif (
                    sl_price > 0
                    and price >= sl_price
                ):
                    close_reason = "sl_hit"

            if close_reason is None and protect_armed:
                bounce = (
                    (price - lowest_price)
                    / max(lowest_price, 1e-12)
                    if lowest_price > 0
                    else 0.0
                )

                reverse_meta = _reverse_meta_once()

                reverse_hit = (
                    isinstance(reverse_meta, dict)
                    and reverse_meta.get("reason")
                    == "reverse_signal"
                    and float(
                        reverse_meta.get(
                            "signal_score",
                            0.0,
                        )
                    )
                    >= profit_protect_reverse_score
                )

                if reverse_hit:
                    close_reason = (
                        "profit_protect_reverse"
                    )

                elif (
                    bounce
                    >= profit_protect_pullback_pct
                ):
                    close_reason = (
                        "profit_protect_pullback"
                    )

            if close_reason is None:
                if (
                    trailing_armed
                    and price >= trail_stop_price
                ):
                    close_reason = "trailing_hit"

                elif (
                    tp_price > 0
                    and price <= tp_price
                ):
                    close_reason = "tp_hit"

        scalp_reason = None
        try:
            scalp_reason = self._evaluate_scalp_exit(
                symbol=sym,
                pos=pos,
                price=float(price),
                side=side,
                entry_price=float(entry_price),
                best_pnl_pct=float(best_pnl_pct),
                highest_price=float(highest_price),
                lowest_price=float(lowest_price),
                now_ts=float(now_ts),
                last_best_ts=float(last_best_ts),
                reverse_meta_provider=_reverse_meta_once,
            )
        except Exception as e:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][SCALP] evaluate failed | symbol=%s err=%s",
                        sym,
                        str(e),
                    )
            except Exception:
                pass

        if close_reason is None and scalp_reason:
            close_reason = str(scalp_reason)
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][SCALP] exit trigger | symbol=%s side=%s reason=%s price=%.6f entry=%.6f pnl_pct=%.6f best_pnl_pct=%.6f",
                        sym,
                        side,
                        str(close_reason),
                        float(price),
                        float(entry_price),
                        float(pnl_pct),
                        float(best_pnl_pct),
                    )
            except Exception:
                pass

        if close_reason is None:
            reverse_meta = _reverse_meta_once()

            if reverse_meta:
                close_reason = reverse_meta.get(
                    "reason",
                    "reverse_signal",
                )

        if close_reason is None:
            stalled_for = now_ts - last_best_ts
            # LONG1 lifecycle policy: zarar eden pozisyonu yalnız zaman
            # dolduğu için kapatma. Zararda safety authority SL / hard-stop'tur.
            # Stall ancak tahmini round-trip maliyetin üzerinde gerçek fiyat
            # kârı oluştuğunda uygulanır; aksi halde pozisyon safety stop'a
            # veya yeniden anlamlı kâra dönene kadar bekler.
            stall_min_profit_pct = float(
                os.getenv("STALL_MIN_PROFIT_PCT", "0.0010") or 0.0010
            )
            if (
                stall_ttl_sec > 0
                and float(pnl_pct) >= max(0.0, stall_min_profit_pct)
                and stalled_for >= stall_ttl_sec
            ):
                close_reason = "stall_exit"

        # ===== ROI PROFIT LOCK =====
        profit_lock_reason = None
        try:
            profit_lock_enabled = bool(getattr(self, "profit_lock_enable", False))

            if profit_lock_enabled:
                lev = float(self._resolve_position_leverage(pos))
                roi_pct = float(pnl_pct) * lev
                best_roi_pct = float(best_pnl_pct) * lev

                # FIXED ROI burada değerlendirilmez.
                # Tek authority: _evaluate_lifecycle_roi_exit.

                if side == "long":
                    retrace_pct = (
                        (float(highest_price) - float(price)) / max(float(highest_price), 1e-12)
                        if float(highest_price) > 0
                        else 0.0
                    )
                else:
                    retrace_pct = (
                        (float(price) - float(lowest_price)) / max(float(lowest_price), 1e-12)
                        if float(lowest_price) > 0
                        else 0.0
                    )

                retrace_roi_pct = max(
                    0.0,
                    float(best_roi_pct) - float(roi_pct)
                )
                profit_lock_arm_roi_pct = float(
                    getattr(self, "profit_lock_arm_roi_pct", 0.0175) or 0.0175
                )
                profit_lock_retrace_roi_pct = float(
                    getattr(self, "profit_lock_retrace_roi_pct", 0.0045) or 0.0045
                )
                profit_floor_roi_pct = float(
                    getattr(self, "profit_floor_roi_pct", 0.0040) or 0.0040
                )

                if (
                    float(best_roi_pct) >= float(profit_lock_arm_roi_pct)
                    and float(retrace_roi_pct) >= float(profit_lock_retrace_roi_pct)
                ):
                    profit_lock_reason = "profit_lock_roi"

                if (
                    profit_lock_reason is None
                    and float(best_roi_pct) >= float(profit_lock_arm_roi_pct)
                    and float(roi_pct) <= float(profit_floor_roi_pct)
                ):
                    profit_lock_reason = "profit_floor_roi_exit"

                if profit_lock_reason is not None:
                    try:
                        if self.logger:
                            self.logger.info(
                                "[EXEC][PROFIT-LOCK] trigger | symbol=%s side=%s reason=%s roi_pct=%.6f best_roi_pct=%.6f retrace_roi_pct=%.6f lev=%.2f",
                                sym,
                                side,
                                str(profit_lock_reason),
                                float(roi_pct),
                                float(best_roi_pct),
                                float(retrace_roi_pct),
                                float(lev),
                            )
                    except Exception:
                        pass
            else:
                try:
                    if self.logger:
                        self.logger.debug(
                            "[EXEC][PROFIT-LOCK] disabled | symbol=%s side=%s",
                            sym,
                            side,
                        )
                except Exception:
                    pass

        except Exception as e:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][PROFIT-LOCK] evaluate failed | symbol=%s err=%s",
                        sym,
                        str(e),
                    )
            except Exception:
                pass

        if close_reason is None and profit_lock_reason is not None:
            close_reason = str(profit_lock_reason)

        # ===== USDT LOSS KILL =====
        try:
            qty_now = float(pos.get("qty") or 0.0)
        except Exception:
            qty_now = 0.0

        unrealized_pnl_usdt = self._calc_unrealized_pnl_usdt(
            side=side,
            entry_price=float(entry_price),
            price=float(price),
            qty=float(qty_now),
        )

        if (
            close_reason is None
            and bool(getattr(self, "usdt_loss_kill_enable", True))
            and float(unrealized_pnl_usdt) <= -abs(float(getattr(self, "max_loss_usdt_per_trade", 4.0) or 4.0))
        ):
            close_reason = "usdt_loss_kill"
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][LOSS-KILL] trigger | symbol=%s side=%s pnl_usdt=%.4f threshold=%.4f",
                        sym,
                        side,
                        float(unrealized_pnl_usdt),
                        float(getattr(self, "max_loss_usdt_per_trade", 4.0) or 4.0),
                    )
            except Exception:
                pass

        # ===== DEAD TRADE EXIT =====
        dead_trade_reason = None
        try:
            if bool(getattr(self, "dead_trade_exit_enable", True)):
                opened_ts = 0.0
                try:
                    opened_at_raw = str(pos.get("opened_at") or "").strip()
                    if opened_at_raw:
                        opened_ts = datetime.fromisoformat(
                            opened_at_raw.replace("Z", "+00:00")
                        ).timestamp()
                except Exception:
                    opened_ts = 0.0

                if opened_ts > 0:
                    alive_sec = float(now_ts) - float(opened_ts)
                    max_sec = float(getattr(self, "dead_trade_max_sec", 240) or 240)
                    min_best = float(
                        getattr(self, "dead_trade_min_best_pnl_pct", 0.0005) or 0.0005
                    )

                    signal_score = 0.0
                    whale_score = 0.0
                    whale_dir = ""

                    try:
                        extra = ((pos.get("meta") or {}).get("extra") or {})
                        signal_score = float(
                            extra.get("signal_score")
                            or extra.get("score")
                            or 0.0
                        )
                        whale_score = float(extra.get("whale_score") or 0.0)
                        whale_dir = str(extra.get("whale_dir") or "")
                    except Exception:
                        signal_score = 0.0
                        whale_score = 0.0
                        whale_dir = ""

                    max_sec, min_best = self._adapt_dead_trade_thresholds(
                        symbol=sym,
                        side=side,
                        base_max_sec=max_sec,
                        base_min_best=min_best,
                        signal_score=signal_score,
                        whale_score=whale_score,
                        whale_dir=whale_dir,
                    )

                    if (
                        float(alive_sec) >= float(max_sec)
                        and float(best_pnl_pct) < float(min_best)
                    ):
                        dead_trade_reason = "dead_trade_exit"

                        try:
                            if self.logger:
                                self.logger.info(
                                    "[EXEC][DEAD-TRADE] trigger | symbol=%s side=%s alive_sec=%.1f best_pnl_pct=%.6f min_best=%.6f signal_score=%.4f whale_score=%.4f whale_dir=%s",
                                    sym,
                                    side,
                                    float(alive_sec),
                                    float(best_pnl_pct),
                                    float(min_best),
                                    float(signal_score),
                                    float(whale_score),
                                    str(whale_dir),
                                )
                        except Exception:
                            pass
        except Exception as e:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][DEAD-TRADE] evaluate failed | symbol=%s err=%s",
                        sym,
                        str(e),
                    )
            except Exception:
                pass

        if close_reason is None and dead_trade_reason is not None:
            close_reason = str(dead_trade_reason)

        # ===== POSITION STATE PERSIST =====
        try:
            pos["highest_price"] = float(highest_price)
            pos["lowest_price"] = float(lowest_price)
            pos["best_pnl_pct"] = float(best_pnl_pct)
            pos["last_best_ts"] = float(last_best_ts)

            pos["sl_price"] = float(sl_price)
            pos["tp_price"] = float(tp_price)

            pos["tp_runner_armed"] = bool(tp_runner_armed)
            pos["tp_runner_armed_ts"] = float(tp_runner_armed_ts)

            pos["trailing_armed"] = bool(trailing_armed)
            pos["trail_stop_price"] = float(trail_stop_price)

            self._set_position(sym, pos)
        except Exception:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][STATE] persist failed | symbol=%s",
                        sym,
                    )
            except Exception:
                pass

        # ===== PURE EXIT DECISION =====
        if close_reason is not None:
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][CLOSE][DECISION] "
                        "symbol=%s side=%s reason=%s "
                        "price=%.6f entry=%.6f pnl_pct=%.6f",
                        sym,
                        side,
                        str(close_reason),
                        float(price),
                        float(entry_price),
                        float(pnl_pct),
                    )
            except Exception:
                pass

            return {
                "should_close": True,
                "symbol": str(sym),
                "side": str(side),
                "reason": str(close_reason),
                "price": float(price),
                "entry_price": float(entry_price),
                "pnl_pct": float(pnl_pct),
                "interval": str(interval or ""),
            }

        return None


    def _get_lifecycle_symbol_lock(
        self,
        symbol: str,
    ) -> threading.Lock:
        """
        Aynı symbol için lifecycle evaluation/state mutation
        zincirini serialize eder.
        """
        sym = str(symbol or "").upper().strip()

        guard = getattr(
            self,
            "_lifecycle_symbol_locks_guard",
            None,
        )

        if guard is None:
            guard = threading.RLock()
            self._lifecycle_symbol_locks_guard = guard

        with guard:
            locks = getattr(
                self,
                "_lifecycle_symbol_locks",
                None,
            )

            if not isinstance(locks, dict):
                locks = {}
                self._lifecycle_symbol_locks = locks

            lock = locks.get(sym)

            if lock is None:
                lock = threading.Lock()
                locks[sym] = lock

            return lock






    def _append_hold_csv(self, row: Dict[str, Any]) -> None:
        return

    def _append_trade_csv(self, row: Dict[str, Any]) -> None:
        return



    # ---------------------------------------------------------
    # open by intent
    # ---------------------------------------------------------
    def open_position_from_signal(
        self,
        symbol: str,
        side: str,
        interval: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        sym_u = str(symbol).upper().strip()
        side0 = str(side or "long").strip().lower()
        if side0 not in ("long", "short"):
            side0 = "long"
        interval0 = str(interval or "1m").strip() or "1m"

        _open_key = f"{sym_u}_{side0}"
        _lock_taken = False

        def _maybe_json(x: Any) -> Optional[Dict[str, Any]]:
            if isinstance(x, dict):
                return x
            if isinstance(x, str):
                try:
                    obj = json.loads(x)
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
            return None

        def _merge_pref(dst: Dict[str, Any], src: Optional[Dict[str, Any]]) -> None:
            if not isinstance(src, dict):
                return
            for k, v in src.items():
                if k not in dst or dst.get(k) in (None, "", 0, 0.0, [], {}):
                    dst[k] = v

        def _ret(reason: str, **extra: Any) -> Dict[str, Any]:
            out = {"status": "skip", "reason": reason, "symbol": sym_u, "side": side0}
            out.update(extra)
            return out

        try:
            # =========================
            # HARD DUPLICATE OPEN PROTECTION
            # en başta olmalı: concurrency + timestamp guard
            # =========================
            if not hasattr(self, "_opening_now"):
                self._opening_now = set()
            if not hasattr(
                self,
                "_last_open_attempt_ts",
            ):
                self._last_open_attempt_ts = {}

            attempt_guard_sec = float(
                os.environ["OPEN_ATTEMPT_GUARD_SEC"]
            )

            now_guard = time.time()

            if _open_key in self._opening_now:
                if self.logger:
                    self.logger.info(
                        "[EXEC][OPEN-BLOCK] opening in progress | symbol=%s side=%s",
                        sym_u,
                        side0,
                    )
                return _ret("opening_in_progress")

            last_attempt = self._last_open_attempt_ts.get(
                _open_key
            )

            if (
                last_attempt
                and (
                    now_guard
                    - float(last_attempt)
                ) < attempt_guard_sec
            ):
                if self.logger:
                    self.logger.info(
                        "[EXEC][OPEN-BLOCK] duplicate protection | "
                        "symbol=%s side=%s wait_left=%.2f",
                        sym_u,
                        side0,
                        float(
                            attempt_guard_sec
                            - (
                                now_guard
                                - float(last_attempt)
                            )
                        ),
                    )
                return _ret("duplicate_open_guard")

            self._opening_now.add(_open_key)
            self._last_open_attempt_ts[
                _open_key
            ] = now_guard
            _lock_taken = True

            meta_in = meta if isinstance(meta, dict) else {}
            raw1 = _maybe_json(meta_in.get("raw"))
            raw2 = _maybe_json(raw1.get("raw")) if isinstance(raw1, dict) else None
            raw3 = _maybe_json(raw2.get("raw")) if isinstance(raw2, dict) else None

            meta0: Dict[str, Any] = {}
            _merge_pref(meta0, meta_in)
            _merge_pref(meta0, raw1)
            _merge_pref(meta0, raw2)
            _merge_pref(meta0, raw3)

            meta0["symbol"] = sym_u
            meta0["side"] = side0
            meta0["interval"] = interval0

            if self.logger:
                self.logger.info(
                    "[EXEC][OPEN] enter | symbol=%s side=%s interval=%s meta_keys=%s",
                    sym_u,
                    side0,
                    interval0,
                    sorted(list(meta_in.keys())) if isinstance(meta_in, dict) else [],
                )

            # -------------------------
            # SCORE METADATA
            #
            # Threshold kararı burada tekrar verilmez.
            # Canonical MODEL SCORE GATE execute_decision içindedir:
            #
            # _resolve_long_decision_open_score_context
            #   -> _evaluate_long_candidate_base_precheck
            #
            # Burada signal_score yalnız execution metadata /
            # telemetry için normalize edilir.
            # -------------------------
            signal_score = 0.0
            for k in ("signal_score", "score", "score_total", "_score_total_final", "_score_selected"):
                try:
                    v = float(meta0.get(k) or 0.0)
                except Exception:
                    v = 0.0
                if v > signal_score:
                    signal_score = v

            try:
                whale_score = float(meta0.get("whale_score") or 0.0)
            except Exception:
                whale_score = 0.0

            whale_dir = str(meta0.get("whale_dir", "none") or "none").strip().lower()
            if whale_dir in ("buy", "bull", "up"):
                whale_dir = "long"
            elif whale_dir in ("sell", "bear", "down"):
                whale_dir = "short"
            elif whale_dir not in ("long", "short"):
                whale_dir = "none"

            whale_action = str(meta0.get("whale_action") or "").strip().lower()
            if not whale_action:
                try:
                    whale_action = str(self._whale_action(meta0) or "").strip().lower()
                except Exception:
                    whale_action = ""

            whale_bias_now = str(meta0.get("whale_bias") or "").strip().lower()
            if not whale_bias_now:
                whale_bias_now = whale_dir if whale_dir in ("long", "short") else "hold"

            meta0["signal_score"] = float(signal_score)
            meta0["score"] = float(signal_score)
            meta0["whale_score"] = float(whale_score)
            meta0["whale_dir"] = whale_dir
            meta0["whale_action"] = whale_action
            meta0["whale_bias"] = whale_bias_now

            existing_pos = self._get_effective_position(sym_u)
            existing_side = (
                str(existing_pos.get("side") or "").strip().lower()
                if isinstance(existing_pos, dict) else ""
            )
            try:
                existing_layers = max(1, int(existing_pos.get("entry_layers") or 1)) if isinstance(existing_pos, dict) else 0
            except Exception:
                existing_layers = 1 if isinstance(existing_pos, dict) else 0
            scale_in_enable = (
                side0 == "long"
                and str(os.getenv("LONG_SCALE_IN_ENABLE", "0") or "0").strip().lower()
                in ("1", "true", "yes", "on")
            )
            try:
                max_entry_layers = max(1, int(float(os.getenv("LONG_MAX_ENTRY_LAYERS", "1") or 1)))
            except Exception:
                max_entry_layers = 1
            try:
                scale_in_score_floor = float(os.getenv("LONG_SCALE_IN_SCORE_FLOOR", "0.5114") or 0.5114)
            except Exception:
                scale_in_score_floor = 0.5114
            is_scale_in = bool(
                scale_in_enable
                and existing_side == side0
                and existing_layers > 0
                and existing_layers < max_entry_layers
                and float(signal_score) >= float(scale_in_score_floor)
            )
            meta0["is_scale_in"] = bool(is_scale_in)
            meta0["existing_entry_layers"] = int(existing_layers or 0)
            if existing_side == side0 and not is_scale_in:
                return _ret(
                    "same_side_scale_in_blocked",
                    meta={"layers": int(existing_layers or 0), "max_layers": int(max_entry_layers),
                          "score": float(signal_score), "score_floor": float(scale_in_score_floor)},
                )

            if self.logger:
                self.logger.info(
                    "[EXEC][WHALE][CTX] "
                    "symbol=%s side=%s whale_dir=%s "
                    "whale_score=%.4f signal_score=%.4f "
                    "action=%s",
                    sym_u,
                    side0,
                    whale_dir,
                    float(whale_score),
                    float(signal_score),
                    whale_action or "-",
                )

            # -------------------------
            # PRICE RESOLVE
            # -------------------------
            intent_price = self._resolve_price(
                symbol=sym_u,
                price=meta0.get("price"),
                mark_price=meta0.get("mark_price"),
                last_price=meta0.get("last_price"),
            )

            if intent_price is None or intent_price <= 0:
                try:
                    client = getattr(self, "client", None)
                    fn = getattr(client, "futures_mark_price", None) if client is not None else None
                    if callable(fn):
                        mp = fn(symbol=sym_u)
                        if isinstance(mp, dict):
                            intent_price = self._clip_float(mp.get("markPrice"), None)
                except Exception:
                    intent_price = None

            if intent_price is None or intent_price <= 0:
                try:
                    intent_price = self._get_cached_mid_price(sym_u)
                except Exception:
                    intent_price = None

            if intent_price is None or intent_price <= 0:
                return _ret("missing_price")

            meta0["price"] = float(intent_price)

            order_price = None
            try:
                client = getattr(self, "client", None)
                fn = getattr(client, "futures_mark_price", None) if client is not None else None
                if callable(fn):
                    mp = fn(symbol=sym_u)
                    if isinstance(mp, dict):
                        order_price = self._clip_float(mp.get("markPrice"), None)
            except Exception:
                order_price = None

            if order_price is None or order_price <= 0:
                try:
                    order_price = self._get_cached_mid_price(sym_u)
                except Exception:
                    order_price = None

            if order_price is None or order_price <= 0:
                order_price = float(intent_price)

            original_intent_price = float(intent_price)
            intent_order_gap = abs(float(original_intent_price) - float(order_price)) / max(abs(float(order_price)), 1e-12)
            max_gap_pct_block = float(
                os.environ["OPEN_PRICE_MAX_GAP_PCT_BLOCK"]
            )

            if self.logger:
                self.logger.info(
                    "[EXEC][PRICE][CHECK] symbol=%s side=%s intent_price=%.6f order_price=%.6f gap_pct=%.4f max_gap=%.4f",
                    sym_u,
                    side0,
                    float(original_intent_price),
                    float(order_price),
                    float(intent_order_gap),
                    float(max_gap_pct_block),
                )

            if intent_order_gap >= float(max_gap_pct_block):
                if self.logger:
                    self.logger.info(
                        "[EXEC][OPEN-BLOCK][PRICE-MISMATCH] symbol=%s side=%s gap_pct=%.4f max_gap=%.4f",
                        sym_u,
                        side0,
                        float(intent_order_gap),
                        float(max_gap_pct_block),
                    )
                return _ret("price_mismatch")

            meta0["intent_price_sanity_fallback"] = False
            meta0["intent_price_original"] = float(original_intent_price)

            # -------------------------
            # POSITION / COOLDOWN CHECKS
            # -------------------------
            same_symbol_cooldown_sec = float(
                os.environ["SAME_SYMBOL_OPEN_COOLDOWN_SEC"]
            )
            try:
                last_open_key = f"bot:last_open_ts:{sym_u}"
                last_open_ts_raw = self.redis.get(last_open_key) if getattr(self, "redis", None) is not None else None
                last_open_ts = float(last_open_ts_raw or 0.0)
            except Exception:
                last_open_ts = 0.0

            now_ts = time.time()
            if last_open_ts > 0 and (now_ts - last_open_ts) < same_symbol_cooldown_sec:
                if self.logger:
                    self.logger.info(
                        "[EXEC][OPEN-BLOCK][SYMBOL-COOLDOWN] symbol=%s wait_left=%.1f cooldown=%.1f",
                        sym_u,
                        float(same_symbol_cooldown_sec - (now_ts - last_open_ts)),
                        float(same_symbol_cooldown_sec),
                    )
                return _ret("symbol_cooldown")

            # -------------------------
            # BALANCE / QTY
            # -------------------------
            try:
                eq_live = self._get_futures_equity_usdt_sync()
                if eq_live > 0:
                    meta0["equity_usdt"] = float(eq_live)
            except Exception:
                pass

            try:
                avail_live = self._get_available_balance_usdt_sync()
                if avail_live > 0:
                    meta0["available_balance_usdt"] = float(avail_live)
            except Exception:
                pass

            if is_scale_in:
                try:
                    add_pct = float(os.getenv("LONG_SCALE_IN_ADD_BALANCE_PCT", "0.10") or 0.10)
                except Exception:
                    add_pct = 0.10
                add_pct = max(0.01, min(float(add_pct), 1.0))
                equity_for_add = self._clip_float(meta0.get("equity_usdt"), None)
                if equity_for_add is None or equity_for_add <= 0:
                    equity_for_add = self._clip_float(self._get_futures_equity_usdt_sync(), None)
                if equity_for_add is None or equity_for_add <= 0:
                    equity_for_add = self._clip_float(meta0.get("available_balance_usdt"), None)
                notional = float(equity_for_add or 0.0) * float(add_pct)
                meta0["scale_in_add_balance_pct"] = float(add_pct)
                meta0["scale_in_layer_target"] = int(existing_layers + 1)
            else:
                notional = self._compute_balance_based_notional(
                    sym_u,
                    side0,
                    float(order_price),
                    meta0,
                )
            raw_notional = float(notional)

            if notional <= 0:
                return _ret(
                    "invalid_balance_based_notional",
                    meta={
                        "notional": float(notional),
                        "balance_pct": float(
                            self.per_position_balance_pct
                        ),
                    },
                )

            raw_qty = self._round_qty(float(notional) / float(order_price))
            symbol_info = self._get_symbol_info(sym_u)
            qty, qmeta = self._normalize_order_qty(
                symbol=sym_u,
                raw_qty=float(raw_qty),
                price=float(order_price),
                symbol_info=symbol_info,
            )

            if qty <= 0:
                return _ret("bad_qty_after_normalization", meta=qmeta)

            final_notional = float(qty) * float(order_price)
            incremental_order_qty = float(qty)
            incremental_order_notional = float(final_notional)

            extra_safe = dict(meta0)
            extra_safe.update(
                {
                    "symbol": sym_u,
                    "side": side0,
                    "interval": interval0,
                    "price": float(order_price),
                    "intent_price": float(intent_price),
                    "order_price": float(order_price),
                    "signal_score": float(signal_score),
                    "score": float(signal_score),
                    "whale_action": whale_action,
                    "whale_score": float(whale_score),
                    "whale_dir": whale_dir,
                    "trail_pct": meta0.get("trail_pct", None),
                    "stall_ttl_sec": meta0.get("stall_ttl_sec", None),
                    "whale_open_notional_before": float(raw_notional),
                    "whale_open_notional_after": float(final_notional),
                    "whale_notional_adjusted": bool(abs(float(final_notional) - float(raw_notional)) > 1e-12),
                }
            )

            # FAST-OPEN EMA metadata:
            # Yeni piyasa verisi fetch edilmez.
            # Upstream'den gelen geçerli EMA değerleri korunur.
            ema7_safe = (
                self._clip_float(extra_safe.get("ema7"), None)
                or self._clip_float(extra_safe.get("ema_fast"), None)
                or 0.0
            )
            ema25_safe = (
                self._clip_float(extra_safe.get("ema25"), None)
                or self._clip_float(extra_safe.get("ema_slow"), None)
                or 0.0
            )
            ema99_safe = (
                self._clip_float(extra_safe.get("ema99"), None)
                or 0.0
            )

            extra_safe["ema7"] = float(ema7_safe)
            extra_safe["ema25"] = float(ema25_safe)
            extra_safe["ema99"] = float(ema99_safe)
            extra_safe["ema_fast"] = float(ema7_safe)
            extra_safe["ema_slow"] = float(ema25_safe)

            whale_bias_now = self._whale_bias(
                side=side0,
                extra=extra_safe,
            )
            extra_safe["whale_bias"] = whale_bias_now

            if self.logger:
                self.logger.info(
                    "[EXEC][WHALE][OPEN-CHECK] "
                    "symbol=%s side=%s action=%s bias=%s "
                    "whale_dir=%s whale_score=%.3f "
                    "signal_score=%.4f raw_notional=%.2f "
                    "final_notional=%.2f",
                    sym_u,
                    side0,
                    whale_action or "-",
                    whale_bias_now,
                    whale_dir,
                    float(whale_score),
                    float(signal_score),
                    float(raw_notional),
                    float(final_notional),
                )

            # -------------------------
            # SINGLE EXCHANGE OPEN ONLY
            # -------------------------
            order_resp = None

            if not self.dry_run:
                order_resp = self._exchange_open_market(
                    symbol=sym_u,
                    side=side0,
                    qty=float(qty),
                    price=float(order_price),
                    reduce_only=False,
                    extra=extra_safe,
                )

                if not isinstance(order_resp, dict):
                    raise RuntimeError(
                        "exchange open returned invalid response"
                    )

                target_leverage = int(
                    order_resp.get("_target_leverage")
                    or 0
                )
                applied_leverage = int(
                    order_resp.get("_applied_leverage")
                    or target_leverage
                    or 0
                )

                if target_leverage <= 0:
                    raise RuntimeError(
                        "exchange leverage metadata missing"
                    )

            else:
                target_leverage = self._resolve_target_leverage(
                    extra_safe
                )
                target_leverage = int(
                    max(
                        1,
                        min(
                            int(target_leverage),
                            int(self.max_leverage),
                        ),
                    )
                )
                applied_leverage = int(target_leverage)

            extra_safe["target_leverage"] = int(
                target_leverage
            )
            extra_safe["applied_leverage"] = int(
                applied_leverage
            )
            extra_safe["leverage"] = int(
                applied_leverage
            )

            commit_qty = float(qty)
            commit_price = float(order_price)
            commit_source = "requested"

            if isinstance(order_resp, dict):
                position_verify = order_resp.get(
                    "_position_verify"
                )

                if isinstance(position_verify, dict):
                    verified_qty = self._clip_float(
                        position_verify.get("positionAmt"),
                        None,
                    )
                    verified_price = self._clip_float(
                        position_verify.get("entryPrice"),
                        None,
                    )

                    if verified_qty is not None and abs(float(verified_qty)) > 0:
                        commit_qty = abs(float(verified_qty))
                        commit_source = "position_verify"

                    if verified_price is not None and float(verified_price) > 0:
                        commit_price = float(verified_price)

                if commit_source == "requested":
                    executed_qty = self._clip_float(
                        order_resp.get("executedQty"),
                        None,
                    )
                    avg_price = self._clip_float(
                        order_resp.get("avgPrice"),
                        None,
                    )
                    cum_quote = self._clip_float(
                        order_resp.get("cumQuote"),
                        None,
                    )

                    if executed_qty is not None and float(executed_qty) > 0:
                        commit_qty = float(executed_qty)
                        commit_source = "order_response"

                        if avg_price is not None and float(avg_price) > 0:
                            commit_price = float(avg_price)
                        elif cum_quote is not None and float(cum_quote) > 0:
                            commit_price = (
                                float(cum_quote)
                                / float(executed_qty)
                            )

            incremental_commit_qty = float(incremental_order_qty)
            incremental_commit_price = float(order_price)
            if isinstance(order_resp, dict):
                _exec_q = self._clip_float(order_resp.get("executedQty"), None)
                _avg_p = self._clip_float(order_resp.get("avgPrice"), None)
                if _exec_q is not None and _exec_q > 0:
                    incremental_commit_qty = float(_exec_q)
                if _avg_p is not None and _avg_p > 0:
                    incremental_commit_price = float(_avg_p)

            if is_scale_in and commit_source != "position_verify" and isinstance(existing_pos, dict):
                old_qty = float(existing_pos.get("qty") or 0.0)
                old_entry = float(existing_pos.get("entry_price") or 0.0)
                new_total_qty = old_qty + float(incremental_commit_qty)
                if old_qty > 0 and old_entry > 0 and new_total_qty > 0:
                    commit_price = (old_qty * old_entry + float(incremental_commit_qty) * float(incremental_commit_price)) / new_total_qty
                    commit_qty = float(new_total_qty)
                    commit_source = "local_scale_merge"

            commit_notional = float(commit_qty) * float(commit_price)
            incremental_commit_notional = float(incremental_commit_qty) * float(incremental_commit_price)

            extra_safe["exchange_commit_source"] = str(
                commit_source
            )
            extra_safe["exchange_commit_qty"] = float(
                commit_qty
            )
            extra_safe["exchange_commit_price"] = float(
                commit_price
            )

            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][OPEN][COMMIT] "
                        "symbol=%s side=%s source=%s "
                        "qty=%.10f price=%.8f notional=%.4f",
                        sym_u,
                        side0,
                        str(commit_source),
                        float(commit_qty),
                        float(commit_price),
                        float(commit_notional),
                    )

                    if (
                        not self.dry_run
                        and commit_source == "requested"
                    ):
                        self.logger.warning(
                            "[EXEC][OPEN][COMMIT-FALLBACK] "
                            "confirmed order without exchange fill metrics | "
                            "symbol=%s side=%s",
                            sym_u,
                            side0,
                        )
            except Exception:
                pass

            probs: Dict[str, float] = {}
            now_ts = time.time()
            sync_grace_sec = 45.0

            pos, _opened_at = self._create_position_dict(
                signal=side0,
                symbol=sym_u,
                price=float(commit_price),
                qty=float(commit_qty),
                notional=float(commit_notional),
                interval=interval0,
                probs=probs,
                extra=extra_safe,
            )
            if not isinstance(pos, dict):
                pos = {}

            if is_scale_in and isinstance(existing_pos, dict):
                preserved_created_ts = float(existing_pos.get("created_ts") or now_ts)
                new_layers = int(existing_layers + 1)
            else:
                preserved_created_ts = float(now_ts)
                new_layers = 1

            pos.update(
                {
                    "created_ts": float(preserved_created_ts),
                    "bridge_written_ts": float(now_ts),
                    "sync_grace_until": float(now_ts + sync_grace_sec),
                    "symbol": sym_u,
                    "side": side0,
                    "qty": float(commit_qty),
                    "entry_price": float(
                        pos.get("entry_price")
                        or commit_price
                        or 0.0
                    ),
                    "notional": float(
                        pos.get("notional")
                        or commit_notional
                        or 0.0
                    ),
                    "interval": str(pos.get("interval") or interval0).strip() or "1m",
                    "intent_id": str(extra_safe.get("intent_id") or ""),
                    "open_order_id": str(
                        order_resp.get("orderId")
                        if isinstance(order_resp, dict)
                        else ""
                    ),
                    "open_client_order_id": str(
                        order_resp.get("clientOrderId")
                        if isinstance(order_resp, dict)
                        else ""
                    ),
                    "exchange_commit_source": str(commit_source),
                    "entry_layers": int(new_layers),
                    "scale_in_last_ts": float(now_ts if is_scale_in else 0.0),
                    "scale_in_last_add_qty": float(incremental_commit_qty if is_scale_in else 0.0),
                    "scale_in_last_add_notional": float(incremental_commit_notional if is_scale_in else 0.0),
                }
            )

            if is_scale_in:
                pos["highest_price"] = float(commit_price)
                pos["lowest_price"] = float(commit_price)
                pos["best_pnl_pct"] = 0.0
                pos["best_roi_pct"] = 0.0
                pos["best_roi"] = 0.0
                pos["last_best_ts"] = float(now_ts)
                pos["sl_price"] = 0.0
                pos["tp_price"] = 0.0
                pos["tp_runner_armed"] = False
                pos["tp_runner_armed_ts"] = 0.0
                pos["dynamic_stop_pending_ts"] = 0.0

            try:
                if self.redis is not None:
                    self.redis.delete("fixed_roi_best:" + str(sym_u).upper().strip())
            except Exception:
                pass

            self._set_position(sym_u, pos)

            try:
                if getattr(self, "redis", None) is not None:
                    self.redis.setex(f"bot:last_open_ts:{sym_u}", 3600, str(time.time()))
            except Exception:
                pass

            try:
                self._upsert_bridge_state_on_open(
                    symbol=sym_u,
                    side=side0,
                    interval=interval0,
                    intent_id=str(extra_safe.get("intent_id") or ""),
                )
            except Exception:
                pass

            try:
                self._notify_position_open(
                    sym_u,
                    interval0,
                    side0,
                    float(commit_qty),
                    float(commit_price),
                    extra_safe,
                )
            except Exception:
                pass

            try:
                rm = getattr(self, "risk_manager", None)
                if rm is not None:
                    out = rm.on_position_open(
                        symbol=sym_u,
                        side=side0,
                        qty=float(incremental_commit_qty if is_scale_in else commit_qty),
                        notional=float(incremental_commit_notional if is_scale_in else commit_notional),
                        price=float(incremental_commit_price if is_scale_in else commit_price),
                        interval=interval0,
                        meta={
                            "reason": "INTENT_SCALE_IN" if is_scale_in else "INTENT_OPEN",
                            **extra_safe,
                            "created_ts": float(now_ts),
                            "bridge_written_ts": float(now_ts),
                            "sync_grace_until": float(now_ts + sync_grace_sec),
                        },
                    )
                    self._fire_and_forget(out, label="risk_on_open_intent")
            except Exception:
                pass

            return {
                "status": ("scaled_in" if is_scale_in else "opened") if not self.dry_run else ("dry_run_scale_in" if is_scale_in else "dry_run"),
                "symbol": sym_u,
                "side": side0,
                "qty": float(commit_qty),
                "price": float(commit_price),
                "notional": float(commit_notional),
                "trail_pct": float(pos.get("trailing_pct") or 0.0),
                "stall_ttl_sec": int(pos.get("stall_ttl_sec") or 0),
                "target_leverage": int(target_leverage),
                "intent_id": str(pos.get("intent_id") or ""),
                "open_order_id": str(pos.get("open_order_id") or ""),
                "open_client_order_id": str(pos.get("open_client_order_id") or ""),
                "exchange_commit_source": str(pos.get("exchange_commit_source") or ""),
                "whale_action": whale_action,
                "whale_bias": whale_bias_now,
                "signal_score": float(signal_score),
                "whale_score": float(whale_score),
                "whale_dir": whale_dir,
                "created_ts": float(pos.get("created_ts") or now_ts),
                "bridge_written_ts": float(pos.get("bridge_written_ts") or now_ts),
                "sync_grace_until": float(pos.get("sync_grace_until") or (now_ts + sync_grace_sec)),
                "entry_layers": int(pos.get("entry_layers") or 1),
                "is_scale_in": bool(is_scale_in),
                "incremental_notional": float(incremental_commit_notional if is_scale_in else commit_notional),
            }

        except Exception as e:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][INTENT] open_position_from_signal failed | symbol=%s side=%s err=%s",
                        sym_u,
                        side0,
                        str(e)[:300],
                    )
            except Exception:
                pass
            return {"status": "skip", "reason": "open_exception", "symbol": sym_u, "side": side0}

        finally:
            try:
                if _lock_taken and hasattr(self, "_opening_now"):
                    self._opening_now.discard(_open_key)
            except Exception:
                pass

    # ---------------------------------------------------------
    # async decision executor
    # ---------------------------------------------------------
    # =========================================================
    # LONG ENTRY DECISION ARCHITECTURE
    # =========================================================

    def _make_long_entry_decision(
        self,
        *,
        allow: bool,
        action: str,
        reason: str,
        signal_score: Optional[float] = None,
        required_score: Optional[float] = None,
        progress: Optional[float] = None,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        LONG giriş değerlendirmeleri için standart karar sözlüğü
        oluşturur.

        Bu helper:
            - state değiştirmez
            - pozisyon açmaz
            - pozisyon kapatmaz
            - yalnızca karar verisi üretir
        """
        action_norm = str(
            action or "block"
        ).strip().lower()

        if action_norm not in (
            "open",
            "block",
            "pending",
            "close",
            "hold",
        ):
            action_norm = "block"

        reason_norm = str(
            reason or "unknown"
        ).strip().lower()

        decision: Dict[str, Any] = {
            "allow": bool(allow),
            "action": action_norm,
            "reason": reason_norm,
            "retryable": bool(retryable),
        }

        if signal_score is not None:
            try:
                decision["score"] = float(signal_score)
            except Exception:
                pass

        if required_score is not None:
            try:
                decision["required_score"] = float(
                    required_score
                )
            except Exception:
                pass

        if progress is not None:
            try:
                decision["progress"] = float(progress)
            except Exception:
                pass

        if isinstance(details, dict) and details:
            decision["details"] = dict(details)

        return decision

    def _normalize_long_entry_decision(
        self,
        decision: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Evaluator veya başka bir karar katmanından gelen değeri
        standart LONG karar formatına dönüştürür.

        Geçersiz karar güvenli biçimde block kabul edilir.
        """
        if not isinstance(decision, dict):
            return self._make_long_entry_decision(
                allow=False,
                action="block",
                reason="invalid_decision",
                retryable=False,
            )

        allow = bool(
            decision.get("allow", False)
        )

        action = str(
            decision.get("action")
            or ("open" if allow else "block")
        ).strip().lower()

        reason = str(
            decision.get("reason")
            or "unknown"
        ).strip().lower()

        retryable = bool(
            decision.get("retryable", False)
        )

        score = decision.get("score")
        required_score = decision.get(
            "required_score"
        )
        progress = decision.get("progress")

        details = decision.get("details")

        return self._make_long_entry_decision(
            allow=allow,
            action=action,
            reason=reason,
            signal_score=score,
            required_score=required_score,
            progress=progress,
            retryable=retryable,
            details=(
                details
                if isinstance(details, dict)
                else None
            ),
        )

    def _prepare_long_open_payload(
        self,
        extra: Optional[Dict[str, Any]],
        *,
        price: float,
        signal_score: float,
        decision_interval: str,
        entry_interval: str,
        exit_interval: str,
        lifecycle_interval: str,
        required_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        LONG emir açılışı için kullanılacak payload'u üretir.

        Gelen extra sözlüğünü doğrudan değiştirmez.
        """
        payload: Dict[str, Any] = dict(
            extra
            if isinstance(extra, dict)
            else {}
        )

        try:
            price_f = float(price or 0.0)
        except Exception:
            price_f = 0.0

        try:
            score_f = float(signal_score)
        except Exception:
            score_f = 0.0

        payload["price"] = price_f
        payload["signal_score"] = score_f
        payload["decision_interval"] = str(
            decision_interval or ""
        )
        payload["entry_interval"] = str(
            entry_interval or ""
        )
        payload["exit_interval"] = str(
            exit_interval or ""
        )
        payload["lifecycle_interval"] = str(
            lifecycle_interval or ""
        )

        if required_score is not None:
            try:
                payload["open_min_score"] = float(
                    required_score
                )
            except Exception:
                pass

        return payload

    def _resolve_long_open_context(
        self,
        *,
        symbol: str,
        side: str,
        extra: Optional[Dict[str, Any]],
        probs: Optional[Dict[str, float]],
    ) -> Dict[str, Any]:
        """
        LONG açılış kararında kullanılan skor bağlamını çözer.

        Bu helper:
            - minimum açılış skorunu hesaplar
            - coin/side özel eşiği uygular
            - model sinyal skorunu çözer
            - dynamic score ayarını uygular
            - yalnızca context sözlüğü döndürür

        Pozisyon açmaz veya kapatmaz.
        """
        sym_u = str(symbol or "").upper().strip()
        side_norm = str(side or "").strip().lower()

        extra0: Dict[str, Any] = dict(
            extra
            if isinstance(extra, dict)
            else {}
        )

        probs0: Dict[str, float] = dict(
            probs
            if isinstance(probs, dict)
            else {}
        )

        min_open_score = float(
            os.environ["OPEN_MIN_SCORE"]
        )

        open_min_score = self._get_coin_side_min_open_score(
            symbol=sym_u,
            side=side_norm,
            default_score=min_open_score,
        )

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][COIN-MIN-SCORE] "
                    "symbol=%s side=%s min_open=%.4f",
                    sym_u,
                    side_norm,
                    float(open_min_score),
                )
        except Exception:
            pass

        signal_score = self._resolve_signal_score_for_open(
            side=side_norm,
            extra=extra0,
            probs=probs0,
        )

        # =====================================================
        # DYNAMIC COIN SCORE ADJUST
        # =====================================================
        try:
            dyn_enable = str(
                os.getenv(
                    "DYNAMIC_COIN_SCORE_ENABLE",
                    "0",
                )
                or "0"
            ).strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )

            if dyn_enable and side_norm in (
                "long",
                "short",
            ):
                dyn_min = float(
                    os.getenv(
                        "DYNAMIC_SCORE_MIN",
                        "0.49",
                    )
                    or 0.49
                )

                dyn_max = float(
                    os.getenv(
                        "DYNAMIC_SCORE_MAX",
                        "0.58",
                    )
                    or 0.58
                )

                atr_boost = float(
                    os.getenv(
                        "DYNAMIC_SCORE_ATR_BOOST",
                        "0.0",
                    )
                    or 0.0
                )

                spread_boost = float(
                    os.getenv(
                        "DYNAMIC_SCORE_SPREAD_BOOST",
                        "0.0",
                    )
                    or 0.0
                )

                ema_relax = float(
                    os.getenv(
                        "DYNAMIC_SCORE_EMA_RELAX",
                        "0.0",
                    )
                    or 0.0
                )

                whale_relax = float(
                    os.getenv(
                        "DYNAMIC_SCORE_WHALE_RELAX",
                        "0.0",
                    )
                    or 0.0
                )

                dyn_score = float(open_min_score)

                atr_v = float(
                    extra0.get("atr")
                    or extra0.get("atr_pct")
                    or 0.0
                )

                spread_v = float(
                    extra0.get("spread_pct")
                    or extra0.get("spread")
                    or 0.0
                )

                whale_dir_dyn = str(
                    extra0.get("whale_dir")
                    or ""
                ).strip().lower()

                whale_score_dyn = float(
                    extra0.get("whale_score")
                    or 0.0
                )

                ema7_v = float(
                    extra0.get("ema7")
                    or 0.0
                )

                ema25_v = float(
                    extra0.get("ema25")
                    or 0.0
                )

                # ATR yüksekse daha seçici ol.
                if atr_v > 0:
                    dyn_score += atr_boost

                # Spread yüksekse daha seçici ol.
                if spread_v > 0:
                    dyn_score += spread_boost

                # EMA aynı yöndeyse eşiği gevşet.
                if (
                    side_norm == "long"
                    and ema7_v > 0
                    and ema25_v > 0
                    and ema7_v > ema25_v
                ):
                    dyn_score -= ema_relax

                if (
                    side_norm == "short"
                    and ema7_v > 0
                    and ema25_v > 0
                    and ema7_v < ema25_v
                ):
                    dyn_score -= ema_relax

                # Whale aynı yöndeyse eşiği gevşet.
                if (
                    whale_dir_dyn == side_norm
                    and whale_score_dyn > 0
                ):
                    dyn_score -= whale_relax

                dyn_score = max(
                    dyn_min,
                    min(dyn_max, dyn_score),
                )

                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][DYNAMIC-SCORE] "
                            "symbol=%s side=%s "
                            "base=%.4f final=%.4f "
                            "min=%.4f max=%.4f "
                            "atr=%.6f spread=%.6f "
                            "whale_dir=%s "
                            "whale_score=%.4f",
                            sym_u,
                            side_norm,
                            float(open_min_score),
                            float(dyn_score),
                            float(dyn_min),
                            float(dyn_max),
                            float(atr_v),
                            float(spread_v),
                            whale_dir_dyn,
                            float(whale_score_dyn),
                        )
                except Exception:
                    pass

                open_min_score = float(dyn_score)

        except Exception as exc:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][DYNAMIC-SCORE][WARN] "
                        "symbol=%s side=%s err=%s",
                        sym_u,
                        side_norm,
                        str(exc)[:200],
                    )
            except Exception:
                pass

        if side_norm in ("long", "short"):
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][OPEN][SCORE] "
                        "symbol=%s side=%s "
                        "resolved_score=%.4f "
                        "p_buy_ema=%.4f "
                        "p_buy_raw=%.4f "
                        "mcf=%.4f",
                        sym_u,
                        side_norm,
                        float(signal_score),
                        float(
                            extra0.get("p_buy_ema")
                            or 0.0
                        ),
                        float(
                            extra0.get("p_buy_raw")
                            or 0.0
                        ),
                        float(
                            extra0.get(
                                "model_confidence_factor"
                            )
                            or 0.0
                        ),
                    )
            except Exception:
                pass

        return {
            "symbol": sym_u,
            "side": side_norm,
            "signal_score": float(signal_score),
            "open_min_score": float(open_min_score),
            "base_min_score": float(min_open_score),
        }

    def _handle_long_explicit_close_signal(
        self,
        *,
        raw_signal: str,
        symbol: str,
        price: float,
        interval: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Açık CLOSE / EXIT / FLAT kararlarını position close akışına yönlendirir.

        True:
            Sinyal explicit close sinyalidir ve çağrı bu katmanda tüketilmiştir.

        False:
            Sinyal explicit close değildir; normal karar akışı devam etmelidir.
        """
        raw_signal_norm = str(
            raw_signal or ""
        ).strip().lower()

        if raw_signal_norm not in (
            "close",
            "exit",
            "flat",
        ):
            return False

        sym_u = str(
            symbol or ""
        ).upper().strip()

        extra0 = (
            extra
            if isinstance(extra, dict)
            else {}
        )

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][CLOSE] explicit close signal received | "
                    "symbol=%s signal=%s interval=%s",
                    sym_u,
                    raw_signal_norm,
                    str(interval or ""),
                )
        except Exception:
            pass

        try:
            self.close_position(
                symbol=sym_u,
                price=price,
                reason=f"signal_{raw_signal_norm}",
                interval=str(interval or ""),
                intent_id=str(
                    extra0.get("intent_id")
                    or ""
                ),
            )
        except Exception:
            try:
                if self.logger:
                    self.logger.exception(
                        "[EXEC][CLOSE] explicit close execution failed | "
                        "symbol=%s signal=%s",
                        sym_u,
                        raw_signal_norm,
                    )
            except Exception:
                pass

        return True

    def _prepare_long_decision_request(
        self,
        *,
        signal: str,
        symbol: str,
        price: float,
        size: Optional[float],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Long karar akışının değişmez giriş bağlamını hazırlar.

        Bu katman:
        - whale context'i çıkarır,
        - interval router değerlerini çözer,
        - sembol ve ham sinyali normalize eder,
        - erken fiyat fallback zincirini uygular,
        - decision giriş logunu üretir.

        Entry, candidate veya order kararı vermez.
        """
        extra0 = self._extract_whale_context(
            extra
            if isinstance(extra, dict)
            else {}
        )

        decision_interval = str(
            os.getenv(
                "DECISION_INTERVAL",
                os.getenv("INTERVAL", "3m"),
            )
            or "3m"
        ).strip() or "3m"

        entry_interval = str(
            os.getenv(
                "ENTRY_INTERVAL",
                os.getenv(
                    "SNIPER_ENTRY_INTERVAL",
                    "1m",
                ),
            )
            or "1m"
        ).strip() or "1m"

        exit_interval = str(
            os.getenv(
                "EXIT_INTERVAL",
                os.getenv(
                    "SCALP_EXIT_INTERVAL",
                    "1m",
                ),
            )
            or "1m"
        ).strip() or "1m"

        lifecycle_interval = str(
            os.getenv(
                "LIFECYCLE_INTERVAL",
                "3m",
            )
            or "3m"
        ).strip() or "3m"

        interval = decision_interval

        extra0["decision_interval"] = (
            decision_interval
        )
        extra0["entry_interval"] = (
            entry_interval
        )
        extra0["exit_interval"] = (
            exit_interval
        )
        extra0["lifecycle_interval"] = (
            lifecycle_interval
        )

        raw_signal = str(
            signal or ""
        ).strip().lower()

        sym_u = str(
            symbol
        ).upper().strip()

        try:
            price_f = float(
                price or 0.0
            )
        except Exception:
            price_f = 0.0

        if price_f <= 0.0:
            try:
                price_f = float(
                    extra0.get("price")
                    or extra0.get("close")
                    or extra0.get("last_price")
                    or extra0.get("mark_price")
                    or extra0.get("mid_price")
                    or 0.0
                )
            except Exception:
                price_f = 0.0

        if price_f <= 0.0:
            try:
                cached_px = (
                    self._get_cached_mid_price(
                        sym_u
                    )
                )

                if (
                    cached_px
                    and float(cached_px) > 0.0
                ):
                    price_f = float(
                        cached_px
                    )
            except Exception:
                pass

        resolved_price = price

        if price_f > 0.0:
            resolved_price = float(
                price_f
            )
            extra0["price"] = float(
                price_f
            )
            extra0["intent_price"] = float(
                price_f
            )

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][DECISION] enter | "
                    "symbol=%s signal=%s interval=%s "
                    "entry_interval=%s exit_interval=%s "
                    "lifecycle_interval=%s price=%s "
                    "size=%s extra_keys=%s",
                    sym_u,
                    str(signal),
                    str(decision_interval),
                    str(entry_interval),
                    str(exit_interval),
                    str(lifecycle_interval),
                    str(resolved_price),
                    str(size),
                    sorted(
                        list(
                            (extra or {}).keys()
                        )
                    )
                    if isinstance(extra, dict)
                    else [],
                )
        except Exception:
            pass

        return {
            "extra": extra0,
            "raw_signal": raw_signal,
            "symbol": sym_u,
            "price": resolved_price,
            "decision_interval": (
                decision_interval
            ),
            "entry_interval": (
                entry_interval
            ),
            "exit_interval": (
                exit_interval
            ),
            "lifecycle_interval": (
                lifecycle_interval
            ),
            "interval": interval,
        }

    def _apply_long_hold_conversion(
        self,
        *,
        signal: str,
        raw_signal: str,
        symbol: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str]:
        """
        Uygun whale ve model bağlamında HOLD sinyalini LONG'a dönüştürür.

        Mevcut davranışı korur:
        - yalnızca raw_signal == "hold" iken değerlendirilir,
        - whale_dir long olmalıdır,
        - whale_score en az 0.15 olmalıdır,
        - p_buy_ema 0.50 üzerinde olmalıdır.

        Her hata durumunda orijinal signal/raw_signal değerleri döner.
        """
        signal_out = signal
        raw_signal_out = str(
            raw_signal or ""
        ).strip().lower()

        extra0 = (
            extra
            if isinstance(extra, dict)
            else {}
        )

        try:
            if raw_signal_out == "hold":
                whale_dir_h = str(
                    extra0.get("whale_dir")
                    or ""
                ).strip().lower()

                whale_score_h = float(
                    extra0.get(
                        "whale_score",
                        0.0,
                    )
                    or 0.0
                )

                p_buy_h = float(
                    extra0.get(
                        "p_buy_ema",
                        0.5,
                    )
                    or 0.5
                )

                if (
                    whale_dir_h == "long"
                    and whale_score_h >= 0.15
                    and p_buy_h > 0.50
                ):
                    signal_out = "long"
                    raw_signal_out = "long"

                    if self.logger:
                        self.logger.info(
                            "[EXEC][HOLD→LONG] "
                            "symbol=%s p_buy=%.3f "
                            "whale_score=%.3f",
                            str(symbol or "").upper().strip(),
                            p_buy_h,
                            whale_score_h,
                        )
        except Exception:
            pass

        return (
            signal_out,
            raw_signal_out,
        )

    def _resolve_long_whale_open_context(
        self,
        *,
        symbol: str,
        raw_signal: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Long karar akışında kullanılacak whale open bağlamını hazırlar.

        Bu katman yalnızca:
        - whale context logunu üretir,
        - whale action/direction/score değerlerini normalize eder.

        Whale policy, entry veya order kararı vermez.
        """
        sym_u = str(
            symbol or ""
        ).upper().strip()

        extra0 = (
            extra
            if isinstance(extra, dict)
            else {}
        )

        raw_signal_norm = str(
            raw_signal or ""
        ).strip().lower()

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][WHALE][CTX] "
                    "symbol=%s side=%s "
                    "whale_dir=%s whale_score=%.4f "
                    "keys=%s",
                    sym_u,
                    raw_signal_norm,
                    str(
                        extra0.get("whale_dir")
                        or "none"
                    ),
                    float(
                        extra0.get("whale_score")
                        or 0.0
                    ),
                    sorted(
                        list(
                            extra0.keys()
                        )
                    ),
                )
        except Exception:
            pass

        whale_action = str(
            self._whale_action(
                extra0
            )
            or ""
        ).strip().lower()

        whale_dir = str(
            extra0.get(
                "whale_dir",
                "none",
            )
            or "none"
        ).strip().lower()

        whale_score = float(
            extra0.get(
                "whale_score",
                0.0,
            )
            or 0.0
        )

        if whale_dir in (
            "buy",
            "bull",
            "up",
        ):
            whale_dir = "long"
        elif whale_dir in (
            "sell",
            "bear",
            "down",
        ):
            whale_dir = "short"
        elif whale_dir not in (
            "long",
            "short",
        ):
            whale_dir = "none"

        return {
            "whale_action": whale_action,
            "whale_dir": whale_dir,
            "whale_score": float(
                whale_score
            ),
        }

    def _resolve_long_decision_signal_context(
        self,
        *,
        signal: str,
        raw_signal: str,
        symbol: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Long sinyalini normalize eder ve yön modunu doğrular."""
        sym_u = str(symbol or "").upper().strip()
        raw_signal_norm = str(raw_signal or "").strip().lower()
        extra0 = extra if isinstance(extra, dict) else {}

        signal_u = self._signal_u_from_any(signal)
        side_norm = self._normalize_side(signal_u)

        try:
            bot_side_mode = str(
                os.getenv("BOT_SIDE_MODE", "both") or "both"
            ).strip().lower()
        except Exception:
            bot_side_mode = "both"

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][SIDE-DEBUG] symbol=%s mode=%s "
                    "raw_signal=%s signal_u=%s side_norm=%s "
                    "p_buy_raw=%s p_buy_ema=%s best_side=%s "
                    "signal_source=%s p_buy_source=%s "
                    "whale_dir=%s whale_score=%s",
                    sym_u,
                    bot_side_mode,
                    raw_signal_norm,
                    signal_u,
                    side_norm,
                    extra0.get("p_buy_raw"),
                    extra0.get("p_buy_ema"),
                    extra0.get("best_side"),
                    extra0.get("signal_source"),
                    extra0.get("p_buy_source"),
                    extra0.get("whale_dir"),
                    extra0.get("whale_score"),
                )
        except Exception:
            pass

        try:
            best_side = str(
                extra0.get("best_side") or ""
            ).strip().lower()

            p_buy_raw = float(
                extra0.get("p_buy_raw", 0.5) or 0.5
            )
            p_buy_ema = float(
                extra0.get("p_buy_ema", 0.5) or 0.5
            )

            override_enabled = str(
                os.getenv(
                    "LONG_BEST_SIDE_OVERRIDE_ENABLE",
                    "1",
                )
                or "1"
            ).strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )

            neutral_band = float(
                os.getenv(
                    "LONG_BEST_SIDE_OVERRIDE_NEUTRAL_BAND",
                    "0.01",
                )
                or 0.01
            )

            if (
                override_enabled
                and bot_side_mode == "long"
                and side_norm != "long"
                and best_side == "long"
                and abs(p_buy_raw - 0.5) <= neutral_band
                and abs(p_buy_ema - 0.5) <= neutral_band
            ):
                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][LONG-BEST-OVERRIDE] "
                            "symbol=%s raw_signal=%s old_side=%s "
                            "new_side=long p_buy_raw=%.4f "
                            "p_buy_ema=%.4f best_side=%s",
                            sym_u,
                            raw_signal_norm,
                            side_norm,
                            p_buy_raw,
                            p_buy_ema,
                            best_side,
                        )
                except Exception:
                    pass

                signal_u = "BUY"
                side_norm = "long"
        except Exception:
            pass

        side_allowed = True

        if (
            bot_side_mode == "long"
            and side_norm != "long"
        ):
            side_allowed = False

        elif (
            bot_side_mode == "short"
            and side_norm != "short"
        ):
            side_allowed = False

        if not side_allowed:
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][SIDE-MODE-BLOCK] "
                        "symbol=%s mode=%s side=%s",
                        sym_u,
                        bot_side_mode,
                        side_norm,
                    )
            except Exception:
                pass

        return {
            "signal_u": signal_u,
            "side_norm": side_norm,
            "bot_side_mode": bot_side_mode,
            "side_allowed": bool(side_allowed),
        }

    def _resolve_long_dynamic_model_threshold(
        self,
        *,
        symbol: str,
        side: str,
        signal_score: float,
        base_threshold: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """LONG conditional recovery threshold authority.

        Base threshold remains authoritative by default. A lower recovery floor
        is allowed only for the configured LONG symbol when fresh 3m structure
        context proves the locked research recovery condition. Missing/stale
        context never relaxes the threshold.
        """
        sym_u=str(symbol or "").upper().strip()
        side_norm=str(side or "").lower().strip()
        base=float(base_threshold)
        score=float(signal_score)
        enabled=str(os.getenv("LONG_DYNAMIC_MODEL_GATE_ENABLE","0") or "0").strip().lower() in ("1","true","yes","on")
        target=str(os.getenv("LONG_DYNAMIC_MODEL_GATE_SYMBOL","") or "").upper().strip()
        if not enabled or side_norm!="long" or (target and sym_u!=target):
            return {"threshold":base,"base_threshold":base,"mode":"base","recovery":False}
        try: floor=float(os.getenv("LONG_DYNAMIC_MODEL_GATE_FLOOR",str(base)) or base)
        except Exception: floor=base
        floor=min(base,max(0.0,floor))
        if score>=base or score<floor:
            return {"threshold":base,"base_threshold":base,"floor":floor,"mode":"base","recovery":False}
        try: min_hist=max(1,int(float(os.getenv("LONG_DYNAMIC_MODEL_GATE_MIN_HISTORY","80") or 80)))
        except Exception: min_hist=80
        try: min_atr=float(os.getenv("LONG_DYNAMIC_MODEL_GATE_MIN_ATR_RANK","0.60") or 0.60)
        except Exception: min_atr=0.60
        try: min_close=float(os.getenv("LONG_DYNAMIC_MODEL_GATE_MIN_CLOSE_LOC","0.25") or 0.25)
        except Exception: min_close=0.25
        try: min_wick=float(os.getenv("LONG_DYNAMIC_MODEL_GATE_MIN_LOWER_WICK_FRAC","0.25") or 0.25)
        except Exception: min_wick=0.25
        st={}
        try:
            if self.redis is not None and _read_binance_structure_shadow is not None:
                obj=_read_binance_structure_shadow(self.redis,sym_u)
                if isinstance(obj,dict): st=obj
        except Exception:
            st={}
        status=str(st.get("status") or "").upper()
        try: atr_rank=float(st.get("research_m3_atr_rank_240"))
        except Exception: atr_rank=float("nan")
        try: hist=int(float(st.get("research_m3_atr_rank_history") or 0))
        except Exception: hist=0
        try: close_loc=float(st.get("research_m3_close_loc"))
        except Exception: close_loc=float("nan")
        try: wick=float(st.get("research_m3_lower_wick_frac"))
        except Exception: wick=float("nan")
        fresh=status=="OK"
        recovery=bool(fresh and hist>=min_hist and math.isfinite(atr_rank) and atr_rank>=min_atr and ((math.isfinite(close_loc) and close_loc>=min_close) or (math.isfinite(wick) and wick>=min_wick)))
        threshold=floor if recovery else base
        try:
            if self.logger:
                self.logger.info("[EXEC][LONG-DYN-GATE] symbol=%s score=%.4f base=%.4f floor=%.4f effective=%.4f recovery=%s atr_rank=%s hist=%s close_loc=%s lower_wick=%s status=%s",sym_u,score,base,floor,threshold,recovery,str(atr_rank),hist,str(close_loc),str(wick),status or "MISSING")
        except Exception: pass
        return {"threshold":float(threshold),"base_threshold":base,"floor":floor,"mode":"recovery" if recovery else "base","recovery":recovery,"atr_rank":atr_rank,"history":hist,"close_loc":close_loc,"lower_wick_frac":wick,"context_status":status or "MISSING"}

    def _resolve_long_decision_open_score_context(
        self,
        *,
        symbol: str,
        side: str,
        extra: Optional[Dict[str, Any]] = None,
        probs: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Long open score bağlamını karar akışı için sadeleştirir."""
        extra0 = extra if isinstance(extra, dict) else {}
        probs0 = probs if isinstance(probs, dict) else {}

        long_open_context = self._resolve_long_open_context(
            symbol=str(symbol or "").upper().strip(),
            side=str(side or "").strip().lower(),
            extra=extra0,
            probs=probs0,
        )

        if not isinstance(long_open_context, dict):
            long_open_context = {}

        signal_score = float(
            long_open_context.get("signal_score")
            or 0.0
        )

        open_min_score = float(
            long_open_context.get("open_min_score")
            or 0.0
        )
        dyn_enabled = str(os.getenv("LONG_DYNAMIC_MODEL_GATE_ENABLE","0") or "0").strip().lower() in ("1","true","yes","on")
        dyn_symbol = str(os.getenv("LONG_DYNAMIC_MODEL_GATE_SYMBOL","") or "").upper().strip()
        sym_u = str(symbol or "").upper().strip()
        if dyn_enabled and str(side or "").strip().lower()=="long" and (not dyn_symbol or sym_u==dyn_symbol):
            try:
                open_min_score=float(os.getenv(f"COIN_LONG_THRESHOLD_{sym_u}", os.getenv("LONG_THRESHOLD", str(open_min_score))) or open_min_score)
            except Exception:
                pass
        dyn_gate = self._resolve_long_dynamic_model_threshold(
            symbol=str(symbol or "").upper().strip(),
            side=str(side or "").strip().lower(),
            signal_score=signal_score,
            base_threshold=open_min_score,
            extra=extra0,
        )
        open_min_score=float(dyn_gate.get("threshold") or open_min_score)
        long_open_context=dict(long_open_context)
        long_open_context["dynamic_model_gate"]=dict(dyn_gate)
        long_open_context["open_min_score"]=open_min_score

        return {
            "context": long_open_context,
            "signal_score": signal_score,
            "open_min_score": open_min_score,
            "dynamic_model_gate": dyn_gate,
        }


    def _update_long_decision_snapshot(
        self,
        *,
        symbol: str,
        interval: str,
        signal_u: str,
        side: str,
        signal_score: float,
        whale_action: str,
        whale_dir: str,
        whale_score: float,
        probs: Optional[Dict[str, float]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Son long karar snapshot kaydını günceller."""
        sym_u = str(symbol or "").upper().strip()
        side_norm = str(side or "").strip().lower()
        extra0 = extra if isinstance(extra, dict) else {}
        probs0 = probs if isinstance(probs, dict) else {}

        try:
            p_used = extra0.get("ensemble_p")

            if p_used is None:
                p_used = (
                    extra0.get("p_buy_ema")
                    or extra0.get("p_buy_raw")
                )

            if p_used is None:
                p_used = (
                    probs0.get("p_used")
                    or probs0.get("p_single")
                )

            snapshot = {
                "ts": datetime.utcnow().isoformat(),
                "ts_epoch": time.time(),
                "symbol": sym_u,
                "interval": interval,
                "signal": signal_u,
                "signal_norm": side_norm,
                "signal_source": str(
                    extra0.get("signal_source")
                    or extra0.get("p_buy_source")
                    or ""
                ),
                "p_used": p_used,
                "p_single": probs0.get("p_single"),
                "p_buy_raw": extra0.get("p_buy_raw"),
                "p_buy_ema": extra0.get("p_buy_ema"),
                "whale_dir": whale_dir,
                "whale_score": whale_score,
                "whale_action": whale_action,
                "signal_score": float(signal_score),
                "extra": extra0,
            }

            self.last_snapshot = snapshot
            self.last_snapshot_by_symbol[sym_u] = snapshot
        except Exception:
            pass

    def _handle_long_hold_signal(
        self,
        *,
        symbol: str,
        price: float,
        interval: str,
        signal_score: float,
        whale_action: str,
        whale_dir: str,
        whale_score: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """HOLD sinyalinde telemetry, kayıt ve takip işlemlerini yürütür."""
        sym_u = str(symbol or "").upper().strip()
        extra0 = extra if isinstance(extra, dict) else {}

        try:
            ens = extra0.get("ensemble_p")
            mcf = extra0.get("model_confidence_factor")
            pbe = extra0.get("p_buy_ema")
            pbr = extra0.get("p_buy_raw")

            p_val = (
                ens
                if ens is not None
                else (pbe if pbe is not None else pbr)
            )

            p_src = (
                "ensemble_p"
                if ens is not None
                else (
                    "p_buy_ema"
                    if pbe is not None
                    else (
                        "p_buy_raw"
                        if pbr is not None
                        else "none"
                    )
                )
            )

            pv = self._clip_float(p_val, None)

            if pv is not None:
                pv = max(0.0, min(1.0, pv))

            self._append_hold_csv({
                "timestamp": datetime.utcnow().isoformat(),
                "symbol": sym_u,
                "interval": interval,
                "signal": "HOLD",
                "p": pv,
                "p_source": p_src,
                "ensemble_p": ens,
                "model_confidence_factor": mcf,
                "p_buy_ema": pbe,
                "p_buy_raw": pbr,
            })
        except Exception:
            pass

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC] Signal=HOLD symbol=%s "
                    "whale_action=%s whale_dir=%s "
                    "whale_score=%.3f signal_score=%.4f",
                    sym_u,
                    whale_action or "-",
                    whale_dir,
                    float(whale_score),
                    float(signal_score),
                )
        except Exception:
            pass

    def _evaluate_long_candidate_base_precheck(
        self,
        *,
        symbol: str,
        side: str,
        training_mode: bool,
        signal_score: float,
        open_min_score: float,
    ) -> bool:
        """
        Temel long candidate açılış ön kontrollerini uygular.

        True:
            Candidate akışı devam edebilir.

        False:
            Shadow, training, geçersiz yön veya düşük skor
            nedeniyle candidate engellenmelidir.
        """
        sym_u = str(symbol or "").upper().strip()
        side_norm = str(side or "").strip().lower()

        if self._truthy_env("SHADOW_MODE", "0"):
            return False

        if training_mode:
            return False

        if side_norm not in ("long", "short"):
            return False

        if float(signal_score) < float(open_min_score):
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][OPEN-BLOCK] low score | "
                        "symbol=%s side=%s signal_score=%.4f "
                        "min_open=%.4f",
                        sym_u,
                        side_norm,
                        float(signal_score),
                        float(open_min_score),
                    )
            except Exception:
                pass

            return False

        return True

    def _resolve_long_entry_market_context(
        self,
        *,
        price: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Long entry kararı için ortak piyasa bağlamını çözer."""
        extra0 = extra if isinstance(extra, dict) else {}

        def as_float(*values: Any) -> float:
            try:
                for value in values:
                    if value is not None:
                        return float(value)
            except Exception:
                pass
            return 0.0

        def as_optional_float(*values: Any) -> Optional[float]:
            for value in values:
                if value is None:
                    continue
                try:
                    return float(value)
                except Exception:
                    continue
            return None

        candle_progress = as_float(
            extra0.get("candle_progress")
        )
        candle_change = as_float(
            extra0.get("candle_change_pct")
        )
        # Entry Confirmation öncelikle ENTRY_INTERVAL
        # candle context'ini kullanır.
        # Legacy candle_* yalnız fallback olarak korunur.
        candle_open = as_float(
            extra0.get("entry_candle_open"),
            extra0.get("candle_open"),
            extra0.get("open"),
        )
        candle_high = as_float(
            extra0.get("entry_candle_high"),
            extra0.get("candle_high"),
            extra0.get("high"),
        )
        candle_low = as_float(
            extra0.get("entry_candle_low"),
            extra0.get("candle_low"),
            extra0.get("low"),
        )
        candle_close = as_float(
            extra0.get("entry_candle_close"),
            extra0.get("candle_close"),
            extra0.get("close"),
            price,
        )
        px_now = as_float(
            price,
            extra0.get("price"),
            extra0.get("close"),
            extra0.get("last_price"),
            extra0.get("mark_price"),
            extra0.get("mid_price"),
        )
        atr_val = as_float(
            extra0.get("atr")
        )

        atr_pct = as_optional_float(
            extra0.get("atr_pct")
        )
        spread_pct = as_optional_float(
            extra0.get("spread_pct")
        )
        confidence = as_optional_float(
            extra0.get("confidence")
        )
        micro_score = as_optional_float(
            extra0.get("micro_score")
        )
        liq_score = as_optional_float(
            extra0.get("liq_score")
        )

        try:
            whale_dir_now = str(
                extra0.get("whale_dir")
                or ""
            ).strip().lower()
        except Exception:
            whale_dir_now = ""

        whale_score_now = as_float(
            extra0.get("whale_score")
        )

        return {
            "candle_progress": candle_progress,
            "candle_change": candle_change,
            "candle_open": candle_open,
            "candle_high": candle_high,
            "candle_low": candle_low,
            "candle_close": candle_close,
            "entry_candle_interval": str(
                extra0.get("entry_candle_interval")
                or extra0.get("entry_interval")
                or ""
            ),
            "entry_context_source": str(
                extra0.get("entry_context_source")
                or "legacy"
            ),
            "px_now": px_now,
            "atr_val": atr_val,
            "atr_pct": atr_pct,
            "spread_pct": spread_pct,
            "confidence": confidence,
            "micro_score": micro_score,
            "liq_score": liq_score,
            "whale_dir_now": whale_dir_now,
            "whale_score_now": whale_score_now,
        }



    def _evaluate_long_execution_risk_gate(
        self, *, symbol, side, price, interval, extra=None,
    ):
        sym_u = str(symbol or "").upper().strip()
        side_norm = str(side or "").strip().lower()
        cur = self._get_effective_position(sym_u)
        cur_side = str(cur.get("side")).lower().strip() if isinstance(cur, dict) else None
        if cur_side in ("long", "short"):
            if cur_side == side_norm:
                scale_in_enable = (
                    side_norm == "long"
                    and str(os.getenv("LONG_SCALE_IN_ENABLE", "0") or "0").strip().lower()
                    in ("1", "true", "yes", "on")
                )
                try:
                    current_layers = max(1, int(cur.get("entry_layers") or 1))
                except Exception:
                    current_layers = 1
                try:
                    max_layers = max(1, int(float(os.getenv("LONG_MAX_ENTRY_LAYERS", "1") or 1)))
                except Exception:
                    max_layers = 1
                try:
                    scale_floor = float(os.getenv("LONG_SCALE_IN_SCORE_FLOOR", "0.5114") or 0.5114)
                except Exception:
                    scale_floor = 0.5114
                extra0 = extra if isinstance(extra, dict) else {}
                incoming_score = 0.0
                for _k in ("signal_score", "score", "score_total", "_score_total_final", "_score_selected"):
                    try:
                        incoming_score = max(incoming_score, float(extra0.get(_k) or 0.0))
                    except Exception:
                        pass
                if scale_in_enable and current_layers < max_layers and incoming_score >= scale_floor:
                    try:
                        if self.logger:
                            self.logger.info(
                                "[EXEC][SCALE-IN][ALLOW] symbol=%s side=%s layers=%s/%s score=%.4f floor=%.4f",
                                sym_u, side_norm, current_layers, max_layers, incoming_score, scale_floor,
                            )
                    except Exception:
                        pass
                    return True
                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][OPEN-BLOCK] symbol already open same-side | symbol=%s current=%s incoming=%s layers=%s/%s score=%.4f",
                            sym_u, cur_side, side_norm, current_layers, max_layers, incoming_score,
                        )
                except Exception:
                    pass
                return False

            # ==================================================
            # POSITION OWNERSHIP BOUNDARY
            #
            # Execution Risk yalnız incoming OPEN kararını
            # engeller. Mevcut pozisyonu kapatma yetkisi
            # POSITION LIFECYCLE katmanına aittir.
            #
            # Canonical reverse close:
            # _evaluate_position_signal_exit()
            #   -> lifecycle evaluator
            #   -> _execute_lifecycle_close()
            # ==================================================
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][OPEN-BLOCK][OPPOSITE] "
                        "existing opposite-side position is owned "
                        "by position lifecycle | "
                        "symbol=%s current=%s incoming=%s",
                        sym_u,
                        cur_side,
                        side_norm,
                    )
            except Exception:
                pass

            return False
        try:
            open_count = int(self._count_open_positions_for_side(side_norm))
            if open_count >= int(self.max_open_positions):
                if self.logger:
                    self.logger.info("[EXEC][OPEN-BLOCK] max_open_positions reached | symbol=%s side=%s side_open_count=%s limit=%s", sym_u, side_norm, open_count, int(self.max_open_positions))
                return False
        except Exception:
            pass
        return True


    def _resolve_long_intent_price(self, *, symbol, price, extra=None):
        sym_u = str(symbol or "").upper().strip()
        extra0 = extra if isinstance(extra, dict) else {}
        intent_price = self._resolve_price(symbol=sym_u, price=price, mark_price=extra0.get("mark_price"), last_price=extra0.get("last_price"))
        if intent_price is None or intent_price <= 0:
            try:
                if self.logger:
                    self.logger.info("[EXEC][PRICECACHE-FALLBACK][TRY] symbol=%s", sym_u)
                intent_price = self._get_cached_mid_price(sym_u)
                if self.logger:
                    self.logger.info("[EXEC][PRICECACHE-FALLBACK][RESULT] symbol=%s price=%s", sym_u, intent_price)
                if intent_price and intent_price > 0 and self.logger:
                    self.logger.info("[EXEC][PRICECACHE-FALLBACK] symbol=%s price=%.8f", sym_u, float(intent_price))
            except Exception as e:
                if self.logger:
                    self.logger.warning("[EXEC][PRICECACHE-FALLBACK][ERR] symbol=%s err=%s", sym_u, e)
                intent_price = None
        return intent_price


    def _resolve_long_order_price(self, *, symbol, price, intent_price, extra=None):
        sym_u = str(symbol or "").upper().strip()
        extra0 = extra if isinstance(extra, dict) else {}
        order_price = None
        try:
            client = getattr(self, "client", None)
            fn = getattr(client, "futures_mark_price", None) if client is not None else None
            if callable(fn):
                mp = fn(symbol=sym_u)
                if isinstance(mp, dict):
                    order_price = self._clip_float(mp.get("markPrice"), None)
        except Exception:
            order_price = None
        if order_price is None or order_price <= 0:
            try:
                order_price = self._get_cached_mid_price(sym_u)
            except Exception:
                order_price = None
        if order_price is None or order_price <= 0:
            order_price = self._resolve_price(symbol=sym_u, price=price, mark_price=extra0.get("mark_price"), last_price=extra0.get("last_price"))
        if order_price is None or order_price <= 0:
            order_price = float(intent_price)
        return order_price


    async def _execute_long_order_pipeline(
        self, *, symbol, side, order_price, intent_price,
        signal_score, decision_interval, entry_interval,
        exit_interval, lifecycle_interval, extra=None,
    ):
        sym_u = str(symbol or "").upper().strip()
        extra0 = extra if isinstance(extra, dict) else {}
        return await asyncio.to_thread(
            self.open_position_from_signal,
            sym_u,
            str(side or "").strip().lower(),
            str(entry_interval or "1m"),
            dict(
                extra0,
                price=float(intent_price),
                signal_score=float(signal_score),
                decision_interval=str(decision_interval),
                entry_interval=str(entry_interval),
                exit_interval=str(exit_interval),
                lifecycle_interval=str(lifecycle_interval),
            ),
        )


    def _dispatch_long_candidate_decision(self, decision):
        """Candidate kararını standart LONG EntryDecision formatına çevirir."""
        normalized = self._normalize_long_entry_decision(decision)
        action = str(normalized.get("action") or "block").strip().lower()
        if action not in ("open", "block", "pending", "close", "hold"):
            return self._make_long_entry_decision(
                allow=False,
                action="block",
                reason="invalid_candidate_action",
                retryable=False,
            )

        details = normalized.get("details")
        details = details if isinstance(details, dict) else {}

        try:
            if self.logger:
                self.logger.info(
                    "[EXEC][ENTRY-DECISION] "
                    "action=%s reason=%s retryable=%s "
                    "score=%s required=%s "
                    "proposed=%s quality=%s body=%s retrace=%s "
                    "support=%s span=%s has_span=%s "
                    "atr_rev=%s mode=%s shadow=%s "
                    "entry_itv=%s ctx_source=%s",
                    action,
                    str(normalized.get("reason") or ""),
                    bool(normalized.get("retryable", False)),
                    normalized.get("score"),
                    normalized.get("required_score"),
                    details.get("proposed_action"),
                    details.get("entry_quality"),
                    details.get("body_ratio"),
                    details.get("retrace_ratio"),
                    details.get("direction_support"),
                    details.get("directional_span"),
                    details.get("has_directional_span"),
                    details.get("atr_reversal"),
                    details.get("context_mode"),
                    details.get("shadow"),
                    details.get("entry_candle_interval"),
                    details.get("entry_context_source"),
                )
        except Exception:
            pass

        return normalized


    def _store_long_pending_candidate(
        self, *, symbol, side, decision, interval="1m", extra=None,
    ):
        sym_u = str(symbol or "").upper().strip()
        side_norm = str(side or "").strip().lower()
        interval_norm = str(interval or "1m").strip().lower()
        normalized = self._normalize_long_entry_decision(decision)
        created_ts = float(time.time())
        item = {
            "symbol": sym_u,
            "side": side_norm,
            "decision": normalized,
            "created_ts": created_ts,
            "interval": interval_norm,
            "candle_id": int(self._get_long_candle_id(interval_norm, created_ts)),
            "extra": dict(extra) if isinstance(extra, dict) else {},
        }
        self.long_pending_by_symbol[sym_u] = item
        return item



    def _clear_long_pending_candidate(self, *, symbol):
        sym_u = str(symbol or "").upper().strip()
        if not sym_u:
            return None
        return self.long_pending_by_symbol.pop(sym_u, None)


    def _get_long_pending_candidate(self, *, symbol):
        sym_u = str(symbol or "").upper().strip()
        if not sym_u:
            return None
        item = self.long_pending_by_symbol.get(sym_u)
        return item if isinstance(item, dict) else None


    @staticmethod
    def _interval_to_seconds(interval: str) -> int:
        value = str(interval or "").strip().lower()
        if not value:
            return 60
        unit = value[-1]
        try:
            amount = int(value[:-1])
        except (TypeError, ValueError):
            return 60
        if amount <= 0:
            return 60
        multipliers = {
            "s": 1,
            "m": 60,
            "h": 60 * 60,
            "d": 24 * 60 * 60,
            "w": 7 * 24 * 60 * 60,
        }
        multiplier = multipliers.get(unit)
        if multiplier is None:
            return 60
        return int(amount * multiplier)


    def _get_long_candle_id(
        self, interval: str, timestamp=None,
    ) -> int:
        interval_sec = self._interval_to_seconds(interval)
        ts = float(time.time() if timestamp is None else timestamp)
        return int(ts // interval_sec)


    def _classify_long_pending_window(
        self, *, created_candle_id, current_candle_id,
        progress, max_pending_progress,
        pending_kind="late",
    ):
        created_id = int(created_candle_id or 0)
        current_id = int(current_candle_id or 0)
        if created_id <= 0 or current_id <= 0:
            return "invalid", 0

        candle_age = current_id - created_id
        if candle_age < 0:
            return "invalid", candle_age

        try:
            min_progress = float(
                os.getenv("SNIPER_ENTRY_MIN_CANDLE_PROGRESS", "0.08") or 0.08
            )
        except Exception:
            min_progress = 0.08

        progress_now = float(progress)
        max_progress = float(max_pending_progress)
        kind = str(pending_kind or "late").strip().lower()

        if kind == "confirmation":
            # Confirmation yalnız oluşturulduğu mum içinde
            # yeniden değerlendirilebilir.
            if candle_age > 0:
                return "expired", candle_age

            # Sniper timing authority korunur:
            # confirmation pending üzerinden mumun geç
            # bölümünde OPEN yapılamaz.
            if progress_now > max_progress:
                return "expired", candle_age

            if progress_now < min_progress:
                return "wait_same_candle", candle_age

            return "ready", candle_age

        if kind == "early":
            if candle_age > 0:
                return "expired", candle_age
            if progress_now < min_progress:
                return "wait_same_candle", candle_age
            if progress_now > max_progress:
                return "expired", candle_age
            return "ready", candle_age

        if candle_age <= 0:
            return "wait_same_candle", candle_age
        if candle_age > 1:
            return "expired", candle_age
        if (
            progress_now < min_progress
            or progress_now > max_progress
        ):
            return "wait_window", candle_age
        return "ready", candle_age


    def _check_long_pending_window(
        self, *, symbol, pending, current_candle_id,
        progress, max_pending_progress,
    ) -> bool:
        sym_u = str(symbol or "").upper().strip()
        created_candle_id = int(
            pending.get("candle_id") or 0
        ) if isinstance(pending, dict) else 0
        decision0 = (
            pending.get("decision")
            if isinstance(pending, dict)
            else {}
        )
        decision0 = (
            decision0
            if isinstance(decision0, dict)
            else {}
        )
        details0 = decision0.get("details")
        details0 = (
            details0
            if isinstance(details0, dict)
            else {}
        )
        pending_kind = str(
            details0.get("pending_kind")
            or "late"
        ).strip().lower()

        window_state, candle_age = (
            self._classify_long_pending_window(
                created_candle_id=created_candle_id,
                current_candle_id=current_candle_id,
                progress=progress,
                max_pending_progress=max_pending_progress,
                pending_kind=pending_kind,
            )
        )
        if window_state == "invalid":
            self._clear_long_pending_candidate(symbol=sym_u)
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][PENDING-CANCEL] symbol=%s reason=invalid_candle_id",
                        sym_u,
                    )
            except Exception:
                pass
            return False
        if window_state == "expired":
            self._clear_long_pending_candidate(symbol=sym_u)
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][PENDING-EXPIRE] symbol=%s created_candle=%s current_candle=%s age=%s",
                        sym_u,
                        created_candle_id,
                        current_candle_id,
                        candle_age,
                    )
            except Exception:
                pass
            return False
        return window_state == "ready"





    def _evaluate_long_entry_confirmation(
        self, *, side, signal_score, open_min_score,
        market_context,
    ):
        side_norm = str(side or "").strip().lower()
        ctx = (
            market_context
            if isinstance(market_context, dict)
            else {}
        )

        enabled = str(
            os.getenv("ENTRY_CONFIRM_ENABLE", "0")
        ).strip().lower() in ("1", "true", "yes", "on")

        if not enabled:
            return self._make_long_entry_decision(
                allow=True,
                action="open",
                reason="entry_confirmation_disabled",
                signal_score=signal_score,
                required_score=open_min_score,
                retryable=False,
            )

        shadow = str(
            os.getenv("ENTRY_CONFIRM_SHADOW", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

        min_body_ratio = float(
            os.environ["ENTRY_CONFIRM_MIN_BODY_RATIO"]
        )
        max_retrace_ratio = float(
            os.environ["ENTRY_CONFIRM_MAX_RETRACE_RATIO"]
        )
        reject_retrace_ratio = float(
            os.environ["ENTRY_CONFIRM_REJECT_RETRACE_RATIO"]
        )
        min_quality = float(
            os.environ["ENTRY_CONFIRM_MIN_QUALITY"]
        )

        if not (
            0.0 <= min_body_ratio <= 1.0
            and 0.0 <= max_retrace_ratio < reject_retrace_ratio <= 1.0
            and 0.0 <= min_quality <= 1.0
        ):
            raise RuntimeError(
                "invalid ENTRY_CONFIRM configuration: "
                f"min_body={min_body_ratio} "
                f"max_retrace={max_retrace_ratio} "
                f"reject_retrace={reject_retrace_ratio} "
                f"min_quality={min_quality}"
            )

        px = float(ctx.get("px_now") or 0.0)
        op = float(ctx.get("candle_open") or 0.0)
        hi = float(ctx.get("candle_high") or 0.0)
        lo = float(ctx.get("candle_low") or 0.0)

        if px > 0.0:
            if hi > 0.0:
                hi = max(hi, px)
            if lo > 0.0:
                lo = min(lo, px)

        has_ohlc = (
            px > 0.0
            and op > 0.0
            and hi > lo > 0.0
            and lo <= op <= hi
        )

        if not has_ohlc:
            details = {
                "context_mode": "limited",
                "shadow": shadow,
                "proposed_action": "pending",
                "pending_kind": "confirmation",
                "entry_quality": None,
                "body_ratio": None,
                "retrace_ratio": None,
                "location_ratio": None,
                "direction_support": None,
                "atr_reversal": None,
                "entry_candle_interval": str(
                    ctx.get("entry_candle_interval")
                    or ""
                ),
                "entry_context_source": str(
                    ctx.get("entry_context_source")
                    or ""
                ),
            }

            if shadow:
                return self._make_long_entry_decision(
                    allow=True,
                    action="open",
                    reason="entry_confirmation_shadow",
                    signal_score=signal_score,
                    required_score=open_min_score,
                    retryable=False,
                    details=details,
                )

            return self._make_long_entry_decision(
                allow=False,
                action="pending",
                reason="entry_confirmation_limited_data",
                signal_score=signal_score,
                required_score=open_min_score,
                retryable=True,
                details=details,
            )

        candle_range = hi - lo
        body_ratio = abs(px - op) / candle_range

        if side_norm == "long":
            direction_support = px >= op
            reversal_abs = max(0.0, hi - px)
            directional_span = max(0.0, hi - op)
            location_ratio = (px - lo) / candle_range
        else:
            direction_support = px <= op
            reversal_abs = max(0.0, px - lo)
            directional_span = max(0.0, op - lo)
            location_ratio = (hi - px) / candle_range

        has_directional_span = (
            directional_span > 0.0
        )

        retrace_ratio = (
            min(
                1.0,
                reversal_abs / directional_span,
            )
            if has_directional_span
            else 0.0
        )

        body_quality = min(
            1.0,
            body_ratio / max(min_body_ratio, 1e-9),
        )
        retrace_quality = max(
            0.0,
            1.0 - retrace_ratio,
        )
        direction_quality = 1.0 if direction_support else 0.0
        location_quality = max(
            0.0,
            min(1.0, location_ratio),
        )

        entry_quality = (
            0.30 * direction_quality
            + 0.25 * body_quality
            + 0.25 * retrace_quality
            + 0.20 * location_quality
        )

        atr_abs = float(ctx.get("atr_val") or 0.0)
        atr_pct = ctx.get("atr_pct")
        if atr_abs <= 0.0 and atr_pct is not None:
            try:
                atr_abs = px * float(atr_pct)
            except Exception:
                atr_abs = 0.0

        atr_reversal = (
            reversal_abs / atr_abs
            if atr_abs > 0.0
            else None
        )

        proposed_action = "open"
        reason = "entry_confirmation_ready"
        retryable = False

        if not has_directional_span:
            proposed_action = "pending"
            reason = "entry_confirmation_no_directional_span"
            retryable = True

        elif retrace_ratio >= reject_retrace_ratio:
            proposed_action = "block"
            reason = "entry_confirmation_strong_reversal"

        elif (
            not direction_support
            or retrace_ratio >= max_retrace_ratio
            or body_ratio < min_body_ratio
            or entry_quality < min_quality
        ):
            proposed_action = "pending"
            reason = "entry_confirmation_wait"
            retryable = True

        details = {
            "context_mode": "full",
            "shadow": shadow,
            "proposed_action": proposed_action,
            "entry_quality": round(entry_quality, 6),
            "body_ratio": round(body_ratio, 6),
            "retrace_ratio": round(retrace_ratio, 6),
            "location_ratio": round(location_ratio, 6),
            "direction_support": bool(direction_support),
            "directional_span": round(
                directional_span,
                12,
            ),
            "has_directional_span": bool(
                has_directional_span
            ),
            "entry_candle_interval": str(
                ctx.get("entry_candle_interval")
                or ""
            ),
            "entry_context_source": str(
                ctx.get("entry_context_source")
                or ""
            ),
            "atr_reversal": (
                round(atr_reversal, 6)
                if atr_reversal is not None
                else None
            ),
        }

        if proposed_action == "pending":
            details["pending_kind"] = "confirmation"

        if shadow:
            return self._make_long_entry_decision(
                allow=True,
                action="open",
                reason="entry_confirmation_shadow",
                signal_score=signal_score,
                required_score=open_min_score,
                retryable=False,
                details=details,
            )

        return self._make_long_entry_decision(
            allow=(proposed_action == "open"),
            action=proposed_action,
            reason=reason,
            signal_score=signal_score,
            required_score=open_min_score,
            retryable=retryable,
            details=details,
        )


    def _evaluate_long_candidate_pipeline(
        self, *, symbol, side, price, signal_score,
        open_min_score, extra=None,
    ):
        sym_u = str(symbol or "").upper().strip()
        side_norm = str(side or "").strip().lower()
        extra0 = extra if isinstance(extra, dict) else {}
        entry_market_context = self._resolve_long_entry_market_context(
            price=price,
            extra=extra0,
        )
        candle_progress = float(entry_market_context["candle_progress"])
        candle_change = float(entry_market_context["candle_change"])
        candle_open = float(entry_market_context["candle_open"])
        candle_close = float(entry_market_context["candle_close"])
        atr_val = float(entry_market_context["atr_val"])
        px_now = float(entry_market_context["px_now"])
        candle_high = float(entry_market_context["candle_high"])
        candle_low = float(entry_market_context["candle_low"])



        return self._evaluate_long_entry_confirmation(
            side=side_norm,
            signal_score=signal_score,
            open_min_score=open_min_score,
            market_context=entry_market_context,
        )


    def _handle_long_pending_candidate_result(
        self, *, symbol, candidate,
        signal_score, min_score,
    ) -> bool:
        sym_u = str(symbol or "").upper().strip()
        normalized = self._normalize_long_entry_decision(candidate)
        if normalized.get("allow", False):
            return False
        reason = str(
            normalized.get("reason") or "candidate_block"
        ).strip().lower()
        retryable = bool(normalized.get("retryable", False))
        if not retryable:
            self._clear_long_pending_candidate(symbol=sym_u)
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][PENDING-CANCEL] symbol=%s reason=%s score=%.4f min=%.4f",
                        sym_u, reason, float(signal_score), float(min_score),
                    )
            except Exception:
                pass
        else:
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][PENDING-WAIT] symbol=%s reason=%s retryable=true",
                        sym_u, reason,
                    )
            except Exception:
                pass
        return True


    def _prepare_long_pending_candidate(
        self, *, symbol, pending,
    ):
        sym_u = str(symbol or "").upper().strip()
        if not isinstance(pending, dict):
            return None
        decision0 = pending.get("decision")
        decision0 = decision0 if isinstance(decision0, dict) else {}
        try:
            pending_score = float(decision0.get("score") or 0.0)
        except Exception:
            pending_score = 0.0
        try:
            pending_min_score = float(decision0.get("required_score") or 0.0)
        except Exception:
            pending_min_score = 0.0
        extra0 = pending.get("extra")
        extra0 = extra0 if isinstance(extra0, dict) else {}
        pending_price = self._resolve_long_intent_price(
            symbol=sym_u,
            price=extra0.get("price"),
            extra=extra0,
        )
        if pending_price is None or pending_price <= 0:
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][PENDING-WAIT] symbol=%s reason=missing_price",
                        sym_u,
                    )
            except Exception:
                pass
            return None
        candidate = self._evaluate_long_candidate_pipeline(
            symbol=sym_u,
            side=str(pending.get("side") or "").strip().lower(),
            price=float(pending_price),
            signal_score=pending_score,
            open_min_score=pending_min_score,
            extra=extra0,
        )
        candidate = self._dispatch_long_candidate_decision(candidate)
        return (
            float(pending_price),
            pending_score,
            pending_min_score,
            candidate,
        )


    def _process_long_pending_candidate(
        self, *, symbol, pending, current_candle_id,
        progress, max_pending_progress,
    ):
        sym_u = str(symbol or "").upper().strip()

        window_ok = self._check_long_pending_window(
            symbol=sym_u,
            pending=pending,
            current_candle_id=current_candle_id,
            progress=progress,
            max_pending_progress=max_pending_progress,
        )

        if not window_ok:
            still_pending = self._get_long_pending_candidate(
                symbol=sym_u
            )
            if still_pending is None:
                return {"status": "cleared"}
            return {"status": "wait"}

        prepared = self._prepare_long_pending_candidate(
            symbol=sym_u,
            pending=pending,
        )

        if prepared is None:
            return {"status": "wait"}

        (
            pending_price,
            pending_score,
            pending_min_score,
            candidate,
        ) = prepared

        if self._handle_long_pending_candidate_result(
            symbol=sym_u,
            candidate=candidate,
            signal_score=pending_score,
            min_score=pending_min_score,
        ):
            still_pending = self._get_long_pending_candidate(
                symbol=sym_u
            )
            return {
                "status": (
                    "wait"
                    if still_pending is not None
                    else "blocked"
                )
            }

        return {
            "status": "ready",
            "price": float(pending_price),
            "signal_score": float(pending_score),
            "min_score": float(pending_min_score),
            "candidate": candidate,
        }


    def _evaluate_long_sniper_timing_decision(
        self, *, symbol, side, entry_interval,
        signal_score, open_min_score, allow_pending=True,
    ):
        sym_u = str(symbol or "").upper().strip()
        side_norm = str(side or "").strip().lower()
        try:
            sniper_enable = str(
                os.getenv("SNIPER_ENTRY_ENABLE", "0")
            ).strip().lower() in ("1", "true", "yes", "on")
            if not sniper_enable or side_norm not in ("long", "short"):
                return None
            max_progress = float(
                os.getenv("SNIPER_ENTRY_MAX_CANDLE_PROGRESS", "0.55") or 0.55
            )
            min_progress = float(
                os.getenv("SNIPER_ENTRY_MIN_CANDLE_PROGRESS", "0.08") or 0.08
            )
            interval_sec = float(
                self._interval_to_seconds(str(entry_interval or "1m"))
            )
            progress = (time.time() % interval_sec) / max(interval_sec, 1.0)
            if progress > max_progress:
                return self._make_long_entry_decision(
                    allow=False,
                    action="pending" if allow_pending else "block",
                    reason="sniper_window_passed" if allow_pending else "pending_window_passed",
                    signal_score=signal_score,
                    required_score=open_min_score,
                    progress=progress,
                    retryable=bool(allow_pending),
                    details={
                        "pending_kind": "late",
                    },
                )
            if progress < min_progress:
                return self._make_long_entry_decision(
                    allow=False,
                    action="pending" if allow_pending else "block",
                    reason="sniper_window_early",
                    signal_score=signal_score,
                    required_score=open_min_score,
                    progress=progress,
                    retryable=bool(allow_pending),
                    details={
                        "pending_kind": "early",
                    },
                )
            return None
        except Exception as exc:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC][SNIPER-DECISION][WARN] symbol=%s side=%s err=%s",
                        sym_u, side_norm, str(exc)[:200],
                    )
            except Exception:
                pass
            return None


    async def _execute_long_validated_candidate(
        self, *, symbol, side, price, signal_score,
        decision_interval, entry_interval,
        exit_interval, lifecycle_interval,
        interval, extra=None, signal_label="",
    ) -> bool:
        sym_u = str(symbol or "").upper().strip()
        side_norm = str(side or "").strip().lower()
        extra0 = extra if isinstance(extra, dict) else {}

        if not self._evaluate_long_execution_risk_gate(
            symbol=sym_u,
            side=side_norm,
            price=price,
            interval=str(interval or ""),
            extra=extra0,
        ):
            return False

        intent_price = self._resolve_long_intent_price(
            symbol=sym_u,
            price=price,
            extra=extra0,
        )

        if intent_price is None or intent_price <= 0:
            try:
                if self.logger:
                    self.logger.warning(
                        "[EXEC] live_price unavailable -> skip | "
                        "symbol=%s signal=%s",
                        sym_u,
                        str(signal_label or ""),
                    )
            except Exception:
                pass

            return False

        order_price = self._resolve_long_order_price(
            symbol=sym_u,
            price=price,
            intent_price=intent_price,
            extra=extra0,
        )

        order_result = await self._execute_long_order_pipeline(
            symbol=sym_u,
            side=side_norm,
            order_price=order_price,
            intent_price=intent_price,
            signal_score=signal_score,
            decision_interval=decision_interval,
            entry_interval=entry_interval,
            exit_interval=exit_interval,
            lifecycle_interval=lifecycle_interval,
            extra=extra0,
        )

        status = str(
            order_result.get("status")
            if isinstance(order_result, dict)
            else ""
        ).strip().lower()

        # Shadow telemetry only: remember the context that actually reached
        # a confirmed live OPEN. No order/risk decision is changed here.
        if status == "opened":
            try:
                if (
                    _mark_okx_oi_position_open_shadow is not None
                    and self.redis is not None
                ):
                    _mark_okx_oi_position_open_shadow(
                        self.redis,
                        symbol=sym_u,
                        side=side_norm,
                        entry_price=float(order_result.get("price") or order_price),
                        signal_score=float(signal_score),
                        intent_id=str(order_result.get("intent_id") or extra0.get("intent_id") or ""),
                        qty=float(order_result.get("qty") or 0.0),
                        notional=float(order_result.get("notional") or 0.0),
                        leverage=float(order_result.get("target_leverage") or extra0.get("target_leverage") or 1.0),
                        open_order_id=str(order_result.get("open_order_id") or ""),
                        open_client_order_id=str(order_result.get("open_client_order_id") or ""),
                    )
            except Exception:
                pass

        return status in (
            "opened",
            "dry_run",
        )


    async def execute_decision(
        self,
        signal: str,
        symbol: str,
        price: float,
        size: Optional[float],
        interval: str,
        training_mode: bool,
        hybrid_mode: bool,
        probs: Dict[str, float],
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        decision_request = self._prepare_long_decision_request(
            signal=signal,
            symbol=symbol,
            price=price,
            size=size,
            extra=extra,
        )

        extra0 = decision_request["extra"]
        raw_signal = str(
            decision_request["raw_signal"]
        )
        sym_u = str(
            decision_request["symbol"]
        )
        price = decision_request["price"]
        decision_interval = str(
            decision_request["decision_interval"]
        )
        entry_interval = str(
            decision_request["entry_interval"]
        )
        exit_interval = str(
            decision_request["exit_interval"]
        )
        lifecycle_interval = str(
            decision_request["lifecycle_interval"]
        )
        interval = str(
            decision_request["interval"]
        )

        signal, raw_signal = self._apply_long_hold_conversion(
            signal=signal,
            raw_signal=raw_signal,
            symbol=sym_u,
            extra=extra0,
        )

        whale_open_context = self._resolve_long_whale_open_context(
            symbol=sym_u,
            raw_signal=raw_signal,
            extra=extra0,
        )

        whale_action = str(
            whale_open_context["whale_action"]
        )
        whale_dir = str(
            whale_open_context["whale_dir"]
        )
        whale_score = float(
            whale_open_context["whale_score"]
        )

        if self._handle_long_explicit_close_signal(
            raw_signal=raw_signal,
            symbol=sym_u,
            price=price,
            interval=str(interval or ""),
            extra=extra0,
        ):
            return

        pending = self._get_long_pending_candidate(
            symbol=sym_u
        )

        # ---------------------------------------------------------
        # PENDING MODEL REVALIDATION
        # Eski pending side/score execution yetkisi taşıyamaz.
        # Güncel model sinyali ve güncel score yeniden doğrulanır.
        # ---------------------------------------------------------
        if isinstance(pending, dict):
            pending_side_check = str(
                pending.get("side") or ""
            ).strip().lower()

            current_signal_context = (
                self._resolve_long_decision_signal_context(
                    signal=signal,
                    raw_signal=raw_signal,
                    symbol=sym_u,
                    extra=extra0,
                )
            )

            current_side = str(
                current_signal_context["side_norm"]
            ).strip().lower()

            side_still_valid = (
                bool(current_signal_context["side_allowed"])
                and current_side == pending_side_check
            )

            if not side_still_valid:
                self._clear_long_pending_candidate(
                    symbol=sym_u
                )
                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][PENDING-CANCEL] "
                            "symbol=%s reason=stale_model_side "
                            "pending_side=%s current_side=%s",
                            sym_u,
                            pending_side_check,
                            current_side,
                        )
                except Exception:
                    pass
                pending = None

            else:
                current_score_context = (
                    self._resolve_long_decision_open_score_context(
                        symbol=sym_u,
                        side=current_side,
                        extra=extra0,
                        probs=probs,
                    )
                )

                current_score = float(
                    current_score_context["signal_score"]
                )
                current_min_score = float(
                    current_score_context["open_min_score"]
                )

                if current_score < current_min_score:
                    self._clear_long_pending_candidate(
                        symbol=sym_u
                    )
                    try:
                        if self.logger:
                            self.logger.info(
                                "[EXEC][PENDING-CANCEL] "
                                "symbol=%s reason=stale_model_score "
                                "score=%.4f min=%.4f",
                                sym_u,
                                current_score,
                                current_min_score,
                            )
                    except Exception:
                        pass
                    pending = None

                else:
                    pending_decision = pending.get("decision")
                    pending_decision = (
                        dict(pending_decision)
                        if isinstance(pending_decision, dict)
                        else {}
                    )
                    pending_decision["score"] = current_score
                    pending_decision["required_score"] = current_min_score
                    pending["decision"] = pending_decision

        if isinstance(pending, dict):
            pending_side = str(
                pending.get("side") or ""
            ).strip().lower()

            if pending_side not in ("long", "short"):
                self._clear_long_pending_candidate(
                    symbol=sym_u
                )
                pending = None

            else:
                pending_extra = pending.get("extra")
                pending_extra = (
                    dict(pending_extra)
                    if isinstance(pending_extra, dict)
                    else {}
                )
                pending_extra.update(extra0)
                pending_extra["price"] = price
                pending["extra"] = pending_extra

                pending_interval = str(
                    pending.get("interval")
                    or entry_interval
                    or "1m"
                ).strip().lower()

                interval_sec = float(
                    self._interval_to_seconds(
                        pending_interval
                    )
                )

                current_candle_id = (
                    self._get_long_candle_id(
                        pending_interval
                    )
                )

                pending_progress = (
                    time.time() % interval_sec
                ) / max(interval_sec, 1.0)

                pending_max_progress = float(
                    os.environ[
                        "SNIPER_ENTRY_MAX_CANDLE_PROGRESS"
                    ]
                )

                pending_result = (
                    self._process_long_pending_candidate(
                        symbol=sym_u,
                        pending=pending,
                        current_candle_id=current_candle_id,
                        progress=pending_progress,
                        max_pending_progress=pending_max_progress,
                    )
                )

                pending_status = str(
                    (pending_result or {}).get("status")
                    or "wait"
                ).strip().lower()

                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][PENDING-RECHECK] "
                            "symbol=%s side=%s status=%s "
                            "progress=%.3f max=%.3f",
                            sym_u,
                            pending_side,
                            pending_status,
                            float(pending_progress),
                            float(pending_max_progress),
                        )
                except Exception:
                    pass

                if pending_status in ("wait", "blocked"):
                    return

                if pending_status == "ready":
                    pending_price = float(
                        pending_result["price"]
                    )
                    pending_score = float(
                        pending_result["signal_score"]
                    )

                    executed = await self._execute_long_validated_candidate(
                        symbol=sym_u,
                        side=pending_side,
                        price=pending_price,
                        signal_score=pending_score,
                        decision_interval=decision_interval,
                        entry_interval=pending_interval,
                        exit_interval=exit_interval,
                        lifecycle_interval=lifecycle_interval,
                        interval=interval,
                        extra=pending_extra,
                        signal_label="pending_revalidated",
                    )

                    if executed:
                        self._clear_long_pending_candidate(
                            symbol=sym_u
                        )

                    return

                # cleared:
                # Eski pending invalid/expired olduğu için
                # normal yeni-entry akışı devam eder.

        decision_signal_context = (
            self._resolve_long_decision_signal_context(
                signal=signal,
                raw_signal=raw_signal,
                symbol=sym_u,
                extra=extra0,
            )
        )

        signal_u = str(
            decision_signal_context["signal_u"]
        )
        side_norm = str(
            decision_signal_context["side_norm"]
        )
        bot_side_mode = str(
            decision_signal_context["bot_side_mode"]
        )

        if not bool(
            decision_signal_context["side_allowed"]
        ):
            return

        open_score_context = (
            self._resolve_long_decision_open_score_context(
                symbol=sym_u,
                side=side_norm,
                extra=extra0,
                probs=probs,
            )
        )

        long_open_context = open_score_context["context"]
        signal_score = float(
            open_score_context["signal_score"]
        )
        open_min_score = float(
            open_score_context["open_min_score"]
        )

        # ---------------------------------------------------------
        # SHADOW-ONLY OKX OI CONTEXT TELEMETRY
        # Fail-open by design: no threshold, veto, pending, or order effect.
        # ---------------------------------------------------------
        try:
            if (
                _read_okx_oi_shadow is not None
                and _emit_okx_oi_entry_shadow is not None
                and self.redis is not None
            ):
                combined_shadow = (
                    _read_market_context_shadow(self.redis, sym_u)
                    if _read_market_context_shadow is not None
                    else {}
                )
                if str(combined_shadow.get("status") or "").upper() in ("OK", "DEGRADED"):
                    oi_shadow = combined_shadow.get("okx_oi") if isinstance(combined_shadow.get("okx_oi"), dict) else {}
                    structure_shadow = combined_shadow.get("binance_structure") if isinstance(combined_shadow.get("binance_structure"), dict) else {}
                    micro_shadow = combined_shadow.get("binance_microstructure") if isinstance(combined_shadow.get("binance_microstructure"), dict) else {}
                else:
                    oi_shadow = _read_okx_oi_shadow(self.redis, sym_u)
                    structure_shadow = (
                        _read_binance_structure_shadow(self.redis, sym_u)
                        if _read_binance_structure_shadow is not None
                        else {}
                    )
                    micro_shadow = {}
                _emit_okx_oi_entry_shadow(
                    self.redis,
                    symbol=sym_u,
                    side=side_norm,
                    signal_score=signal_score,
                    open_min_score=open_min_score,
                    entry_interval=entry_interval,
                    oi_context=oi_shadow,
                    structure_context=structure_shadow,
                    micro_context=micro_shadow,
                    extra=extra0,
                )
        except Exception:
            pass

        sniper_decision = self._evaluate_long_sniper_timing_decision(
            symbol=sym_u,
            side=side_norm,
            entry_interval=entry_interval,
            signal_score=signal_score,
            open_min_score=open_min_score,
            allow_pending=True,
        )
        if sniper_decision is not None:
            sniper_decision = self._dispatch_long_candidate_decision(
                sniper_decision
            )
            sniper_action = str(
                sniper_decision.get("action") or "block"
            ).strip().lower()
            if sniper_action == "pending":
                pending_extra = dict(extra0)
                pending_extra["price"] = price
                pending_extra["entry_interval"] = str(entry_interval or "1m")
                self._store_long_pending_candidate(
                    symbol=sym_u,
                    side=side_norm,
                    decision=sniper_decision,
                    interval=str(entry_interval or "1m"),
                    extra=pending_extra,
                )
                try:
                    if self.logger:
                        self.logger.info(
                            "[EXEC][PENDING-STORE] symbol=%s side=%s reason=%s progress=%s interval=%s",
                            sym_u,
                            side_norm,
                            str(sniper_decision.get("reason") or ""),
                            str(sniper_decision.get("progress") or ""),
                            str(entry_interval or "1m"),
                        )
                except Exception:
                    pass
                return
            return

        self._update_long_decision_snapshot(
            symbol=sym_u,
            interval=interval,
            signal_u=signal_u,
            side=side_norm,
            signal_score=signal_score,
            whale_action=whale_action,
            whale_dir=whale_dir,
            whale_score=whale_score,
            probs=probs,
            extra=extra0,
        )

        if signal_u == "HOLD":
            self._handle_long_hold_signal(
                symbol=sym_u,
                price=price,
                interval=str(interval or ""),
                signal_score=signal_score,
                whale_action=whale_action,
                whale_dir=whale_dir,
                whale_score=whale_score,
                extra=extra0,
            )
            return

        if not self._evaluate_long_candidate_base_precheck(
            symbol=sym_u,
            side=side_norm,
            training_mode=training_mode,
            signal_score=signal_score,
            open_min_score=open_min_score,
        ):
            return

        candidate_decision = self._evaluate_long_candidate_pipeline(
            symbol=sym_u,
            side=side_norm,
            price=price,
            signal_score=signal_score,
            open_min_score=open_min_score,
            extra=extra0,
        )
        candidate_decision = self._dispatch_long_candidate_decision(
            candidate_decision
        )
        candidate_action = str(
            candidate_decision.get("action") or "block"
        ).strip().lower()

        if candidate_action == "pending":
            pending_extra = dict(extra0)
            pending_extra["price"] = price
            pending_extra["entry_interval"] = str(
                entry_interval or "1m"
            )
            self._store_long_pending_candidate(
                symbol=sym_u,
                side=side_norm,
                decision=candidate_decision,
                interval=str(entry_interval or "1m"),
                extra=pending_extra,
            )
            try:
                if self.logger:
                    self.logger.info(
                        "[EXEC][PENDING-STORE] "
                        "symbol=%s side=%s reason=%s "
                        "kind=confirmation interval=%s",
                        sym_u,
                        side_norm,
                        str(candidate_decision.get("reason") or ""),
                        str(entry_interval or "1m"),
                    )
            except Exception:
                pass
            return

        if candidate_action != "open":
            return

        await self._execute_long_validated_candidate(
            symbol=sym_u,
            side=side_norm,
            price=price,
            signal_score=signal_score,
            decision_interval=decision_interval,
            entry_interval=entry_interval,
            exit_interval=exit_interval,
            lifecycle_interval=lifecycle_interval,
            interval=interval,
            extra=extra0,
            signal_label=signal_u,
        )
        return
