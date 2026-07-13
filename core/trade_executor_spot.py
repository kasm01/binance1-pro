from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _env_float(k: str, d: float) -> float:
    try:
        return float(os.getenv(k, str(d)) or d)
    except Exception:
        return float(d)


def _env_int(k: str, d: int) -> int:
    try:
        return int(float(os.getenv(k, str(d)) or d))
    except Exception:
        return int(d)


def _env_bool(k: str, d: str = "0") -> bool:
    return str(os.getenv(k, d) or d).strip().lower() in ("1", "true", "yes", "on")


class SpotTradeExecutor:
    """
    Sade spot executor:
    Alım:
      - long/BUY
      - score >= SPOT_MIN_SCORE
      - 3m + 5m trend yukarı
      - whale/EMA sadece log
      - günlük max SPOT_DAILY_MAX_TRADES_PER_SYMBOL

    Satış:
      - %3 TP'de trailing aktif
      - %2 trailing geri çekilirse SELL
      - stop yok
    """

    def __init__(
        self,
        client: Any,
        redis_client: Any = None,
        risk_manager: Any = None,
        position_manager: Any = None,
        logger: Any = None,
        dry_run: bool = True,
        base_order_notional: float = 25.0,
        max_position_notional: float = 30.0,
        max_leverage: int = 1,
        sl_pct: float = 0.0,
        tp_pct: float = 0.03,
        trailing_pct: float = 0.02,
        use_atr_sltp: bool = False,
        atr_sl_mult: float = 0.0,
        atr_tp_mult: float = 0.0,
        whale_risk_boost: float = 1.0,
        tg_bot: Any = None,
        price_cache: Any = None,
        **kwargs: Any,
    ) -> None:
        self.client = client
        self.redis = redis_client
        self.redis_client = redis_client
        self.risk_manager = risk_manager
        self.position_manager = position_manager
        self.logger = logger
        self.dry_run = bool(dry_run)
        self.armed = _env_bool("ARMED", "0")
        self.live_trading_enabled = _env_bool("LIVE_TRADING_ENABLED", "0")
        self.live_kill_switch = _env_bool("LIVE_KILL_SWITCH", "0")

        self.base_order_notional = float(_env_float("SPOT_ORDER_USDT", base_order_notional))
        self.max_position_notional = float(max_position_notional or self.base_order_notional)
        self.tg_bot = tg_bot
        self.price_cache = price_cache

        self.min_score = _env_float("SPOT_MIN_SCORE", 0.55)
        self.tp_pct = _env_float("SPOT_TP_PCT", 0.03)
        self.trailing_pct = _env_float("SPOT_TRAILING_PCT", 0.02)
        self.daily_max = _env_int("SPOT_DAILY_MAX_TRADES_PER_SYMBOL", 5)
        self.max_open_positions = _env_int("MAX_OPEN_POSITIONS", 3)
        self.position_lifecycle_interval_sec = _env_int("POSITION_LIFECYCLE_INTERVAL_SEC", 2)
        self.position_sync_interval_sec = _env_int("POSITION_SYNC_INTERVAL_SEC", 20)
        self.redis_key_prefix = os.getenv("REDIS_KEY_PREFIX", "bot:spot_positions").rstrip(":")

    def _log(self, level: str, msg: str, *args: Any) -> None:
        try:
            lg = self.logger
            if lg is not None:
                getattr(lg, level)(msg, *args)
        except Exception:
            pass

    def _pos_key(self, symbol: str) -> str:
        return f"{self.redis_key_prefix}:{str(symbol).upper()}"

    def _spot_base_asset(self, symbol: str) -> str:
        sym = str(symbol or "").upper().strip()
        quote = str(os.getenv("SPOT_QUOTE_ASSET", "USDT") or "USDT").upper().strip()

        if quote and sym.endswith(quote):
            return sym[:-len(quote)]

        return sym

    def _spot_free_balance(self, asset: str) -> float:
        try:
            fn = getattr(self.client, "get_asset_balance", None)
            if not callable(fn):
                return 0.0

            row = fn(asset=str(asset).upper())
            if not isinstance(row, dict):
                return 0.0

            return float(row.get("free") or 0.0)
        except Exception as e:
            self._log(
                "warning",
                "[EXEC][SPOT][BALANCE] read failed | asset=%s err=%s",
                asset,
                str(e)[:300],
            )
            return 0.0

    def _spot_market_step_size(self, symbol: str) -> float:
        try:
            fn = getattr(self.client, "get_symbol_info", None)
            if not callable(fn):
                return 0.0

            info = fn(str(symbol).upper())
            if not isinstance(info, dict):
                return 0.0

            filters = info.get("filters") or []

            # MARKET emri için önce MARKET_LOT_SIZE.
            # stepSize=0 ise LOT_SIZE fallback.
            lot_step = 0.0

            for row in filters:
                if not isinstance(row, dict):
                    continue

                filter_type = str(row.get("filterType") or "").upper()

                if filter_type == "MARKET_LOT_SIZE":
                    step = float(row.get("stepSize") or 0.0)
                    if step > 0:
                        return step

                if filter_type == "LOT_SIZE":
                    lot_step = float(row.get("stepSize") or 0.0)

            return lot_step
        except Exception as e:
            self._log(
                "warning",
                "[EXEC][SPOT][FILTER] step read failed | symbol=%s err=%s",
                symbol,
                str(e)[:300],
            )
            return 0.0

    @staticmethod
    def _floor_qty_to_step(qty: float, step: float) -> float:
        from decimal import Decimal, ROUND_DOWN

        try:
            q = Decimal(str(qty))
            st = Decimal(str(step))

            if q <= 0:
                return 0.0

            if st <= 0:
                return float(q)

            units = (q / st).to_integral_value(rounding=ROUND_DOWN)
            return float(units * st)
        except Exception:
            return 0.0

    def _daily_key(self, symbol: str) -> str:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"bot:spot_daily_trades:{day}:{str(symbol).upper()}"

    def _get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        sym = str(symbol).upper()
        try:
            if self.position_manager is not None and hasattr(self.position_manager, "get_position"):
                pos = self.position_manager.get_position(sym)
                if isinstance(pos, dict):
                    return pos
        except Exception:
            pass

        try:
            if self.redis is not None:
                raw = self.redis.get(self._pos_key(sym))
                if raw:
                    return json.loads(raw)
        except Exception:
            pass

        return None

    def _set_position(self, symbol: str, pos: Dict[str, Any]) -> None:
        sym = str(symbol).upper()
        try:
            if self.position_manager is not None and hasattr(self.position_manager, "set_position"):
                self.position_manager.set_position(sym, pos)
                return
        except Exception:
            pass

        try:
            if self.redis is not None:
                self.redis.set(self._pos_key(sym), json.dumps(pos, ensure_ascii=False, default=str))
        except Exception:
            pass

    def _del_position(self, symbol: str) -> None:
        sym = str(symbol).upper()
        try:
            if self.position_manager is not None and hasattr(self.position_manager, "clear_position"):
                self.position_manager.clear_position(sym)
        except Exception:
            pass
        try:
            if self.redis is not None:
                self.redis.delete(self._pos_key(sym))
        except Exception:
            pass

    def _all_positions(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}

        # Spot için Redis prefix'i içinde ":" olduğu için PositionManager.list_symbols()
        # sembolü yanlış parse edebilir. Bu yüzden direkt bot:spot_positions:* okuyoruz.
        try:
            if self.redis is not None:
                pattern = f"{self.redis_key_prefix}:*"
                keys = self.redis.keys(pattern) or []
                prefix = f"{self.redis_key_prefix}:"

                for k in keys:
                    try:
                        key_s = k.decode("utf-8", errors="ignore") if isinstance(k, (bytes, bytearray)) else str(k)
                        sym = key_s[len(prefix):].upper().strip() if key_s.startswith(prefix) else key_s.split(":")[-1].upper().strip()
                        raw = self.redis.get(key_s)
                        if raw:
                            obj = json.loads(raw)
                            if isinstance(obj, dict):
                                obj["symbol"] = str(obj.get("symbol") or sym).upper()
                                out[sym] = obj
                    except Exception:
                        pass

                return out
        except Exception:
            pass

        try:
            if self.position_manager is not None and hasattr(self.position_manager, "list_symbols"):
                for sym in self.position_manager.list_symbols() or []:
                    pos = self._get_position(sym)
                    if isinstance(pos, dict):
                        out[str(pos.get("symbol") or sym).upper()] = pos
        except Exception:
            pass

        return out

    def _price(self, symbol: str) -> Optional[float]:
        sym = str(symbol).upper()

        try:
            pc = self.price_cache
            if pc is not None and hasattr(pc, "get"):
                v = pc.get(sym)
                if isinstance(v, (int, float)) and float(v) > 0:
                    return float(v)
        except Exception:
            pass

        try:
            fn = getattr(self.client, "get_symbol_ticker", None)
            if callable(fn):
                r = fn(symbol=sym)
                px = float(r.get("price") or 0)
                if px > 0:
                    return px
        except Exception:
            return None

        return None

    def _klines(self, symbol: str, interval: str, limit: int = 80):
        fn = getattr(self.client, "get_klines", None)
        if not callable(fn):
            return []
        return fn(symbol=str(symbol).upper(), interval=interval, limit=limit)

    def _trend_up(self, symbol: str, interval: str) -> bool:
        try:
            rows = self._klines(symbol, interval, 80)
            closes = [float(r[4]) for r in rows if r and len(r) > 4]
            if len(closes) < 30:
                return False
            ema7 = self._ema(closes, 7)
            ema25 = self._ema(closes, 25)
            ema99 = self._ema(closes, 50)
            last = closes[-1]
            ok = last > ema25 and ema7 > ema25 and ema25 >= ema99 * 0.998
            self._log("info", "[SPOT][TREND] symbol=%s interval=%s ok=%s price=%.8f ema7=%.8f ema25=%.8f ema99=%.8f",
                      symbol, interval, ok, last, ema7, ema25, ema99)
            return bool(ok)
        except Exception as e:
            self._log("warning", "[SPOT][TREND][WARN] symbol=%s interval=%s err=%s", symbol, interval, str(e)[:160])
            return False

    @staticmethod
    def _ema(vals, n: int) -> float:
        alpha = 2.0 / (n + 1.0)
        e = float(vals[0])
        for v in vals[1:]:
            e = alpha * float(v) + (1 - alpha) * e
        return float(e)

    def _daily_limit_ok(self, symbol: str) -> bool:
        try:
            if self.redis is None:
                return True
            k = self._daily_key(symbol)
            n = int(self.redis.get(k) or 0)
            return n < int(self.daily_max)
        except Exception:
            return True

    def _daily_inc(self, symbol: str) -> None:
        try:
            if self.redis is None:
                return
            k = self._daily_key(symbol)
            v = self.redis.incr(k)
            if int(v) == 1:
                self.redis.expire(k, 36 * 3600)
        except Exception:
            pass

    def _score_from(self, side: str, extra: Dict[str, Any], probs: Any = None) -> float:
        vals = [
            extra.get("signal_score"),
            extra.get("long_score") if side == "long" else None,
            extra.get("p_buy_ema"),
            extra.get("p_buy_raw"),
        ]
        if isinstance(probs, dict):
            vals += [probs.get("p_used"), probs.get("p_single")]
        for v in vals:
            try:
                if v is not None:
                    return float(v)
            except Exception:
                pass
        return 0.0

    async def execute_decision(self, symbol: str, signal: str, price: Any = None, interval: str = "3m", size: Any = None, extra: Any = None, probs: Any = None, **kwargs: Any):
        extra0 = extra if isinstance(extra, dict) else {}
        sig = str(signal or "").strip().lower()
        side = "long" if sig in ("buy", "long") else "hold"

        if side != "long":
            return {"ok": False, "reason": "not_long"}

        sym = str(symbol).upper()
        score = self._score_from(side, extra0, probs)

        self._log("info", "[SPOT][DECISION] symbol=%s side=%s score=%.4f min=%.4f whale_dir=%s whale_score=%s",
                  sym, side, score, self.min_score, extra0.get("whale_dir"), extra0.get("whale_score"))

        if score < self.min_score:
            self._log("info", "[SPOT][OPEN-BLOCK] low_score | symbol=%s score=%.4f min=%.4f", sym, score, self.min_score)
            return {"ok": False, "reason": "low_score"}

        if self._get_position(sym):
            self._log("info", "[SPOT][OPEN-BLOCK] already_open | symbol=%s", sym)
            return {"ok": False, "reason": "already_open"}

        open_positions = self._all_positions()
        open_count = len(open_positions)

        if open_count >= int(self.max_open_positions):
            self._log(
                "info",
                "[SPOT][OPEN-BLOCK] max_open_positions | symbol=%s open_count=%s limit=%s symbols=%s",
                sym,
                open_count,
                self.max_open_positions,
                list(open_positions.keys()),
            )
            return {"ok": False, "reason": "max_open_positions"}

        if not self._daily_limit_ok(sym):
            self._log("info", "[SPOT][OPEN-BLOCK] daily_limit | symbol=%s limit=%s", sym, self.daily_max)
            return {"ok": False, "reason": "daily_limit"}

        # Trend sadece bilgi/log amaçlıdır; spotta alımı veto etmez.
        trend_3m = self._trend_up(sym, "3m")
        trend_5m = self._trend_up(sym, "5m")

        self._log(
            "info",
            "[SPOT][TREND-SUMMARY] symbol=%s trend_3m=%s trend_5m=%s veto=0",
            sym,
            trend_3m,
            trend_5m,
        )

        return await self.open_position_from_signal(symbol=sym, side="long", price=price, interval=interval, score=score, extra=extra0)

    async def open_position_from_signal(self, symbol: str, side: str = "long", price: Any = None, interval: str = "3m", score: float = 0.0, extra: Any = None, **kwargs: Any):
        sym = str(symbol).upper()
        px = float(price or 0) if price else 0.0
        if px <= 0:
            px0 = self._price(sym)
            if not px0:
                return {"ok": False, "reason": "no_price"}
            px = float(px0)

        notional = min(float(self.base_order_notional), float(self.max_position_notional))
        qty = notional / px

        if self.dry_run:
            resp = {"dry_run": True, "symbol": sym, "side": "BUY", "qty": qty, "notional": notional}
        else:
            if (
                not self.armed
                or not self.live_trading_enabled
                or self.live_kill_switch
            ):
                self._log(
                    "warning",
                    "[EXEC][SPOT][LIVE-BLOCK] BUY blocked | symbol=%s armed=%s live_enabled=%s kill_switch=%s",
                    sym,
                    self.armed,
                    self.live_trading_enabled,
                    self.live_kill_switch,
                )
                return {"ok": False, "reason": "live_safety_block"}

            fn = getattr(self.client, "create_order", None)
            if not callable(fn):
                return {"ok": False, "reason": "create_order_missing"}
            resp = fn(
                symbol=sym,
                side="BUY",
                type="MARKET",
                quoteOrderQty=round(notional, 2),
                newOrderRespType="FULL",
            )

            # Gerçek Binance fill miktarı ve ortalama alış fiyatı.
            try:
                buy_status = str(resp.get("status") or "").upper().strip()
                executed_qty = float(resp.get("executedQty") or 0.0)
            except Exception:
                buy_status = ""
                executed_qty = 0.0

            try:
                cumulative_quote = float(
                    resp.get("cummulativeQuoteQty")
                    or resp.get("cumulativeQuoteQty")
                    or 0.0
                )
            except Exception:
                cumulative_quote = 0.0

            if buy_status != "FILLED" or executed_qty <= 0:
                self._log(
                    "error",
                    "[EXEC][SPOT][ORDER] BUY not fully filled | symbol=%s status=%s executed_qty=%.10f resp=%s",
                    sym,
                    buy_status,
                    executed_qty,
                    str(resp)[:1200],
                )
                return {
                    "ok": False,
                    "reason": "buy_not_fully_filled",
                    "status": buy_status,
                    "executed_qty": executed_qty,
                    "resp": resp,
                }

            # BUY komisyonu base asset'ten kesildiyse net alınan qty'yi hesapla.
            base_asset = self._spot_base_asset(sym)
            base_commission = 0.0

            try:
                fills = resp.get("fills") or []

                for fill in fills:
                    if not isinstance(fill, dict):
                        continue

                    commission_asset = str(
                        fill.get("commissionAsset") or ""
                    ).upper().strip()

                    if commission_asset == base_asset:
                        base_commission += float(
                            fill.get("commission") or 0.0
                        )
            except Exception:
                base_commission = 0.0

            qty = max(
                0.0,
                float(executed_qty) - float(base_commission),
            )

            if qty <= 0:
                self._log(
                    "error",
                    "[EXEC][SPOT][ORDER] BUY net qty invalid | symbol=%s executed_qty=%.10f base_commission=%.10f",
                    sym,
                    executed_qty,
                    base_commission,
                )
                return {
                    "ok": False,
                    "reason": "buy_net_qty_invalid",
                    "executed_qty": executed_qty,
                    "base_commission": base_commission,
                    "resp": resp,
                }

            self._log(
                "info",
                "[EXEC][SPOT][BUY-QTY] symbol=%s executed_qty=%.10f base_commission=%.10f net_qty=%.10f",
                sym,
                executed_qty,
                base_commission,
                qty,
            )

            if cumulative_quote > 0 and executed_qty > 0:
                px = float(cumulative_quote / executed_qty)

        pos = {
            "symbol": sym,
            "side": "long",
            "qty": float(qty),
            "entry_price": float(px),
            "notional": float(notional),
            "interval": str(interval or "3m"),
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "score": float(score),
            "best_price": float(px),
            "trailing_armed": False,
            "trail_stop_price": 0.0,
            "meta": {"extra": extra if isinstance(extra, dict) else {}, "order_resp": resp},
        }
        self._set_position(sym, pos)
        self._daily_inc(sym)

        self._log("info", "[EXEC][SPOT][ORDER] BUY OK | dry_run=%s symbol=%s qty=%.10f notional=%.2f price=%.8f score=%.4f",
                  self.dry_run, sym, qty, notional, px, score)
        return {"ok": True, "symbol": sym, "qty": qty, "price": px, "dry_run": self.dry_run}

    async def close_position(self, symbol: str, reason: str = "tp_trailing", price: Any = None, **kwargs: Any):
        sym = str(symbol).upper()
        pos = self._get_position(sym)
        if not isinstance(pos, dict):
            return {"ok": False, "reason": "no_position"}

        qty = float(pos.get("qty") or 0)
        sell_qty = float(qty)

        px = float(price or 0) if price else 0.0
        if px <= 0:
            px0 = self._price(sym)
            if not px0:
                return {"ok": False, "reason": "no_price"}
            px = float(px0)

        if self.dry_run:
            resp = {"dry_run": True, "symbol": sym, "side": "SELL", "qty": sell_qty}
        else:
            asset = self._spot_base_asset(sym)
            free_qty = self._spot_free_balance(asset)

            if free_qty <= 0:
                self._log(
                    "error",
                    "[EXEC][SPOT][CLOSE] no free balance | symbol=%s asset=%s pos_qty=%.10f free_qty=%.10f",
                    sym,
                    asset,
                    qty,
                    free_qty,
                )
                return {"ok": False, "reason": "no_free_balance"}

            sell_qty = min(float(qty), float(free_qty))

            step_size = self._spot_market_step_size(sym)
            sell_qty = self._floor_qty_to_step(sell_qty, step_size)

            if sell_qty <= 0:
                self._log(
                    "error",
                    "[EXEC][SPOT][CLOSE] sell qty invalid | symbol=%s pos_qty=%.10f free_qty=%.10f step=%.12f sell_qty=%.10f",
                    sym,
                    qty,
                    free_qty,
                    step_size,
                    sell_qty,
                )
                return {"ok": False, "reason": "sell_qty_invalid"}

            self._log(
                "info",
                "[EXEC][SPOT][CLOSE-QTY] symbol=%s asset=%s pos_qty=%.10f free_qty=%.10f step=%.12f sell_qty=%.10f",
                sym,
                asset,
                qty,
                free_qty,
                step_size,
                sell_qty,
            )

            fn = getattr(self.client, "create_order", None)
            if not callable(fn):
                return {"ok": False, "reason": "create_order_missing"}

            resp = fn(
                symbol=sym,
                side="SELL",
                type="MARKET",
                quantity=sell_qty,
                newOrderRespType="FULL",
            )

            try:
                sell_status = str(resp.get("status") or "").upper().strip()
                executed_sell_qty = float(resp.get("executedQty") or 0.0)
            except Exception:
                sell_status = ""
                executed_sell_qty = 0.0

            if sell_status != "FILLED" or executed_sell_qty <= 0:
                self._log(
                    "error",
                    "[EXEC][SPOT][CLOSE] SELL not fully filled | symbol=%s status=%s requested_qty=%.10f executed_qty=%.10f resp=%s",
                    sym,
                    sell_status,
                    sell_qty,
                    executed_sell_qty,
                    str(resp)[:1200],
                )
                return {
                    "ok": False,
                    "reason": "sell_not_fully_filled",
                    "status": sell_status,
                    "executed_qty": executed_sell_qty,
                    "resp": resp,
                }

            sell_qty = float(executed_sell_qty)

        self._del_position(sym)

        self._log(
            "info",
            "[EXEC][SPOT][CLOSE] SELL OK | dry_run=%s symbol=%s qty=%.10f price=%.8f reason=%s",
            self.dry_run,
            sym,
            sell_qty,
            px,
            reason,
        )
        return {
            "ok": True,
            "symbol": sym,
            "qty": sell_qty,
            "price": px,
            "reason": reason,
            "resp": resp,
        }

    def sync_positions_with_exchange(self):
        self._log("info", "[EXEC][SPOT][SYNC] skipped futures position sync")
        return {"spot_mode": True, "exchange_open": 0, "local_open": len(self._all_positions())}

    async def _position_sync_loop(self):
        while True:
            try:
                self.sync_positions_with_exchange()
            except Exception:
                pass
            await asyncio.sleep(max(5, int(self.position_sync_interval_sec)))

    async def _position_lifecycle_loop(self):
        while True:
            try:
                await self._position_lifecycle_once()
            except Exception as e:
                self._log("warning", "[SPOT][LIFECYCLE][WARN] err=%s", str(e)[:200])
            await asyncio.sleep(max(1, int(self.position_lifecycle_interval_sec)))

    async def _position_lifecycle_once(self):
        positions = self._all_positions()
        self._log("info", "[EXEC][SPOT][LIFECYCLE] tick | positions=%s symbols=%s", len(positions), list(positions.keys()))

        for sym, pos in positions.items():
            px = self._price(sym)
            if not px:
                continue

            entry = float(pos.get("entry_price") or 0)
            if entry <= 0:
                continue

            pnl = (float(px) - entry) / entry
            best = max(float(pos.get("best_price") or entry), float(px))
            pos["best_price"] = best

            armed = bool(pos.get("trailing_armed") or False)
            if not armed and pnl >= self.tp_pct:
                armed = True
                pos["trailing_armed"] = True

            trail_stop = float(pos.get("trail_stop_price") or 0.0)
            if armed:
                new_stop = best * (1.0 - self.trailing_pct)
                trail_stop = max(trail_stop, new_stop)
                pos["trail_stop_price"] = trail_stop

            self._set_position(sym, pos)

            self._log("info", "[EXEC][SPOT][LIFECYCLE] symbol=%s pnl=%.4f tp=%.4f trailing=%s best=%.8f trail_stop=%.8f price=%.8f entry=%.8f",
                      sym, pnl, self.tp_pct, armed, best, trail_stop, px, entry)

            if armed and trail_stop > 0 and float(px) <= trail_stop:
                await self.close_position(sym, reason="spot_tp_trailing", price=px)
