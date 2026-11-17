# LONG1 — Stage 17: central portfolio risk, unknown-position fail-open, isolated release contract
Date: 2026-11-17 UTC. All user binance1-* services and timers stopped; Redis infrastructure alone running.

## Critical evidenced findings
1. `core/trade_executor.py::_count_open_positions_for_side` silently suppresses errors from the local `positions.values()` store and falls back to `_count_open_positions()`, which itself suppresses exchange and Redis exceptions and can return zero. Therefore the previous Stage 16 upper-layer exception-only patch is NOT SUFFICIENT to fail closed.
2. Using extracted ACTUAL method AST in a sandbox: local positions object raising OSError -> `_count_open_positions_for_side('long') == 0`; then ACTUAL `_evaluate_long_execution_risk_gate` returned TRUE even though underlying state was unreadable. No real exchange or Redis call in experiment.
3. `_get_effective_position` returns None for local/exchange no-position; its callers cannot distinguish an independently verified flat account from an unavailable exchange state without an authoritative freshness contract.
4. CentralRiskMaster is a pure in-memory portfolio sizing engine and its current `central_risk_enforce_dry` profile has `production_authorized=False`. `evaluate_entry` can return `state='READY'` while `production_ready=False`. Calling code must check BOTH, plus authoritative position/epoch proofs, before any live order.
5. Source search of actual LONG1 `main.py`, MasterExecutor and TradeExecutor did not reveal direct use of `CentralRiskMaster` in live opening path. A shared dry-risk service alone is not demonstrated to be a synchronous live order authority. This must be separately integrated only after proper release authorization and atomic reservation semantics.

## Tests
- `research/trace/test_long1_stage17_central_risk_failopen_offline.py`: 3 production methods extracted in-memory, unknown count -> 0, local Execution Risk -> allow, CentralRiskMaster dry profile READY while non-production; central two-position cap and per-strategy existing-position reject.
- `research/staging/long1_stage17_risk_release_contract_v1.py`: proposed PURE pre-order fail-closed *candidate* contract; no installation or API authority.
- `research/trace/test_long1_stage17_risk_release_contract.py`: 16 tests, one synthetic positive `risk_release_candidate_only` and 15 fail-closed cases including invalid/stale/incomplete snapshot, missing epoch, mismatch, central policy reject, unauthorized production, invalid amount, wrong strategy/symbol/side.
- Tests ran with zero Redis writes, zero exchange calls and zero order submission.

## Important limitations
- The positive pure helper result does NOT authorize actual exchange orders. It has no authenticated exchange snapshot provider, atomic reservation, order ID, current open orders, native stop confirmation, latency bound, TTL or independent idempotency receipt.
- The Stage16 pending/guard-chain test also stubs the terminal order method and cannot be called full Final Safety validation.
- Do not merely patch upper-layer exception and restart: the lower-level swallowing of unknown position errors remains.
- No production changes were made to `core/trade_executor.py`, `main.py`, orchestration, Redis, .env, systemd units or Binance.
- Final risk production release gate remains NO GO.

## Next required gate
Build an independent authoritative LONG1+SHORT1 portfolio snapshot adapter with explicit freshness, authoritative server time, complete position/open-order/stop coverage, dual-side semantics and error->UNKNOWN status. Prove atomic reservations and stale replay protection in independent Redis test instance before connecting to the real order path. Use fail-closed live profile only after verified authorization. Keep native stop safety separate from execution risk.
