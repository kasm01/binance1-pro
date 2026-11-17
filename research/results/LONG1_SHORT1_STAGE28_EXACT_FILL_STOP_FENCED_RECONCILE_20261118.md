# Stage 28 — LONG1+SHORT1 reservation identity -> exact Binance order/fills/native stop evidence
Date: 2026-11-18 TRT. Bot services and timers kept inactive. All evidence
in tests is MOCK exchange output, NEVER a live Binance filled order.

## Reused prior SHORT1 production-independent evidence code
- `~/binance1/orchestration/risk/bound_exchange_reconcile_v1.py`
  validates exact stored clientOrderId, orderId, terminal fill status, sum
  of unique fills, held position size and owned Binance Futures Algo STOP.
  It never grants commit/release/send authority.
- `~/binance1/orchestration/risk/position_stop_lifecycle_evidence_v1.py`:
  independent immutable reservation/ledger binding, owned clientAlgoId,
  native STOP_MARKET closePosition/MARK_PRICE, flat and exit history checks.
- `~/binance1/orchestration/risk/unknown_order_recovery_evidence_v1.py`:
  order lookup 404/network ambiguity -> UNKNOWN, no resubmission.

## New Stage28 bridge
- `~/binance1/research/staging/stage28_reservation_exact_broker_bridge_v1.py`
  maps actual Stage26 internal immutable reservation fields to existing exact
  broker binder, enforces epoch/fencing + request/owner/clientOrderId +
  strategy-symbol-side + expiry + snapshot fingerprint. Native reserve
  directions `long/short` explicitly map to exchange BUY/SELL.
  On ANY mismatch returns UNKNOWN_FREEZE. All returned decisions include
  can_submit=false, can_resubmit=false, can_commit=false, can_release=false
  and live_order_authorized=false.
- `~/binance1/research/tests/test_stage28_exact_broker_bridge_fault_matrix.py`
  tests 27 scenarios for LONG1 and 27 for SHORT1: 54 PASS. Wrong IDs,
  stale/foreign fence, missing native stop, wrong algo owner, wrong
  working type, partial fills, incomplete history, source timeout, flat
  without trusted exit, old reservation, UNKNOWN journal all fail closed.
  Positive PROTECTED_EVIDENCE_ONLY remains only a read-only observation.
- `~/binance1-pro/research/tests/test_stage28_actual_stage26_reservation_exact_broker_bridge.py`:
  actual Stage26 Lua issues and persists both strategy reservation records
  inside separate TCP-port-0 Unix-socket Redis. Those literal Redis records
  are passed to the SHORT exact broker binder with synthetic signed-GET
  response shapes. Both LONG1 and SHORT1 return PROTECTED_EVIDENCE_ONLY
  when filled + owned native stop match; both return FREEZE_UNPROTECTED
  when stop is missing. The actual pending central reservations remain
  held, with zero commits/releases.
- Existing SHORT tests `test_bound_exchange_reconcile_v1.py` (23),
  `test_position_stop_lifecycle_evidence_v1.py` (13) still PASS.

## Notable fault discovered
- First Stage28 cross-repo test correctly BLOCKED due to mismatch between
  Stage26 reserve direction `long/short` and exchange order `BUY/SELL`.
  Fixed explicit one-way mapping in bridge; no live code was modified.

## NO-GO limitations
1. Broker responses in test are **synthetic**. No real submission/fill or
   protective stop was made; no exchange order and no production Redis write.
2. Stage26 reserve TEST gate accepts injected digest and synthetic budget;
   independent authenticated account-wide evidence, epoch and source-signature
   remain unavailable. This code cannot grant final order authority.
3. The bridge proves local equality of recorded fields and provided broker
   data; caller still must authenticate source, account ID, exchange time,
   all open orders and intent registry, validate fill pagination and
   after-ACK state, and prevent replay across persistent Redis generation.
4. `FLAT_EVIDENCE_ONLY` cannot automatically RELEASE. Full filled/exit
   reconciliation and explicit authorized state transition are necessary.
5. Both LIVE OPEN safety gates remain VETO-only. No service restart,
   env changes, LONG2-4/SHORT2-4 creation, or production integration.

## Next
Stage29: durability and independent recovery workflow covering UNKNOWN POST
response, exchange order lookup 404, late ACK/FILL, native stop missing,
cross-epoch journal quarantine and authenticated release candidate. Confirm
that *no* recovery branch automatically resubmits or frees portfolio risk.
