# Stage 27 — Binance signed GET double-pass evidence to central risk research reservation
Date: 2026-11-18 TRT. Bot services and timers remain stopped. No real orders.

## Actual implemented
- `research/staging/stage27_broker_consistency_evidence_v1.py`: strict two-pass,
  8-source-read contract: USD-M v3 account + full positionRisk before and after
  scoped openOrders and openAlgoOrders for NEARUSDT and INJUSDT. It rejects
  missing or inconsistent account fields, nonfinite/malformed quantities, side
  contradictions and duplicate legs, mismatched account vs positionRisk, any
  changed positions or margin metrics between reads, out-of-scope exposure,
  any nonzero position needing mark/stop lifecycle reconciliation, missing,
  mismatched or nonempty open standard/algo order lists, elapsed >5 seconds.
  It also demands zero account-wide initial, open-order initial and position
  initial margin to catch unexplained margin on OTHER symbols.
- Output is `CONSISTENT_READONLY_ONLY` with a local SHA-256 content fingerprint
  or `UNKNOWN` on failure. Output always sets source_authenticated=False,
  independently_verified_account_id=False, live_order_authorized=False.
  Fingerprint is NOT broker signature, atomic snapshot, or risk permit.
- `research/trace/stage27_signed_get_dualpass_readonly.py`: actual Binance
  signed GET-only reader, no state changes; prints only structural counts,
  duration, state, no balance/position sizes, order IDs, secrets or raw payloads.
- `research/tests/test_stage27_broker_dualpass_offline.py`: PASS 23 negative
  scenarios, 8-call positive flat candidate. Specifically second-pass
  account/position drift and outside-scope initial margin are rejected.
- `research/tests/test_stage27_snapshot_to_atomic_research_bridge.py`:
  Stage27 stable local evidence fingerprint -> real DRY CentralRiskMaster
  -> Stage26 local research Lua reservation. Two candidate reservations
  show `order_authorized=False`. Bad broker capture does not bind.
  This bridge exercises only an ISOLATED Redis socket on TCP port=0.

## Real observed read-only check
- LONG1 configured Binance USD-M signed GET, 2026-11-17 22:22:25 UTC:
  double-pass flat and stable, 0 account nonzero positions, 0 standard
  openOrders and 0 openAlgoOrders for scoped symbols, ~1.88s.
  Broker response was obtained by signed authenticated GET requests,
  but the module does NOT independently authenticate an account UID,
  atomic exchange epoch or future fill-free condition. No automatic
  production permit is derived.
- SHORT1 effective API credentials were previously checked equal to LONG1
  in Stage20; this stage did not unnecessarily repeat live SHORT1 reads.

## Known NO-GO limitations
1. Binance USD-M multiple signed GET endpoints are sequential, not an atomic
   snapshot. Two passes reduce missed drift but cannot rule out an entry/fill
   between observations, nor read all external live open intents.
2. No independently attested account identity, native STOP compatibility,
   protective order lifecycle, authenticated CentralRiskMaster decision,
   source verifier identity or exchange server epoch/fence/ack.
3. Stage26 `BIND_TEST` still trusts injected digest and synthetic budget,
   so test-bound RESEARCH reservation is NOT exchange-authorized.
4. Actual LONG1/SHORT1 live entry paths remain on shared VETO-only
   `joint_risk_live_guard_v1`; these guards were not modified in Stage27.
5. NO production Redis writes; NO real Binance POST/DELETE; NO service starts;
   NO config modifications; NO LONG2–4 / SHORT2–4 clones.

## Next acceptance gate
Independent account-wide order/fill/stop reconciliation including in-flight
unknown intents and true account identity, authenticated generation-bound
central risk proof, atomic reservation of both pending and existing margin,
durable fencing across restart, independent Final Safety immediately before
real order and post-ACK protective STOP verification. Until those are proven,
NO-GO for live opening.
