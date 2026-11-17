"""Research-only immutable model candle provenance. No orders, no Redis writes."""
from __future__ import annotations
from dataclasses import dataclass
from numbers import Integral
import re

_INTERVAL_MS = {"1m":60000, "3m":180000, "5m":300000, "15m":900000, "1h":3600000}

@dataclass(frozen=True)
class CandleIdentity:
    model_candle_key: str
    model_open_time_ms: int
    model_close_time_ms: int
    model_interval: str
    model_symbol: str

def _ms(value):
    if isinstance(value, bool):
        raise ValueError("boolean timestamp")
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"[0-9]{13}", value):
        return int(value)
    raise ValueError("timestamp must be integer milliseconds")

def from_closed_candle(*, symbol, interval, open_time_ms, close_time_ms, observed_at_ms):
    """Binance interval-anchored UTC kline close convention: next_open-1ms."""
    sym = str(symbol).upper().strip()
    if sym != "NEARUSDT":
        raise ValueError("not LONG1 NEARUSDT")
    if interval not in _INTERVAL_MS:
        raise ValueError("unsupported fixed interval")
    op = _ms(open_time_ms)
    cl = _ms(close_time_ms)
    now = _ms(observed_at_ms)
    duration = _INTERVAL_MS[interval]
    if op <= 0 or op % duration != 0:
        raise ValueError("invalid candle open alignment")
    if cl != op + duration - 1:
        raise ValueError("close time inconsistent with interval")
    if cl >= now:
        raise ValueError("candle not yet closed")
    # This is candle identity, not attempt identity. Multiple predictions of
    # same candle have the same key and separate SignalEvent event_id.
    return CandleIdentity(
        model_candle_key=f"{sym}:{interval}:{op}:{cl}",
        model_open_time_ms=op,
        model_close_time_ms=cl,
        model_interval=interval,
        model_symbol=sym,
    )

def from_closed_frame(frame, *, symbol, interval, observed_at_ms):
    if frame is None or len(frame) == 0:
        raise ValueError("missing model frame")
    if "open_time" not in frame.columns or "close_time" not in frame.columns:
        raise ValueError("missing source candle columns")
    # Select individual columns rather than frame.iloc[-1]: pandas can
    # promote an entire mixed numeric row to float64, losing the integer
    # timestamp type even while both source columns remain int64.
    return from_closed_candle(
        symbol=symbol, interval=interval,
        open_time_ms=frame["open_time"].iloc[-1],
        close_time_ms=frame["close_time"].iloc[-1],
        observed_at_ms=observed_at_ms,
    )
