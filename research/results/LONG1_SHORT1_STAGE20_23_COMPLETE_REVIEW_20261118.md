# LONG1 + SHORT1 | Aşamalar 20–23 — Birleşik teknik değerlendirme
VM audit: 2026-11-17 21:33–21:45 UTC (2026-11-18 00:33–00:45 TRT)
Scope: NEARUSDT LONG1 + INJUSDT SHORT1. No LONG2–4 / SHORT2–4 created.
All bot services and timers are stopped; Redis infrastructure stays active.

## AŞAMA 20 — Signed broker data, read-only (COMPLETED for observed snapshot)
- Signed Binance USD-M GET of account (fapi/v3/account), full account positionRisk,
  standard openOrders for NEARUSDT/INJUSDT and openAlgoOrders for both symbols.
- LONG1 effective API credential: 0 open account positions, zero standard and algo
  orders in both symbols at read time. Duration ~1.5s.
- SHORT1 effective API credential: identical observed flat account/selected-order
  state, ~1.4s. This is only a dated observation, not durable exchange-flat proof.
- IMPORTANT correction: SHORT1 reads credentials from .runtime_secrets.env,
  not necessarily .env. LONG1 and SHORT1 effective API KEY **AND SECRET MATCH**.
  Earlier .env-only comparison erroneously suggested different keys. No secret
  material or balance amount was printed or stored. Same credentials strongly
  imply same broker API account; this is not independent account UID attestation
  nor evidence that a multi-call snapshot is atomic.
- No POST/PUT/DELETE calls, no Redis writes. No live trading authorization derived.

## AŞAMA 21 — Cross-bot risk authority proposal (RESEARCH COMPLETE; LIVE INTEGRATION BLOCKED)
- Existing CentralRiskMaster, central dry-run portfolio profile, actual LONG/SHORT
  code paths inspected. LONG1 count method swallows unreadable position exceptions
  into zero. In isolated Stage17 fault injection, actual risk gate approved an entry
  on an untrusted zero count.
- SHORT1 has Execution Risk and Final Safety stages. Its visible order path does
  not prove mandatory shared CentralRiskMaster reservation; its own count uses
  local positions, not a verified combined authoritative account view.
- New `research/staging/stage21_joint_risk_authority_v1.py` evaluates shared account
  identity, portfolio source completeness, authenticated/fresh/epoch-bound
  snapshot, open intent unknowns, production authorization, strategy/symbol/side
  binding, allowed notional and available margin. Its approval is explicitly
  ONLY `READY_CANDIDATE_ONLY` and live_order_authorized=False.
- 17 offline cases passed: one simulated positive candidate, 16 fail-closed rejects.
  `source_authenticated=True` is a MOCK fixture, not Binance verification.
- No production code patch or service integration made. Central dry-risk profile
  production_authorized=False. LIVE gate remains NO-GO.

## AŞAMA 22 — Joint E2E failure injection (ISOLATED TEST COMPLETED; LIVE E2E NOT DONE)
- `research/trace/test_stage22_end_to_end_dry_isolated_v1.py`: combines staged
  epoch/fencing Lua protocol in isolated AOF Redis (Unix socket port=0) with
  central risk candidate and a synthetic Final Safety + fake order sink.
- Duplicate same-strategy reservation blocked; same account, exact epoch/fence,
  freshness, final gate tested. Wrong account, untrusted source, unknown intents,
  unauthorized central profile, wrong token, expired TTL, final-second epoch
  switch all BLOCKED. AOF restart retains pending reservation and keeps CLOSED.
- Fake order sink received ZERO calls. Real Binance orders=0, live Redis writes=0.
- Critically, synthetic Final Safety is NOT actual TradeExecutor order
  revalidation, and exchange fill/stop/OCO/native stop lifecycle NOT proven.

## AŞAMA 23 — Controlled rollout *decision*, NOT live deployment (NO-GO)
- `research/trace/stage23_joint_release_readonly_v1.py` produces a machine-readable
  audited release gate `LONG1_SHORT1_STAGE23_RELEASE_GATE_20261118.json`.
- Blockers:
  1. Authenticated broker-account ID and authoritative atomic/complete position
     + orders snapshot bound to the same central generation.
  2. LIVE LONG1 and SHORT1 synchronous Central Risk Master checks before each open.
  3. Resolve LONG1 error->zero count (never treat unavailable as empty).
  4. Replace fixed research test verification marker with independently witnessed
     broker evidence, fencing and persistent risk mode journal.
  5. True independent final safety, order commit/fill/stop rollback end-to-end tests.
  6. Live production risk profile explicitly and safely authorized only after checks.
  7. LONG1 current .env DRY_RUN=0 means `./shadow_start.sh` is potentially LIVE.
  8. Native-stop service intentionally inactive while stack stopped, must be
     activated/healthy before any future live entry.
- No systemd restart, no live trading, no changes to .env, order pipeline,
  Redis state or broker positions.
- A release gate returning NO_GO is an intentional SAFETY RESULT, not successful
  production rollout. No claims that A21 LIVE integration, A22 live e2e or
  A23 live deployment were completed.

## Evidence files
- `research/trace/stage20_live_account_snapshot_readonly_v1.py`
- `research/staging/stage21_joint_risk_authority_v1.py`
- `research/trace/test_stage21_joint_risk_authority_v1.py`
- `research/trace/test_stage22_end_to_end_dry_isolated_v1.py`
- `research/trace/stage23_joint_release_readonly_v1.py`
- `research/results/LONG1_SHORT1_STAGE23_RELEASE_GATE_20261118.json`

## Recommended engineering before acceptance
- Explicitly wire an authenticated shared snapshot provider, atomic lease/epoch
  authority and fail-closed runtime risk gate into BOTH executors; maintain
  isolation and per-bot order state, but share one account-risk authority.
- Prove unknown/timeout/partial GET/slow fills/system crash/restart/stop order
  protection and CentralRiskMaster authority with REAL runtime shadow/no-orders.
- Require release status GO and verified native-stop availability BEFORE running
  shadow_start.sh against live LONG1 env; do not deploy research-only Lua markers.
