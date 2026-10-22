# Stage 4 Strategy Isolation Lock — 2026-10-22

## Scope
Stage 4 target: Redis / log / PID / service / state isolation before LONG2-4 + SHORT2-4 cloning.

## Shared resources (not strategy-cloned)
- `binance1-oi-context.service` is the single central Binance 5m OI collector.
- It now serves `INJUSDT,NEARUSDT` from one process.
- `context:oi:{symbol}` and `shadow:market_context:*:{symbol}` are market-data/context resources and remain symbol-shared.
- Removing the second NEAR OI process reduces duplicate process overhead without increasing request count.

## LONG1 isolation
- Main Redis bus/state names now carry `long1`.
- Structure/microstructure collectors accept `--strategy-id LONG1`.
- Strategy-owned model/hazard telemetry uses `shadow:telemetry:long1:*`.
- Shared symbol context remains `shadow:market_context:*:NEARUSDT`.
- Logs: `long1_near_structure.log`, `long1_near_microstructure.log`.
- PID files: `long1_near_structure.pid`, `long1_near_microstructure.pid`.
- Start/stop uses PID-file identity first and anchored strategy/symbol process matching only as migration fallback.

## SHORT1 isolation
- Main Redis bus/state names now carry `short1`.
- Economic scanner, lifecycle shadow and V44 hazard support generic `STRATEGY_ID/STRATEGY_SYMBOL/STRATEGY_*_STREAM` overrides with SHORT1-compatible fallback.
- Explicit SHORT1 systemd strategy profiles are active.
- Generic old `binance1-short-shadow*` units are retained but inactive.
- Active model service: `binance1-short1-model-shadow.service`.
- Active finalizer timer: `binance1-short1-model-shadow-finalizer.timer`.
- V30 lifecycle and V44 hazard services remain explicit `short1` units.

## Collision guard
- Registry: `config/strategy_isolation_registry.json`.
- Checker: `scripts/check_strategy_isolation.py`.
- Current result: `STRATEGY_ISOLATION_OK strategies=2 owned_identifiers=31 shared_patterns=5`.
- New LONG2/SHORT2 profiles must be added to the registry before service activation; duplicate or non-namespaced owned identifiers fail the checker.

## Operational validation
- `shadow_stop.sh` leaves no LONG1/SHORT1 shadow orphan processes.
- PID files are removed on stop and recreated on start with matching commands.
- `shadow_start.sh` restores LONG1 collectors, central OI, SHORT1 model/lifecycle/hazard and timers.
- Production orchestrator/supervisor remain inactive.

## Stage 4 decision
PASS for LONG1 + SHORT1 isolation foundation. Proceed to Stage 5 only after model/symbol inventory; do not blind-copy services or market-data collectors.
