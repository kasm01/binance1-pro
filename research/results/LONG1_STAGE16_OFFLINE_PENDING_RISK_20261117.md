# Stage 16 — Offline PENDING + Execution Risk + pre-order gate audit
Date: 2026-11-17. All binance1 systemd services and timers stopped at audit, Redis infrastructure remains running; no bot orders or Redis writes.

## Extracted REAL code under test
`research/trace/test_long1_stage16_pending_safety_offline.py` extracts nine actual methods from `core/trade_executor.py` using AST into a new isolated in-memory class. It does NOT import or instantiate actual TradeExecutor; actual order pipeline is replaced with fake sink.

- 11 canonical PENDING window cases: confirmation, early, late, current / next / expired, too-early and invalid clock; observed state ready/wait/expired/invalid as expected.
- 5 PENDING process transition cases with downstream model-evaluation stubs: ready, wait-preparation, wait-revalidation, block-revalidation, expired-cleared.
- 8 actual execution-risk A/B decisions (metadata absent vs present): empty allows, same-side open blocks, opposite-side open blocks, position count limit blocks. Risk scale-in disabled via local process env override. No decision differences.
- 4 actual _execute_long_validated_candidate path-order tests with synthetic guard/price/order sink: Contra -> Risk -> Price -> OrderPrice -> fake order; every early reject prevents reaching fake order.
- This does NOT run full order pipeline, independent Binance final safety, real position state or exchange fills.

## CRITICAL FINDING: risk count fail-open
- Original `_evaluate_long_execution_risk_gate` catches Exception around `_count_open_positions_for_side` and falls through to `return True`.
- Offline fault injection raising RuntimeError from that counter resulted in allow=True despite inability to determine open-position limit. That is dangerous in multi-bot coordination.
- Prospective isolated no-go patch `LONG1_STAGE16_UNAPPLIED_RISK_FAILCLOSED_20261117.diff`: return False on count exception with guarded log. It preserves normal allow and cap-block behavior in tests. Source file not changed.
- The future Risk Master design should make missing authoritative positions fail closed. DO NOT deploy or restart until snapshot consistency and rollbacks confirmed.

## Operational verification
- `./scripts/binance1_stack_control.sh check` shows no binance1 services, timers, or collectors.
- Free disk ~6.6GB, usage ~83%.
- Original production file checksum recorded in test report; no live code edits.
- Release gate: **NO GO**.
