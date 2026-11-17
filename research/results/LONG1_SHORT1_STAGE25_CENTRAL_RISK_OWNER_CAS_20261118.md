# Stage 25 — Central DRY Risk shared owner identity + CAS hardening
Date: 2026-11-18 (Türkiye). Both trading stacks remain stopped.

## Why
Existing LONG1 central DRY service accepted `RELEASE` with only strategy ID,
including LIVE-mode requests. Its `HDEL` was unowned and permitted old/foreign
requests to remove a newer reservation. An existing isolated adversarial
test reproduced this. This is NOT acceptable to reuse for live risk.

## Applied to actual code
- `~/binance1-pro/scripts/central_risk_enforce_dry_service.py`:
  DRY-only RELEASE now demands strategy identity and original reservation
  request ID. A Redis Lua script performs compare-and-delete atomically;
  mismatch, missing/corrupt state, stale owner, or live release => REJECT.
- `~/binance1/orchestration/risk/central_risk_client.py`:
  SHORT1 DRY client tracks original request ID only after successful
  reserved response; RELEASE sends the matching ID, clears it only after
  successful CAS, and fails closed without owner (including process restart).
  A lost owner can lead to temporarily retained DRY reservations pending
  expiry/reconciliation; this is preferable to unsafe release.
- Older audit test converted into a regression test; no production Redis
  or exchange state changes, no services started.

## Executed tests
- Actual central service `_handle` vs isolated Redis socket with real Lua:
  unauthorized LIVE release, missing owner, wrong owner, old owner after a
  later reservation, wrong strategy all rejected. Correct owner releases.
- Actual SHORT1 CentralRiskClient pure mock test:
  release identity transmitted, lost/restarted owner rejected, failed
  release retains owner for retry, reserve=False does not grant an owner.
- Real central handler + actual SHORT1 client request/response via isolated
  Unix-socket Redis: LONG1 and SHORT1 DRY research requests both
  reserved at synthetic equity=100, 46 + 46 notional; only correct owner
  could release. Both decision.production_ready=False; NO live authority.
  The LONG1 request in this test used the common SHORT1 client interface;
  it did NOT execute the actual LONG1 TradeExecutor order path.
- No external APIs, no production Redis mutation, no orders, no bots started.

## Unresolved blocking issues (NO-GO)
1. The central service is **DRY RUN ONLY** and `CentralRiskClient`
   publishes to central:risk:requests:v1 with request_mode=DRY_RUN.
   Research reservation amounts / DRY status NEVER authorize live orders.
2. LONG1 and SHORT1 live OPEN helpers still use the shared VETO-only
   `joint_risk_live_guard_v1` which intentionally rejects all LIVE opens;
   no authenticated broker order/reconciliation proof bound to execution.
3. Other central DRY paths are NOT transactionally atomic: reserve sizing and
   `HSET` are separate operations. Existing expiry cleanup may remove a
   reservation without verified exchange flat. These behaviors must NOT be
   copied into a live authority. A proper live coordinator needs atomic
   issuance, durable epoch/fence and independent exchange reconciliation.
4. Native stop/lifecycle exchange proof and crash recovery remain untested in
   joined real order path. LONG2–4/SHORT2–4 are not to be created.
5. This fix is DRY-only owner release hardening, not an assertion that
   common live Risk Master integration is finished.
