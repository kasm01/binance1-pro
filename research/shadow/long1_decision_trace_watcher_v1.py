#!/usr/bin/env python3
"""Read-only LONG1 production-stream observer; never publishes or sends orders."""
from __future__ import annotations
import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

import redis

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/shadow"))
import long1_decision_fusion_v1 as fusion

STREAMS = ("signals_stream_long1", "exec_events_stream_long1",
           "shadow:telemetry:position_outcome")
OUT = ROOT / "research/results/LONG1_DECISION_TRACE_SHADOW.jsonl"

def key_snapshot(r):
    data = fusion.read_json(r, fusion.COMBINED_KEY)
    for part, key in (
        ("binance_structure", "shadow:market_context:binance_structure:NEARUSDT"),
        ("binance_microstructure", "shadow:market_context:microstructure:NEARUSDT"),
        ("okx_oi", "shadow:market_context:okx_oi:NEARUSDT"),
    ):
        obj = fusion.read_json(r, key)
        if obj:
            data[part] = obj
    return data

def decode(fields):
    obj = json.loads(fields.get("json") or "{}")
    return obj if isinstance(obj, dict) else {}

def compact_event(stream, event, event_id, received_ms, r):
    if stream == STREAMS[0]:
        # ID of Redis stream event is the observed transport ID.
        item = dict(event)
        item["observed_at_ms"] = int(event_id.split("-")[0])
        result = fusion.classify(key_snapshot(r), fusion.read_json(r, fusion.GATE_KEY),
                                 received_ms, item)
        result.update(stream=stream, stream_event_id=event_id,
                      stream_delay_sec=fusion.age(item["observed_at_ms"], received_ms))
        return result

    if stream == STREAMS[1]:
        items = event.get("items", [])
        return {
            "schema_version": "long1_decision_trace_shadow.v1",
            "stream": stream, "stream_event_id": event_id,
            "observed_at_ms": received_ms, "shadow_only": True,
            "event_type": "EXECUTION_INTENT_OBSERVED_NOT_ORDER_PROOF",
            "items": [
                {"intent_id": str(i.get("intent_id") or ""),
                 "symbol": str(i.get("symbol") or ""),
                 "side": str(i.get("side") or ""),
                 "model_score": fusion.number(i.get("model_score"))}
                for i in items if isinstance(i, dict)
            ][:10]
        }
    return {
        "schema_version": "long1_decision_trace_shadow.v1",
        "stream": stream, "stream_event_id": event_id,
        "observed_at_ms": received_ms, "shadow_only": True,
        "event_type": "OUTCOME_TELEMETRY_OBSERVED",
        "symbol": str(event.get("symbol") or ""),
        "side": str(event.get("side") or ""),
        "exit_reason": str(event.get("exit_reason") or event.get("reason") or ""),
        "source_event_observed_at_ms": event.get("observed_at_ms")
    }

def run(seconds, output):
    r = redis.Redis(host="127.0.0.1", port=6379,
                    decode_responses=True, socket_timeout=3,
                    socket_connect_timeout=2)
    r.ping()
    # '$' means NEW events only. Do not consume pending/historical messages.
    cursors = {stream: "$" for stream in STREAMS}
    deadline = time.monotonic() + seconds if seconds else None
    stop = False
    def shutdown(signum, frame):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    print("SHADOW_ONLY listening NEW events", ",".join(STREAMS), flush=True)
    while not stop and (deadline is None or time.monotonic() < deadline):
        try:
            batch = r.xread(cursors, count=20, block=1000)
        except redis.RedisError as exc:
            print("READ_ERROR", type(exc).__name__, flush=True)
            time.sleep(1)
            continue
        for stream, rows in batch:
            for event_id, fields in rows:
                cursors[stream] = event_id
                received_ms = int(time.time() * 1000)
                if fusion.age(int(event_id.split("-")[0]), received_ms) is None:
                    continue
                if fusion.age(int(event_id.split("-")[0]), received_ms) > 180:
                    print("SKIP_STALE",stream,event_id,flush=True)
                    continue
                try:
                    item = decode(fields)
                    out = compact_event(stream, item, event_id, received_ms, r)
                    # local append only; intentionally NO Redis writes.
                    with output.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
                    print("OBSERVED", stream, event_id, out.get("advisory_action",
                          out.get("event_type", "")), flush=True)
                except (ValueError, TypeError, KeyError, OSError) as exc:
                    print("EVENT_ERROR",stream,event_id,type(exc).__name__,flush=True)
    print("SHADOW_STOPPED",flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=int, default=15,
                   help="0 = until SIGTERM; otherwise bounded, default 15s")
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    if args.seconds < 0:
        p.error("--seconds must be >= 0")
    run(args.seconds, args.out)

if __name__ == "__main__":
    main()
