# LONG1 Decision Trace Shadow V1

## Goal
Observe new LONG1 model events and resulting execution-intent and outcome telemetry while leaving production routing, score gates, orders, pending state, risk and lifecycle unchanged.

## Files
- `research/shadow/long1_decision_fusion_v1.py`: one-shot advisory evaluation using existing Redis shadow market-context caches; no order access.
- `research/shadow/long1_decision_trace_watcher_v1.py`: watches only NEW Redis stream events from the moment it starts, without consumer groups or writes to Redis.
- `scripts/systemd/binance1-long1-decision-shadow.service`: separate observer service. Installed as user unit; *not enabled at boot*.
- `research/results/LONG1_DECISION_TRACE_SHADOW.jsonl`: created after first new eligible event. Contains model-stage advice, observed execution-intent notices and outcome telemetry notices.

## Run / inspect
`systemctl --user status binance1-long1-decision-shadow.service`
`journalctl --user -u binance1-long1-decision-shadow.service -n 30 --no-pager`
`tail -n 5 research/results/LONG1_DECISION_TRACE_SHADOW.jsonl`

Stop observer only: `systemctl --user stop binance1-long1-decision-shadow.service`.
Restart observer only: `systemctl --user restart binance1-long1-decision-shadow.service`.
The original three startup commands continue to work. The observer is not added to `shadow_start.sh` yet to avoid unexpected startup changes.

## Safety and limitations
- Only receives from Redis, writes JSONL locally, and reads existing shadow keys. No new Binance API calls, Redis stream writes, trading import or exchange order access.
- A trace `READY` is an **advisory** independent of Sniper, current candidate revalidation, execution risk and final safety. It MUST NOT be treated as authorization to open.
- Observed `exec_events_stream_long1` indicates an execution *intent*, not proof of filled order. `position_outcome` is shadow telemetry; full order/fill-to-candidate joining is not implemented in V1.
- Missing whale data is `UNKNOWN`, not inferred from OI or taker money flow. `4H` OI direction is not automatically LONG/SHORT direction.
- `source_age_sec` and cache observed time are checked independently. The first pass of the combined cache omitted some source timestamps, which are now read directly from original shadow caches.
- Only fresh events (<=180 seconds) are recorded; old messages are not replayed. First startup from Redis XREAD `$` avoids stale processing.
- Output files are small, append-only; review disk free space (previously 91% full) if monitoring for months.

## Future stages
1. On next genuine qualifying LONG1 signal, inspect event_id/candidate_id and advisory vs actual executor log.
2. Make deterministic correlation of model event -> intent -> actual order/fill -> outcome without relying on score/time heuristic alone.
3. Shadow-vs-base paired OOS results: return, fees, PF, drawdown, false rejected winners, and latency.
4. Only after evidence, decide whether to grant any authority to Data Quality/Fusion; keep 8-bot centralized Risk Master design.
