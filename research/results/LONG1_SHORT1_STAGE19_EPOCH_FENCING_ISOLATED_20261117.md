# Aşama 19 — Fenced central risk reservation in isolated AOF Redis
Date: 2026-11-17 UTC. Bot stack stopped. NO live Binance or production Redis writes.

## Reused evidence / existing work
- Stage18 `stage18_shared_portfolio_snapshot_v1.py` checks both NEARUSDT and INJUSDT inputs; all outputs explicitly NOT live-authorized.
- SHORT1 research already contains `isolated_reconcile_epoch_v2.py` and `atomic_reserve_mode_journal_v3_research.py` with staged modes and sticky risk severity; they remain unreleased.
- Existing isolated reservation in SHORT1 relies on a hardcoded `ISOLATED_TEST_RECONCILED` marker, which cannot authenticate real Binance positions.

## New Stage19 research
- `research/staging/stage19_epoch_fencing_reservation_v1.py`: standalone Lua protocol research only. BEGIN increments monotonically persisted epoch and closes gate BEFORE any broker read. PUBLISH requires exact latest epoch + local digest + EXPLICIT RESEARCH-ONLY marker, never grants live authority. Atomic RESERVE increments a persistent fencing serial; request ID, strategy, symbol, side, epoch, digest and token are bound. Every result says live_order_authorized=false. Owner mismatch, old epoch, unknown digest, missing pending, expired idempotent replay and expired commit fail closed.
- `research/trace/test_stage19_epoch_fencing_isolated_redis_v1.py`: Redis server listening solely on chmod-0600 UNIX socket, TCP port 0, separate tempdir, AOF appendfsync always, 32MiB noeviction. 60 simultaneous attempts for one strategy -> exactly one accepted; a separate SHORT1 strategy gets its own reservation; third conflicting request fails. Only one per strategy slot, total two.
- Late PUBLISH and COMMIT with old epoch rejected. Unresolved reserved positions prohibit new research snapshot gate from reopening; restart persists epoch/fence and pending, but default gate remains CLOSED. Replayed idempotent same request is permitted only until expiration. Late retries after expiration rejected. Wrong token cannot commit/release.
- Synthetic fresh isolated prefix demonstrates a new fenced research reservation and synthetic COMMIT; this is NOT proof of actual exchange fill.

## Material security caveats and NO-GO
1. Digest currently computed with a LOCAL TEST HMAC key, while Lua does not authenticate signed Binance/broker receipts. `LOCAL_RESEARCH_VERIFIED` is explicitly a test marker. Any isolated Redis client with write permissions could submit a fabricated digest. NEVER deploy this Lua as a live gate or construe PUBLISH READY as authority.
2. The research protocol has no authenticated account identity, exchange server clock, complete multi-symbol portfolio validation, fill status, non-test reconciliation credential, position ownership proof, available-margin/funding/fees/slippage envelope or true production CentralRiskMaster sizing. The synthetic RESERVE never authorizes exchange orders.
3. Atomic AOF epoch and fencing serials are scoped to a specific database/prefix and its durable Redis instance; a restore/rebuild could reuse counters. Production must use durable fenced generations across disaster recovery and reconfiguration, plus authenticated source evidence and operator-approved reconciliation.
4. Beginning a new observation invalidates old reservations' ability to COMMIT. Outstanding reservations remain persistent and freeze new risk until independently and explicitly reconciled; DO NOT force-clear or treat an expired pending as flat.
5. No independent Final Safety or native stop attachment at actual exchange was tested. No changes to the live LONG1/SHORT1 source, systemd settings, .env, Redis store, orders or Binance position state.
6. Existing live LONG1 `_count_open_positions_for_side()` may still turn unknown source errors into 0, so release gate is **NO-GO**.

## Test output
- `PYTHONPATH=. ./venv/bin/python research/trace/test_stage19_epoch_fencing_isolated_redis_v1.py`: PASS
- Test server is terminated and its temporary files removed on exit.
- Production Redis remains untouched; only `research/` files added.

## Next recommended engineering
Aşama 20: design authenticated, independent broker snapshot evidence and risk mode journal; separately bind true order-intent ledger and STOP order evidence. Reject or quarantine stale, partial, or conflicting observations; run through isolated AOF crash/restart/reconciliation tests before proposing *any* production risk integration.
