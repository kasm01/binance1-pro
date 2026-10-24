from __future__ import annotations

import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import redis

from orchestration.risk.central_risk_master import (
    EntryRiskRequest,
    PortfolioRiskState,
    PositionExposure,
)
from orchestration.risk.central_risk_enforce_dry_profile import (
    BASE_REQUEST_BUDGET_RATIO,
    PROFILE_ID,
    PROFILE_STAGE,
    VALIDATED_STRATEGIES,
    build_enforce_dry_master,
    describe_profile,
)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379") or 6379)
REDIS_DB = int(os.getenv("REDIS_DB", "0") or 0)
REQUEST_STREAM = os.getenv("CENTRAL_RISK_REQUEST_STREAM", "central:risk:requests:v1")
DECISION_STREAM = os.getenv("CENTRAL_RISK_DECISION_STREAM", "telemetry:central_risk:decisions:v1")
SNAPSHOT_KEY = os.getenv("CENTRAL_RISK_CURRENT_KEY", "telemetry:central_risk:shadow:current")
RESERVATION_HASH = os.getenv("CENTRAL_RISK_DRY_RESERVATION_HASH", "central:risk:dry:reservations:v1")
GROUP = os.getenv("CENTRAL_RISK_GATE_GROUP", "central_risk_gate_g1")
CONSUMER = os.getenv("CENTRAL_RISK_GATE_CONSUMER", f"gate-{socket.gethostname()}")
SNAPSHOT_MAX_AGE_SEC = float(os.getenv("CENTRAL_RISK_MAX_AGE_SEC", "420") or 420)
RESPONSE_TTL_SEC = int(os.getenv("CENTRAL_RISK_RESPONSE_TTL_SEC", "30") or 30)
RESERVATION_TTL_SEC = int(os.getenv("CENTRAL_RISK_DRY_RESERVATION_TTL_SEC", "21600") or 21600)
MAXLEN = int(os.getenv("CENTRAL_RISK_DECISION_MAXLEN", "10000") or 10000)


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _load_json(raw: Any) -> Dict[str, Any]:
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _actual_positions(snapshot: Dict[str, Any]) -> List[PositionExposure]:
    out: List[PositionExposure] = []
    for row in snapshot.get("positions") or []:
        if not isinstance(row, dict):
            continue
        notional = max(0.0, _f(row.get("notional")))
        side = str(row.get("side") or "").lower().strip()
        if notional <= 0.0 or side not in {"long", "short"}:
            continue
        out.append(PositionExposure(
            strategy_id=str(row.get("strategy_id") or "").upper().strip(),
            symbol=str(row.get("symbol") or "").upper().strip(),
            side=side,
            notional=notional,
            opened_risk_mode=str(row.get("opened_risk_mode") or "NORMAL"),
        ))
    return out


def _clean_and_load_reservations(r: redis.Redis, actual: List[PositionExposure]) -> List[PositionExposure]:
    now = time.time()
    actual_ids = {p.strategy_id.upper() for p in actual if p.strategy_id}
    out: List[PositionExposure] = []
    rows = r.hgetall(RESERVATION_HASH) or {}
    for strategy_id, raw in rows.items():
        obj = _load_json(raw)
        expires_at = _f(obj.get("expires_at"))
        if expires_at <= now or str(strategy_id).upper() in actual_ids:
            r.hdel(RESERVATION_HASH, strategy_id)
            continue
        notional = max(0.0, _f(obj.get("notional")))
        side = str(obj.get("side") or "").lower().strip()
        symbol = str(obj.get("symbol") or "").upper().strip()
        if notional <= 0.0 or side not in {"long", "short"} or not symbol:
            r.hdel(RESERVATION_HASH, strategy_id)
            continue
        out.append(PositionExposure(
            strategy_id=str(strategy_id).upper(),
            symbol=symbol,
            side=side,
            notional=notional,
            opened_risk_mode=str(obj.get("opened_risk_mode") or "NORMAL"),
        ))
    return out


def _response(r: redis.Redis, request_id: str, payload: Dict[str, Any]) -> None:
    payload = dict(payload)
    payload.setdefault("request_id", request_id)
    payload.setdefault("ts", time.time())
    payload.setdefault("profile_id", PROFILE_ID)
    payload.setdefault("profile_stage", PROFILE_STAGE)
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    if request_id:
        r.setex(f"central:risk:response:{request_id}", RESPONSE_TTL_SEC, raw)
    r.xadd(DECISION_STREAM, {"json": raw}, maxlen=MAXLEN, approximate=True)


def _load_snapshot(r: redis.Redis) -> tuple[Dict[str, Any], str]:
    raw = r.get(SNAPSHOT_KEY)
    if not raw:
        return {}, "snapshot_missing"
    snap = _load_json(raw)
    age = max(0.0, time.time() - _f(snap.get("ts")))
    if age > SNAPSHOT_MAX_AGE_SEC:
        return snap, f"snapshot_stale:{age:.1f}s"
    health = snap.get("exposure_health") if isinstance(snap.get("exposure_health"), dict) else {}
    if str(health.get("status") or "").upper() == "BREACH" or bool(health.get("freeze_new_entries")):
        return snap, "snapshot_exposure_breach"
    return snap, ""


