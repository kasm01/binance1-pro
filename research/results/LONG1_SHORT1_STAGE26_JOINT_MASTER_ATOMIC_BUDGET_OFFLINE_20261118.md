# Stage 26 — LONG1 + SHORT1 Master decisions and single atomic research reservation
Date: 2026-11-18 TRT. Bot services and timers remained inactive.

## What was actually implemented
- `research/staging/stage26_joint_atomic_master_dry_v1.py`: combines an actual
  `CentralRiskMaster` DRY profile decision with a new isolated Redis Lua
  research reservation, bound to request ID, strategy, symbol, side,
  owner, client order ID, source snapshot digest, epoch, fencing counter,
  TTL and approved notional. Every response carries
  `order_authorized=false`. All state belongs to a sandbox prefix and
  standalone Redis; this module is **NOT wired to live executor**.
- Lua reservation computes aggregate pending+quarantined notional IN THE
  SAME atomic transaction as issuing the fencing token. Budget is injected
  only as a synthetic local test figure. It does not authorize source,
  equity or CentralRiskMaster decision in production.
- `research/tests/test_stage26_master_atomic_fencing_isolated.py` uses an
  ephemeral local-only Redis socket, TCP port=0, AOF appendfsync=always.
  Actual Master DRY profile (synthetic equity 100, flat positions):
  LONG1 46 and SHORT1 46 USDT notional; each `production_ready=False`.
  Concurrent 60 same-strategy reservation requests -> one winner; two
  different strategies -> two reservations. With tighter injected budget
  80 USDT, 46 LONG1 approved and 46 SHORT1 REJECTED inside Lua.
- Same request idempotency, request-owner conflict, strict fencing token,
  expired final-safety, stale epoch, sticky QUARANTINE for unknown order,
  AOF restart with CLOSED gate and preserved quarantine/pending all PASS.
- Actual LONG1 and SHORT1 LIVE OPEN safety guard remains veto-only, as
  confirmed in Stage24 tests. Native stop/close methods unmodified.

## Important NO-GO limitations
1. Stage26 `BIND_TEST` takes arbitrary caller-supplied digest and budget.
   THERE IS NO independently authenticated Binance account/snapshot/balance
   proof. Treat all READY outputs strictly as offline experimental outcomes.
2. Lua only checks numeric approved notional against request and injected
   budget. It does NOT independently authenticate CentralRiskMaster decision,
   risk mode, or all external account exposures and open orders. This is not
   atomic portfolio authorization against Binance.
3. `VALIDATE` is final-safety CANDIDATE ONLY, it cannot issue an exchange
   order token. No Binance client POST or actual exchange idempotency link,
   fills, native stop attach, live restart recovery or liquidation checks.
4. No live trading services, env, production Redis, systemd or Binance order
   state were modified. No additional LONG2-4 / SHORT2-4 strategy motors.
5. If an order submission is ambiguous, real implementation must persist
   unknown intent and quarantine risk, then independently reconcile fills,
   positions and open orders before a release. Test QUARANTINE models
   this behavior but does not implement real exchange reconciliation.

## Next engineering
Authenticated broker evidence with account-wide positions, algo/open orders,
server time, equity and durable signed account identity, tied to an independent
Central Risk generation. Atomic risk approval should verify authoritative
decision provenance AND all portfolio exposures in the same transaction,
with durable monotonic fencing across recovery. Connect true final pre-order
authority only after full synthetic and shadow-only test evidence, and
separately test native protective stop availability and rollback. Keep LIVE
OPEN on both engines blocked until explicit production go-live review.
