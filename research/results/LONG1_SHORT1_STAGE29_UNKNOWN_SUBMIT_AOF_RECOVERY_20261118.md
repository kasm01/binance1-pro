# Stage29 — Durable unknown-submit recovery and fenced risk quarantine
Date 2026-11-18 TRT. Scope LONG1 NEARUSDT + SHORT1 INJUSDT.
Bot services/timers stopped. Redis infrastructure remains active; all test
Redis writes occur in standalone Unix socket port=0 AOF instance.

## Existing evidence reused
- Stage26 atomic research risk reservations in `research/staging/stage26_joint_atomic_master_dry_v1.py`
- Stage28 `~/binance1/research/staging/stage28_reservation_exact_broker_bridge_v1.py`, bound exact order/fill/native stop and immutable epoch/fencing
- Existing SHORT research `isolated_reconcile_epoch_v2.py`, `unknown_order_recovery_evidence_v1.py`, and worker tests. Stage29 is fitted to literal Stage26 records, not the incompatible older Stage2 reservation schema.

## New research work and validation
- `research/staging/stage29_unknown_submit_recovery_journal_v1.py`: Redis Lua BEGIN atomically closes stage26 gate BEFORE broker read and advances monotonic observation epoch. RECORD accepts only same immutable request/strategy/owner/clientOrderId/reserve_epoch/fence, with whitelisted evidence states and severity. Each distinct event writes audit stream; serious states emit persistent hazard OUTBOX (not a delivered notification). All observed pending reservations are moved into sticky quarantine; no time-based release, commit, resubmit or order permission. Higher severity is sticky across newer good evidence and late conflicting observations. Exact duplicate event_id is idempotent; conflicting event/owner/fence rejected.
- `research/tests/test_stage29_unknown_submit_aof_recovery_v1.py`: actual Stage26 AOF local Redis records for LONG1+SHORT1, real Stage28 evidence binder, injected synthetic exchange API responses. First LONG lost-POST/network error and SHORT order 404 => UNKNOWN_FREEZE, both quarantined. AOF crash/restart preserves both quarantines + risk gate CLOSED + 2 audit and 2 hazard events. Subsequent SHORT historical fill but prior journal UNKNOWN => RECOVERED_FILL_PENDING_JOURNAL; simulated journal correction + stop returns PROTECTED_EVIDENCE_ONLY; missing stop FREEZE_UNPROTECTED; later good evidence cannot erase severity 6. Late old observation becomes an archived hazard; latest epoch remains intact. Wrong owner and fence rejected. 7 immutable events, 5 durable hazard events, 0 replayed orders, 0 releases, 0 commits, 0 real Binance calls, 0 production Redis writes.

## Safety and release status
- The synthetic FILLED journal update in test is NOT an authenticated repair or production authority. Exchange GETs were MOCKED; not real order fills/stops or account-wide atomic snapshot.
- Stage29 audit CLOSE behavior is a useful research fail-safe; no live risk Master service or TradeExecutor is integrated with this module.
- No safe production release/COMMIT workflow is implemented. No independent authoritative exit/flat proof. Actual Binance order lifecycle is UNTESTED.
- Unknown orders are quarantined rather than automatically retried/released. Any future release must bind authenticated exchange order/position/stop/exit evidence, account identity, monotonic fencing, and trusted reconciliation process.
- Both real LIVE OPEN entry paths retain Stage24 veto-only guard and must remain stopped. Keep LONG2-4/SHORT2-4 uncreated.

## Next engineering
Central Risk authority production design review: independent authenticated broker evidence, durable risk mode/DD and existing exposures, complete intent ledger, verified notional, broker account identity, atomic final authority at order writer with post-ACK STOP protection, authenticated reconciliation across account and all symbols. Run end-to-end fault injection against actual executor with fake exchange and then shadow-only supervised validation. Until then NO-GO.
