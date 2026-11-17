#!/usr/bin/env python3
"""LONG1 read-only market intelligence fusion research. NEVER sends orders."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import time
from pathlib import Path

import redis

ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "NEARUSDT"
COMBINED_KEY = "shadow:market_context:combined:" + SYMBOL
GATE_KEY = "long1:model_gate:rolling:" + SYMBOL + ":state:v1"

def number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def age(observed_ms, now_ms):
    x = number(observed_ms)
    return max(0.0, (now_ms - x) / 1000) if x and x <= now_ms + 10000 else None

def expert(name, direction, quality, reason, confidence=None, **values):
    return dict(expert=name, direction=direction, quality=quality,
                reason=reason, confidence=confidence, **values)

def classify(data, gate, now_ms, candidate=None):
    st = data.get("binance_structure") or {}
    micro = data.get("binance_microstructure") or {}
    oi = data.get("okx_oi") or {}
    der = data.get("derived") or {}
    specs = {}

    st_age = age(st.get("observed_at_ms"), now_ms)
    st_ok = (st.get("status") == "OK" and st_age is not None and st_age <= 180)
    if st_ok:
        long = bool(der.get("m3_persistence_long"))
        short = bool(der.get("m3_persistence_short"))
        direction = "LONG" if long else "SHORT" if short else "NEUTRAL"
        specs["market_direction"] = expert("market_direction", direction, "VALID",
             "completed_3m_persistence", source_age_sec=round(st_age, 2))
    else:
        specs["market_direction"] = expert("market_direction", "UNKNOWN", "STALE",
             "structure_missing_or_stale", source_age_sec=st_age)

    f15 = number(der.get("taker_flow15_completed"))
    f60 = number(der.get("taker_flow60_completed"))
    if st_ok and f15 is not None and f60 is not None:
        sign = "LONG" if f15 > 0 and f60 > 0 else "SHORT" if f15 < 0 and f60 < 0 else "MIXED"
        specs["money_flow"] = expert("money_flow", sign, "VALID",
             "signed_completed_taker_flow", flow15=f15, flow60=f60,
             source_age_sec=round(st_age, 2))
    else:
        specs["money_flow"] = expert("money_flow", "UNKNOWN", "MISSING",
             "completed_flow_unavailable", source_age_sec=st_age)

    m_age = age(micro.get("observed_at_ms"), now_ms)
    m_ok = micro.get("status") == "OK" and m_age is not None and m_age <= 15
    specs["microstructure"] = expert("microstructure",
        "LONG" if m_ok and number(micro.get("t15_signed_ratio")) is not None and float(micro["t15_signed_ratio"]) > 0.1
        else "SHORT" if m_ok and number(micro.get("t15_signed_ratio")) is not None and float(micro["t15_signed_ratio"]) < -0.1
        else "NEUTRAL" if m_ok else "UNKNOWN",
        "VALID" if m_ok else "STALE", "live_orderflow_observation" if m_ok else "micro_missing_or_stale",
        source_age_sec=m_age, spread_bps=number(micro.get("spread_bps")))

    oi_cache_age = age(oi.get("observed_at_ms"), now_ms)
    oi_source_age = number(oi.get("source_age_sec"))
    # 4H observations: cache must be fresh; source max 5 hours (4h candle + tolerance).
    oi_ok = oi.get("status") == "OK" and oi_cache_age is not None and oi_cache_age <= 300 and (
        oi_source_age is not None and oi_source_age <= 18000)
    specs["structure_oi"] = expert("structure_oi",
        str(oi.get("oi_direction") or "UNKNOWN").upper() if oi_ok else "UNKNOWN",
        "VALID_4H" if oi_ok else "STALE",
        "4h_oi_direction_not_trade_direction" if oi_ok else "oi_cache_or_source_stale",
        source_age_sec=oi_source_age, cache_age_sec=oi_cache_age,
        oi_change=number(oi.get("oi_ret_period")))

    # Whale is a distinct signal. Never substitute taker flow or OI for it.
    wd = str((candidate or {}).get("whale_dir") or "none").lower()
    ws = number((candidate or {}).get("whale_score"))
    whale_known = wd in ("long", "short", "buy", "sell") and ws is not None
    wd = "LONG" if wd in ("long", "buy") else "SHORT" if wd in ("short", "sell") else "UNKNOWN"
    specs["whale"] = expert("whale", wd if whale_known else "UNKNOWN",
        "VALID" if whale_known else "MISSING", "candidate_whale_context" if whale_known else "no_fresh_candidate_whale_evidence",
        confidence=ws if whale_known else None)

    gate_age = age(number(gate.get("ts")) * 1000 if number(gate.get("ts")) is not None else None, now_ms)
    gate_valid = gate_age is not None and gate_age <= 300 and number(gate.get("threshold")) is not None
    score = number((candidate or {}).get("model_score"))
    side = str((candidate or {}).get("side_candidate") or (candidate or {}).get("side") or "").upper()
    candidate_ok = side in ("LONG", "SHORT") and score is not None

    if not candidate_ok:
        action, why = "NO_CANDIDATE", ["no_fresh_eligible_model_event"]
    elif side != "LONG":
        action, why = "NOT_APPLICABLE", ["long1_only_no_short_routing"]
    elif not 0.0 <= score <= 1.0:
        action, why = "REJECT", ["invalid_model_score"]
    elif not gate_valid:
        action, why = "PENDING", ["rolling_gate_state_stale"]
    elif side == "LONG" and score < float(gate["threshold"]):
        action, why = "REJECT", ["model_below_current_gate"]
    else:
        conflicts = [key for key in ("market_direction", "money_flow")
                     if specs[key]["direction"] == ("SHORT" if side == "LONG" else "LONG")]
        insufficient = [key for key in ("market_direction", "money_flow", "whale")
                        if specs[key]["quality"] not in ("VALID", "VALID_4H")]
        if conflicts:
            action, why = "PENDING", ["direction_conflict:" + ",".join(conflicts)]
        elif insufficient:
            action, why = "PENDING", ["insufficient_evidence:" + ",".join(insufficient)]
        else:
            action, why = "READY", ["shadow_evidence_aligned"]

    return {
        "schema_version": "long1_decision_fusion_shadow.v1",
        "observed_at_utc": dt.datetime.fromtimestamp(now_ms/1000, dt.timezone.utc).isoformat(),
        "symbol": SYMBOL, "shadow_only": True, "routing_changed": False,
        "order_authority": "NONE", "decision_authority": "ADVISORY_ONLY",
        "candidate_type": "EXPLICIT_EVENT" if candidate_ok else "NO_CANDIDATE",
        "candidate_id": str((candidate or {}).get("event_id") or (candidate or {}).get("intent_id") or "") or None,
        "model": {"side": side if candidate_ok else None, "score": score,
                  "rolling_gate": number(gate.get("threshold")) if gate_valid else None,
                  "gate_age_sec": gate_age, "gate_valid": gate_valid},
        "specialists": specs,
        "advisory_action": action, "reason_codes": why,
        "execution_risk": "NOT_EVALUATED", "final_safety": "NOT_EVALUATED"
    }

def read_json(r, key):
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else {}
    except (ValueError, redis.RedisError):
        return {}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--event-file", help="Optional JSON file of a single current model event")
    p.add_argument("--latest-signal", action="store_true", help="Read last model signal only if it is under 180s old")
    p.add_argument("--output", default=str(ROOT / "research/results/LONG1_DECISION_FUSION_SHADOW_LATEST.json"))
    a = p.parse_args()
    now = int(time.time()*1000)
    r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True, socket_timeout=2)
    r.ping()
    candidate = json.loads(Path(a.event_file).read_text()) if a.event_file else None
    if a.latest_signal and a.event_file:
        raise SystemExit("Choose only one event source")
    if a.latest_signal:
        events = r.xrevrange("signals_stream_long1", count=1)
        if events:
            sid, fields = events[0]
            stamp_ms = int(sid.split("-")[0])
            if age(stamp_ms, now) is not None and age(stamp_ms, now) <= 180:
                candidate = json.loads(fields.get("json") or "{}")
                candidate["observed_at_ms"] = stamp_ms
    if candidate is not None:
        event_ms = age(candidate.get("observed_at_ms") or candidate.get("event_time_ms"), now)
        if event_ms is None or event_ms > 180:
            raise SystemExit("EVENT_REJECTED: missing/stale observed_at_ms (max 180s)")
    data = read_json(r, COMBINED_KEY)
    # The combined projection may omit per-source observed_at_ms.
    # Use canonical raw caches to validate freshness independently.
    for part, key in (
        ("binance_structure", "shadow:market_context:binance_structure:" + SYMBOL),
        ("binance_microstructure", "shadow:market_context:microstructure:" + SYMBOL),
        ("okx_oi", "shadow:market_context:okx_oi:" + SYMBOL),
    ):
        original = read_json(r, key)
        if original:
            data[part] = original
    result = classify(data, read_json(r, GATE_KEY), now, candidate)
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ADVISORY_ONLY",result["advisory_action"],",".join(result["reason_codes"]))
    print("EXPERTS", " ".join(k + ":" + v["direction"] + "/" + v["quality"] for k,v in result["specialists"].items()))
    print("FILE",output)
if __name__ == "__main__":
    main()
