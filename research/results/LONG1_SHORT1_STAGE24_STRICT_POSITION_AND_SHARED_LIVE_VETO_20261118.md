# Stage 24 — LONG1 strict risk count and two-engine shared live OPEN boundary
Date: 2026-11-18 TRT. VM bot services/timers remained inactive throughout.
Status: LONG1 risk counter defect fixed; common live veto integrated in BOTH bot
open paths, but independent authenticated *live* CentralRiskMaster order
authority is STILL NOT IMPLEMENTED. RELEASE = NO-GO. No order sent.

## 1. LONG1 strict unknown-to-block change — implemented
- `core/strict_position_count_v1.py` validates Binance USD-M v3 full account
  `positionRisk` rows. Invalid/unknown/missing, NaN, duplicate or malformed
  source RAISES instead of returning zero.
- `core/trade_executor.py::_count_open_positions_for_side` live mode uses
  signed `_futures_v3_position_risk()` plus strict `count_side()`; dry
  mode continues using the existing local/shadow count, but no silent final
  zero fallback on exceptions.
- `_evaluate_long_execution_risk_gate` checks the live strict count BEFORE
  any same-side scale-in; on any read failure returns FALSE. Also fails
  closed if the last position-cap computation fails.
- These checks are independent of and *not a substitute* for authenticated
  central multi-symbol portfolio/intent reservation. They are an extra veto.
- Binance full account GET per live candidate adds bounded exchange weight,
  but avoids every collector tick. It can be consolidated later under the
  trusted central snapshot to avoid duplicate paid API calls.

## 2. Shared live entry OPEN gate — integrated as VETO-ONLY
- Identical `core/joint_risk_live_guard_v1.py` in BOTH ~/binance1-pro and
  ~/binance1 (identical SHA256).
- Strict strategy assignments: LONG1/NEARUSDT/long and
  SHORT1/INJUSDT/short. Dry-run-only path can proceed with existing shadow
  behavior; LIVE always rejects with
  `joint_risk_live_authority_not_connected` until an actual authenticated
  atomic risk authority is independently implemented and approved.
- LONG1 `open_position_from_signal` checks existing Native Stop latch first,
  then shared gate; separate `_exchange_open_market` LIVE OPEN helper also
  independently rejects. SHORT1 equivalents also reject in both locations.
- The release gate has **no environment toggle**, no metadata-only bypass,
  and makes NO claim of production CentralRiskMaster authorization.
- Existing SHORT1 `CentralRiskClient` dry-only evaluation remains unchanged.
  Existing LONG1/SHORT1 CLOSE and stop methods were verified unmodified
  against git HEAD using AST comparisons (2 LONG1 + 3 SHORT1 protected methods).
- Risks before opening and safety for reducing existing exposure must be
  separated: new OPEN veto must not block existing CLOSE/stop functions.

## Tests and results
- Actual extracted LONG1 methods in offline AST:
  `research/trace/test_stage24_live_guard_long_strict_v1.py` PASS,
  including failed signed GET, invalid position rows, failed scale-in, true
  empty account, direct entry skip and direct exchange helper exception,
  zero client order calls.
- Actual extracted SHORT1 methods:
  `~/binance1/research/tests/test_stage24_shared_joint_guard_short_v1.py`
  PASS, including direct exchange helper deny and DRY_RUN pass.
- Native-stop regression `research/tests/test_long1_native_stop_entry_guard_v1.py`
  PASS (native guard priority preserved).
- Stage16 PENDING, Stage17 regression, Stage19 fencing, Stage21 shared
  candidate, Stage22 isolated E2E PASS after code update.
- Native stop and short bridge tests passed. No exchange orders, NO Redis
  mutations, NO bot starts, NO config edits.

## Remaining for enabling a real shared Central Risk Master
1. Authenticated, authoritative account-wide signed proof with consistency
   and exchange identity, freshness, open orders/stops/fills, unknown -> BLOCK.
2. One durable central atomic reservation tied to generated intent ID,
   epoch, fencing token, TTL, allowed notional, shared portfolio DD mode,
   and fully reconciled position ownership for BOTH executors.
3. Gate authorization must remain atomically bound to the actual final
   order submitter without replay/TOCTOU. Its authorizer does NOT yet exist,
   so both live engines intentionally stay blocked.
4. Independent Final Safety, exchange fill and protective stop attach, restart
   and rollback tests, then explicit production release approval.
5. `./shadow_start.sh` is NOT safe to run as a live-trading deployment: even
   though LIVE opens are now vetoed, service restart remains unverified,
   potentially activates other managers, and does not constitute a release.

No LONG2–4 or SHORT2–4 engines created. Disk ~6.6GB free.
