"""LONG1 native-stop attach failure isolation. No exchange writes at import."""
from __future__ import annotations
from pathlib import Path
import os
from core.binance_futures_v3 import position_risk

KEY = "risk:long1:native_stop_failure_latch"
SYMBOL = "NEARUSDT"
DISK_LATCH = Path(__file__).resolve().parents[1] / "state" / "long1_native_stop_failure.latch"

def entry_allowed(redis_client, *, dry_run=False, native_enabled=True, local_latched=False):
    if dry_run:
        return True
    if not native_enabled or local_latched or redis_client is None:
        return False
    try:
        if DISK_LATCH.exists():
            return False
        if not DISK_LATCH.parent.is_dir():
            return False
        value = redis_client.get(KEY)
        if isinstance(value, bytes):
            value = value.decode(errors="replace")
        return str(value or "").lower() not in ("1", "true", "yes")
    except Exception:
        return False

def long_qty():
    """Read authoritative hedge LONG; a read failure is never treated as flat."""
    rows = position_risk(SYMBOL)
    if not isinstance(rows, list):
        raise RuntimeError("position_risk_bad_response")
    relevant = [
        x for x in rows if isinstance(x, dict)
        and x.get("symbol") == SYMBOL
        and x.get("positionSide") == "LONG"
    ]
    if len(relevant) > 1:
        raise RuntimeError("ambiguous_long_position")
    return max(0.0, float(relevant[0].get("positionAmt") or 0)) if relevant else 0.0

def latch(executor):
    executor._long1_native_stop_latched = True
    DISK_LATCH.parent.mkdir(parents=True, exist_ok=True)
    temp = DISK_LATCH.with_suffix(".tmp")
    with temp.open("w") as f:
        f.write("NATIVE_STOP_FAILURE_MANUAL_REVIEW_REQUIRED\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, DISK_LATCH)
    dirfd = os.open(str(DISK_LATCH.parent), os.O_RDONLY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)
    if executor.redis is None:
        raise RuntimeError("redis_unavailable_disk_latch_set")
    executor.redis.set(KEY, "1")

def emergency(executor, *, price, interval):
    """One close request only, independent post-check. Never infer success from ACK."""
    try:
        latch(executor)
    except Exception as exc:
        if executor.logger:
            executor.logger.critical("[LONG1][STOP-FAIL][LATCH-ERROR] %s", str(exc)[:180])
    try:
        before = long_qty()
    except Exception as exc:
        return {"state": "POSITION_UNKNOWN", "error": type(exc).__name__}
    if before == 0:
        return {"state": "ALREADY_FLAT"}
    try:
        result = executor.close_position(
            SYMBOL, price=float(price or 0.0),
            reason="native_stop_attach_failed", interval=str(interval or "1m")
        )
    except Exception as exc:
        result = {"state": "CLOSE_ERROR", "error": type(exc).__name__}
    try:
        after = long_qty()
    except Exception as exc:
        return {"state": "CLOSE_UNVERIFIED", "error": type(exc).__name__}
    return {
        "state": "FLAT_CONFIRMED" if after == 0 else "STILL_OPEN",
        "remaining_qty": after, "close_result_type": type(result).__name__,
    }
