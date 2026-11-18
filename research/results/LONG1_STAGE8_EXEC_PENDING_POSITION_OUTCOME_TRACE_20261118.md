# LONG1 trace Stage8 — EXECUTION INTENT → PENDING → POSITION → OUTCOME SHADOW
Date: 2026-11-18 (Europe/Istanbul).
Scope: LONG1 NEARUSDT; SHORT1 and six future strategy bots untouched.
No production service restart; live OPEN gate remains fail-closed NO-GO.

## Implementation (real source paths, metadata-only)
- Added `orchestration/trace/long1_execution_lineage_v1.py`:
  pure compact explicit-source identity carrier; preserves candidate / signal /
  model provenance as advisory metadata, never invents missing IDs from score
  or time. Each new PENDING attempt gets unique pending_attempt_id and
  origin intent ID. New rechecks increment pending_recheck_count, carry
  pending_recheck_intent_id distinct from immutable pending_origin_intent_id.
- Updated actual `orchestration/executor/intent_bridge.py::_publish_exec`:
  top-level trace fields survive BRIDGE_PASS_RAW=0 and retain the existing
  intent_id and source_intents_id. Does not change side, score, price,
  deduplication, selection, risk state or order permission.
- Existing `main.py:consume_exec_events_stream` passes execution item as
  `execute_decision(extra=decision_extra)` and appends fresh 1m entry
  market context. No change required here.
- Updated actual `core/trade_executor.py` PENDING store and recheck merge:
  originating metadata is kept separately from the newest intent and
  market-context revalidation input. Avoid false attribution where an old
  PENDING setup is opened only after a newer intent.
- Actual position commit path now optionally stores compact source trace
  metadata and PENDING origin/recheck identifiers in the position dictionary.
  No changes to fill verification, stop, execution order or position sizing.
- `monitoring/okx_oi_shadow_context.py:mark_position_open_shadow` accepts
  optional compact trace_lineage; existing outcome shadow inherits this from
  current active position context, including pending_attempt_id. The shadow
  outcome retains estimated taker/slippage fee fields; funding remains
  unavailable. These are not actual independently attested Binance fills,
  exchange costs or final P&L.

## Validated
- `research/trace/test_long1_stage8_exec_pending_outcome_isolated.py`
  invoked actual IntentBridge method, AST-extracted actual TradeExecutor
  pending-store method, and real shadow open and outcome producers against
  temporary Redis on Unix socket TCP port 0. All PASS.
- Example: intent-first opens PENDING attempt; two new intent IDs recheck.
  pending_attempt_id stays stable, pending_origin_intent_id remains intent-first,
  current/recheck ID becomes intent-third. Model/candidate lineage of original
  intent remains in pending_origin_lineage. Synthetic position-open shadow and
  outcome shadow contain both origins and current intent IDs.
- Stage7 4-stream source trace, actual publisher and strict validator,
  Stage6 model-source lineage, Stage5 13 assertions, Stage24 live deny guard
  and Native Stop regression all PASS.
- No production Redis writes, no Binance order or position queries, no service
  starts. No changes to stop/close execution methods.

## Historical limitation
- 12–14 Nov 2026 current Redis retention: 83/83 CANDIDATE→TOP5→TRADE INTENT
  →EXECUTION INTENT joins are exact through old IDs. Historical
  MODEL→SIGNAL was not recorded with unique evaluation ID, hence cannot be
  established retrospectively. Stage8 cannot repair that missing history.
- Today's new fields have not yet appeared in production streams because bot
  services are inactive; this stage is source+isolated-validation only.
- Position shadows can be missing after restart/TTL, and scale-in/reconcile
  needs separate identity ownership checks before relying on outcomes.

## Remaining for trusted full chain
- Real running shadow-only data acquisition with all live trading gates
  closed, verifying actual published source fields and PENDING attempt IDs.
- Independent Binance clientOrderId/orderId/fills/open position + native STOP
  lifecycle and identity reconciliation before claiming actual ORDER /
  POSITION / outcome linkage.
- Atomic Central Risk Master authorizer and release safety must pass
  separate NO-GO blockers before live trading. No LONG2–4/SHORT2–4 cloning.
