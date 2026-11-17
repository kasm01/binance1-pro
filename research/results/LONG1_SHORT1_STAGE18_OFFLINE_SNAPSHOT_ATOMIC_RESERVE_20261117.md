# Aşama 18 — LONG1 + SHORT1 authoritative snapshot / isolated reservation
Date: 2026-11-17. All binance1-* bot services/timers were verified stopped before and after tests. Redis infrastructure remained active and untouched.

## Existing SHORT1 implementation reused, not reinvented
- `~/binance1/orchestration/risk/binance_exact_readonly_adapter_v1.py`: read-only signed GET methods for NEARUSDT/INJUSDT positions, open standard orders, open algo orders, order and fills. No POST. Not invoked against live exchange in Stage 18.
- `~/binance1/orchestration/risk/authoritative_snapshot_evidence_v1.py`: strict account/equity/DD mode consistency checker. Existing isolated unit tests: PASS 12. Critically, state `CONSISTENT_READONLY` still returns `can_authorize_new_reservation=False`.
- `~/binance1/orchestration/risk/central_reservation_redis_v2_research.py`: actual Lua atomic reservation prototype in a separate Redis ephemeral server.
- `~/binance1/research/tests/test_central_risk_redis_v2_isolated_v1.py`: PASS. Server uses port=0 and unixsocket only, no persistence, 24 MB noeviction. 60 concurrent SHORT1 reservation requests -> only ONE ready; duplicate idempotency, ownership, expiry and restart-closed verified. LONG1+SHORT1 2-slot budget: 46+46 on 100 synthetic equity, not evidence for LIVE budget.
- Important limitation: `OPEN_GATE` accepts fixed `ISOLATED_TEST_RECONCILED` test string; not a verifiable real exchange epoch. `RELEASE` uses a string flag and does not independently verify exchange flat. This protocol must NEVER be deployed as live authority without replacing test proofs with trusted attested snapshots, epoch, fencing tokens and account-wide reconciliation.

## New read-only research prototype
- `research/staging/stage18_shared_portfolio_snapshot_v1.py`: strict two-symbol snapshot data validator. Nonfinite values, wrong symbols/side, duplicates, missing lists, stale/invalid clock, incomplete account equity, unverified standard/algo orders -> UNKNOWN. No derived order permission.
- `research/trace/test_stage18_shared_portfolio_snapshot_v1.py`: PASS 15 negative UNKNOWN cases, positive flat and two open legs, one open standard order recognized; *none* authorizes live order.
- `research/staging/stage18_broker_snapshot_reader_v1.py`: dependency-injected account + positions/orders/algos capture. 7 mocked reads: account, two position endpoints, two open standard order endpoints, two algo endpoints.
- `research/trace/test_stage18_broker_snapshot_reader_v1.py`: PASS 7 missing/unavailable endpoints -> UNKNOWN, excessive snapshot duration -> UNKNOWN. No actual Binance calls; source_complete flag is local and is not cryptographically authenticated.
- These are **schemas**, not a production authoritative market account adapter. No independent signed response verification, account identity, server time, remote sequence/epoch, mark to market drift, symbol-universe completeness beyond NEARUSDT/INJUSDT, hidden fills/partially filled orders, strategy ownership, available margin reservation, true atomic commit authority or native stop completeness proven.

## Architecture and stage gates
- One central signal bus / one risk authority / telemetry across 8 strategy engines. Only LONG1 and SHORT1 eligible for current isolated experiments.
- Prospective live pipeline: all requested symbols + account exposure -> trusted bounded snapshot -> CentralRiskMaster profile authorization -> atomic reservation with epoch and fencing token -> Execution Risk -> Final Safety (reconfirm authoritative state/stop) -> order submission -> exchange ACK/FILL independently verified -> lifecycle -> outcome.
- Under ANY unknown/missing/restarted/stale state, BLOCK new risk; do not treat UNKNOWN as flat.
- Release gate remains NO-GO: live TradeExecutor still has position error-to-zero behavior from Stage 17. Snapshot/read-only results and mock tests are not live integration.
- DO NOT restart the bot with live env until all risk gates are fixed and verified on both stacks.

## Operational controls
- No LIVE Binance request, no live Redis mutation, no source edits to production main.py, core/trade_executor.py, SHORT1 risk module or service configs. Only `research/staging`, `research/trace`, and this report added.
- Disk 40GB, ~6.6GB free, 83% used. Bot services and timers stopped.
