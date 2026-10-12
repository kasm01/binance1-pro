#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.redis_config import RedisConfig

OKX_OI_URL = "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history"
DEFAULT_SYMBOLS = "NEARUSDT"
DEFAULT_PERIOD = "4H"
DEFAULT_POLL_SEC = 60.0
DEFAULT_TTL_SEC = 300


def _symbols(raw: str) -> List[str]:
    out: List[str] = []
    for x in (raw or "").split(","):
        s = x.strip().upper().replace("-", "")
        if not s:
            continue
        if not s.endswith("USDT"):
            raise ValueError(f"Only USDT symbols are supported in shadow collector: {s}")
        if s not in out:
            out.append(s)
    return out


def _inst_id(symbol: str) -> str:
    base = symbol[:-4]
    return f"{base}-USDT-SWAP"


def _to_float(x: Any) -> float | None:
    try:
        return float(x)
    except Exception:
        return None


def fetch_oi(session: requests.Session, symbol: str, period: str, timeout: float) -> Dict[str, Any]:
    t0 = time.perf_counter()
    resp = session.get(
        OKX_OI_URL,
        params={"instId": _inst_id(symbol), "period": period, "limit": "3"},
        timeout=timeout,
    )
    latency_ms = (time.perf_counter() - t0) * 1000.0
    resp.raise_for_status()
    body = resp.json()
    if str(body.get("code")) != "0":
        raise RuntimeError(f"OKX code={body.get('code')} msg={str(body.get('msg') or '')[:160]}")
    data = body.get("data") or []
    if len(data) < 2:
        raise RuntimeError(f"OKX OI history returned too few rows: {len(data)}")

    rows = sorted(data, key=lambda r: int(r[0]))
    prev, cur = rows[-2], rows[-1]
    prev_contracts = _to_float(prev[1])
    cur_contracts = _to_float(cur[1])
    prev_usd = _to_float(prev[3]) if len(prev) > 3 else None
    cur_usd = _to_float(cur[3]) if len(cur) > 3 else None
    if prev_contracts in (None, 0.0) or cur_contracts is None:
        raise RuntimeError("OKX OI contracts missing/zero")

    ret = cur_contracts / prev_contracts - 1.0
    now_ms = int(time.time() * 1000)
    source_ts_ms = int(cur[0])
    return {
        "schema_version": 1,
        "shadow_only": True,
        "source": "okx_public",
        "symbol": symbol,
        "inst_id": _inst_id(symbol),
        "period": period,
        "observed_at_ms": now_ms,
        "source_ts_ms": source_ts_ms,
        "source_age_sec": max(0.0, (now_ms - source_ts_ms) / 1000.0),
        "oi_contracts": cur_contracts,
        "oi_usd": cur_usd,
        "prev_oi_contracts": prev_contracts,
        "prev_oi_usd": prev_usd,
        "oi_ret_period": ret,
        "oi_direction": "UP" if ret > 0 else ("DOWN" if ret < 0 else "FLAT"),
        "latency_ms": round(latency_ms, 2),
        "status": "OK",
    }


def store_snapshot(redis_client: Any, payload: Dict[str, Any], ttl_sec: int) -> str:
    symbol = str(payload["symbol"])
    key = f"shadow:market_context:okx_oi:{symbol}"
    redis_client.setex(key, ttl_sec, json.dumps(payload, separators=(",", ":"), sort_keys=True))

    # Low-cost shadow history: at most one telemetry sample per 5-minute bucket.
    # Snapshot itself still refreshes every poll; this stream is only for later validation.
    source_ts = str(payload["source_ts_ms"])
    sample_bucket = str(int(payload["observed_at_ms"]) // 300000)
    marker = f"shadow:market_context:okx_oi:last_sample_bucket:{symbol}"
    old = redis_client.get(marker)
    if old != sample_bucket:
        redis_client.xadd(
            "shadow:telemetry:okx_oi",
            {
                "symbol": symbol,
                "period": str(payload["period"]),
                "source_ts_ms": source_ts,
                "observed_at_ms": str(payload["observed_at_ms"]),
                "oi_contracts": str(payload["oi_contracts"]),
                "oi_usd": "" if payload.get("oi_usd") is None else str(payload["oi_usd"]),
                "oi_ret_period": str(payload["oi_ret_period"]),
                "oi_direction": str(payload["oi_direction"]),
            },
            maxlen=30000,
            approximate=True,
        )
        redis_client.set(marker, sample_bucket)
    return key


def run_once(redis_client: Any, session: requests.Session, symbols: Iterable[str], period: str, ttl_sec: int, timeout: float) -> int:
    failures = 0
    for symbol in symbols:
        try:
            payload = fetch_oi(session, symbol, period, timeout)
            key = store_snapshot(redis_client, payload, ttl_sec)
            print(
                f"OK symbol={symbol} key={key} dir={payload['oi_direction']} "
                f"ret={payload['oi_ret_period']:.6f} source_age_s={payload['source_age_sec']:.1f} "
                f"latency_ms={payload['latency_ms']:.2f}"
            )
        except Exception as exc:
            failures += 1
            print(f"ERROR symbol={symbol} type={type(exc).__name__} msg={str(exc)[:180]}", file=sys.stderr)
    return failures


def main() -> int:
    p = argparse.ArgumentParser(description="Shadow-only OKX OI context collector. Never places orders.")
    p.add_argument("--once", action="store_true", help="Fetch/store one snapshot and exit")
    p.add_argument("--symbols", default=os.getenv("OKX_OI_SHADOW_SYMBOLS", DEFAULT_SYMBOLS))
    p.add_argument("--period", default=os.getenv("OKX_OI_SHADOW_PERIOD", DEFAULT_PERIOD))
    p.add_argument("--poll-sec", type=float, default=float(os.getenv("OKX_OI_SHADOW_POLL_SEC", DEFAULT_POLL_SEC)))
    p.add_argument("--ttl-sec", type=int, default=int(os.getenv("OKX_OI_SHADOW_TTL_SEC", DEFAULT_TTL_SEC)))
    p.add_argument("--timeout", type=float, default=float(os.getenv("OKX_OI_SHADOW_HTTP_TIMEOUT", "8")))
    args = p.parse_args()

    syms = _symbols(args.symbols)
    if not syms:
        raise SystemExit("No symbols configured")
    if args.poll_sec < 10:
        raise SystemExit("poll-sec must be >= 10 to avoid unnecessary API load")
    if args.ttl_sec < int(args.poll_sec * 2):
        raise SystemExit("ttl-sec must be at least 2x poll-sec")

    redis_client = RedisConfig().client
    if redis_client is None:
        raise SystemExit("Redis unavailable")

    session = requests.Session()
    session.headers.update({"User-Agent": "binance1-okx-oi-shadow/1.0"})

    if args.once:
        return 1 if run_once(redis_client, session, syms, args.period, args.ttl_sec, args.timeout) else 0

    print(f"START shadow-only symbols={','.join(syms)} period={args.period} poll_sec={args.poll_sec} ttl_sec={args.ttl_sec}")
    while True:
        started = time.monotonic()
        run_once(redis_client, session, syms, args.period, args.ttl_sec, args.timeout)
        elapsed = time.monotonic() - started
        time.sleep(max(1.0, args.poll_sec - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
