"""Proposed shared-runtime identity module, staged only; no I/O, no Redis.

Prospective deployment location:
  orchestration/schemas/identity_provenance.py
Only applies to NEARUSDT 3m LONG1. A candle key is a bar identity, not an
event or execution identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
import re
from typing import Any, Mapping

CANDLE_INTERVAL_MS = 180000
MAX_EVENT_ID_LENGTH = 160
_EVENT_ID_RE = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
_STREAM_ID_RE = re.compile(r"[0-9]{11,16}-[0-9]{1,6}\Z")


@dataclass(frozen=True)
class CandleIdentity:
    model_candle_key: str
    model_open_time_ms: int
    model_close_time_ms: int


def _timestamp_ms(value: Any) -> int:
    """Integer epoch millis; no float coercion of high precision timestamps."""
    if type(value) is bool:
        raise ValueError("bool is not an epoch timestamp")
    if isinstance(value, Integral):
        v = int(value)
    elif isinstance(value, str) and re.fullmatch(r"[0-9]{13}", value):
        v = int(value)
    else:
        raise ValueError("epoch timestamp must be integer milliseconds")
    if v <= 0:
        raise ValueError("invalid epoch timestamp")
    return v


def validate_candle_identity(
    *, symbol: str, interval: str, open_time_ms: Any,
    close_time_ms: Any, observed_at_ms: Any,
) -> CandleIdentity:
    """Validate actual Binance 3m candle, closed at observation instant."""
    if str(symbol).strip().upper() != "NEARUSDT" or interval != "3m":
        raise ValueError("outside LONG1 3m identity scope")
    op = _timestamp_ms(open_time_ms)
    cl = _timestamp_ms(close_time_ms)
    now = _timestamp_ms(observed_at_ms)
    if op % CANDLE_INTERVAL_MS or cl != op + CANDLE_INTERVAL_MS - 1:
        raise ValueError("invalid 3m UTC candle boundary")
    if cl >= now:
        raise ValueError("candle is not closed")
    return CandleIdentity(
        model_candle_key=f"NEARUSDT:3m:{op}:{cl}",
        model_open_time_ms=op,
        model_close_time_ms=cl,
    )


def identity_from_closed_frame(
    frame: Any, *, symbol: str, interval: str, observed_at_ms: Any,
) -> CandleIdentity:
    if frame is None or len(frame) == 0:
        raise ValueError("missing source model frame")
    if "open_time" not in frame.columns or "close_time" not in frame.columns:
        raise ValueError("source timestamp columns missing")
    # Critical: never use mixed-numeric frame.iloc[-1] (float64 promotion).
    return validate_candle_identity(
        symbol=symbol, interval=interval,
        open_time_ms=frame["open_time"].iloc[-1],
        close_time_ms=frame["close_time"].iloc[-1],
        observed_at_ms=observed_at_ms,
    )


def verified_source_lineage(
    event: Mapping[str, Any], *, symbol: str, side: str,
    interval: str, observed_at_ms: Any,
) -> dict[str, Any] | None:
    """Only explicit event_id + Redis source ID are authoritative ancestry."""
    if not isinstance(event, Mapping):
        return None
    if (str(symbol).upper(), str(side).lower(), str(interval)) != (
        "NEARUSDT", "long", "3m"
    ):
        return None
    event_id = event.get("event_id")
    stream_id = event.get("_source_stream_id")
    if not isinstance(event_id, str) or not _EVENT_ID_RE.fullmatch(event_id):
        return None
    if not isinstance(stream_id, str) or not _STREAM_ID_RE.fullmatch(stream_id):
        return None
    lineage: dict[str, Any] = {
        "lineage_state": "EXACT_SIGNAL_EVENT_ID_AND_STREAM_ID",
        "source_signal_event_id": event_id,
        "source_signal_stream_id": stream_id,
    }
    key = event.get("model_candle_key")
    if isinstance(key, str) and len(key) <= 120:
        try:
            verified = validate_candle_identity(
                symbol=symbol, interval=interval,
                open_time_ms=event.get("model_open_time_ms"),
                close_time_ms=event.get("model_close_time_ms"),
                observed_at_ms=observed_at_ms,
            )
        except (ValueError, TypeError):
            pass
        else:
            if verified.model_candle_key == key:
                lineage["model_candle_key"] = key
                lineage["model_open_time_ms"] = verified.model_open_time_ms
                lineage["model_close_time_ms"] = verified.model_close_time_ms
    # No model_close_id copied from a wall-clock bucket or legacy field.
    return lineage