def _handle(r: redis.Redis, req: Dict[str, Any]) -> Dict[str, Any]:
    request_id = str(req.get("request_id") or uuid.uuid4())
    action = str(req.get("action") or "EVALUATE_OPEN").upper().strip()
    strategy_id = str(req.get("strategy_id") or "").upper().strip()

    if action == "PING":
        return {"request_id": request_id, "state": "READY", "reason": "pong", "profile": describe_profile()}

    if action == "RELEASE":
        if strategy_id:
            r.hdel(RESERVATION_HASH, strategy_id)
        return {"request_id": request_id, "state": "READY", "reason": "reservation_released", "strategy_id": strategy_id}

    mode = str(req.get("request_mode") or "DRY_RUN").upper().strip()
    if mode != "DRY_RUN":
        return {"request_id": request_id, "state": "REJECT", "reason": "live_not_authorized", "strategy_id": strategy_id}
    if strategy_id not in {str(x).upper() for x in VALIDATED_STRATEGIES}:
        return {"request_id": request_id, "state": "REJECT", "reason": "strategy_not_validated", "strategy_id": strategy_id}

    snap, snap_error = _load_snapshot(r)
    if snap_error:
        return {"request_id": request_id, "state": "REJECT", "reason": snap_error, "strategy_id": strategy_id}

    account = snap.get("account") if isinstance(snap.get("account"), dict) else {}
    portfolio = snap.get("portfolio_state") if isinstance(snap.get("portfolio_state"), dict) else {}
    equity = max(0.0, _f(account.get("mtm_equity")))
    state = PortfolioRiskState(
        equity_peak=max(equity, _f(portfolio.get("equity_peak"), equity)),
        mode=str(portfolio.get("mode") or "NORMAL"),
        recovery_successes=int(_f(portfolio.get("recovery_successes"), 0)),
    )

    actual = _actual_positions(snap)
    reservations = _clean_and_load_reservations(r, actual)
    positions = actual + reservations

    symbol = str(req.get("symbol") or "").upper().strip()
    side = str(req.get("side") or "").lower().strip()
    context_mult = max(0.0, min(1.0, _f(req.get("market_context_multiplier"), 1.0)))
    # Central authority owns the base request budget. Strategy engines may only
    # reduce risk through market_context_multiplier; they cannot raise this cap.
    base_budget = float(BASE_REQUEST_BUDGET_RATIO)
    requested_notional = equity * base_budget

    master = build_enforce_dry_master()
    decision = master.evaluate_entry(
        request=EntryRiskRequest(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            requested_notional=requested_notional,
            market_context_multiplier=context_mult,
        ),
        state=state,
        portfolio_equity=equity,
        positions=positions,
    ).to_dict()

    reserve_raw = req.get("reserve", 1)
    if isinstance(reserve_raw, bool):
        reserve = reserve_raw
    elif isinstance(reserve_raw, (int, float)):
        reserve = bool(int(reserve_raw))
    else:
        reserve = str(reserve_raw).strip().lower() in {"1", "true", "yes", "on"}
    if decision.get("state") == "READY" and reserve:
        allowed = max(0.0, _f(decision.get("allowed_notional")))
        obj = {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "side": side,
            "notional": allowed,
            "opened_risk_mode": str(decision.get("portfolio_mode") or state.normalized_mode()),
            "created_at": time.time(),
            "expires_at": time.time() + RESERVATION_TTL_SEC,
            "request_id": request_id,
        }
        r.hset(RESERVATION_HASH, strategy_id, json.dumps(obj, separators=(",", ":")))

    return {
        "request_id": request_id,
        "state": str(decision.get("state") or "REJECT"),
        "reason": "central_risk_decision",
        "strategy_id": strategy_id,
        "symbol": symbol,
        "side": side,
        "snapshot_ts": snap.get("ts"),
        "snapshot_authority": snap.get("authority"),
        "base_budget_ratio": base_budget,
        "reservation_count_before": len(reservations),
        "decision": decision,
    }


def main() -> int:
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True, socket_timeout=2.0)
    r.ping()
    try:
        r.xgroup_create(REQUEST_STREAM, GROUP, id="$", mkstream=True)
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    print(f"CENTRAL_RISK_ENFORCE_DRY started profile={PROFILE_ID} stream={REQUEST_STREAM} group={GROUP} consumer={CONSUMER}", flush=True)
    while True:
        rows = r.xreadgroup(GROUP, CONSUMER, {REQUEST_STREAM: ">"}, count=20, block=5000)
        if not rows:
            continue
        for _, entries in rows:
            for sid, fields in entries:
                req = _load_json(fields.get("json"))
                request_id = str(req.get("request_id") or uuid.uuid4())
                try:
                    out = _handle(r, req)
                except Exception as exc:
                    out = {"request_id": request_id, "state": "REJECT", "reason": "central_gate_exception", "detail": str(exc)[:220]}
                _response(r, request_id, out)
                r.xack(REQUEST_STREAM, GROUP, sid)


if __name__ == "__main__":
    raise SystemExit(main())
