# LONG1 Stage7 — CANDIDATE → TOP5 → TRADE INTENT
Date: 2026-11-18 Europe/Istanbul. Bot services OFF, production Redis READ ONLY.

## Actual production code changes
Stage6 HeavyEngine SignalEvent stores event_id, model_evaluation_id and
wallclock bucket model_close_id. Aggregator preserves exact parent signal
transport and candidate_id.
TopSelector's actual selection preserves candidate_id, source candidate
Redis stream _source_stream_id and model parent fields.
MasterExecutor _make_intent already retains selected candidate in raw and
creates a separate immutable intent_id. Before Stage7, published intent item
did not carry source candidate ancestry at TOP-LEVEL.
New orchestration/trace/long1_candidate_intent_lineage_v1.py pure helper
extracts source_candidate_id / source_candidate_stream /
source_candidate_stream_id ONLY from explicit source fields. It preserves
previous Stage6 parent_signal_event_id and model_evaluation_id ONLY if
complete, well-shaped and recalculated transport parent hash matches.
Changed orchestration/executor/master_executor.py::_publish_intents to add
those tiny metadata fields. No strategy/scoring/PENDING/risk/order change,
no new stream/service/collector/API calls.

## Tests
- test_long1_candidate_intent_lineage_stage7_v1.py: actual AST-extracted
  TopSelector normalizer and MasterExecutor publisher, PASS. Legacy
  input with no model parent does not invent one.
- test_long1_stage7_stream_chain_isolated_v1.py: actual Redis port=0
  4 streams signals/candidates/top5/intents; all literal (stream name, ID)
  pairs verified, PASS. Redis IDs can coincide across different streams.
- test_long1_candidate_intent_lineage_verifier_v1.py: one fully exact,
  one legacy candidate-only, 13 intentional UNLINKED negative cases, PASS.
- Stage6 source/payload, Stage5 strict contract, Stage24 fail-closed
  central Risk Master and Native Stop regression suite PASS.

## 12–14 November legacy Redis historical discovery
Read-only audit: research/trace/audit_long1_legacy_candidate_intent_exact_readonly_v1.py
Sampled 894 candidate, 866 top5, 285 trade intent and 285 exec intent
batches (bounded current retention, not complete historical coverage).
Legacy TradeIntent.raw retained candidate_id and originating candidate
stream ID, and TOP5/EXECUTION INTENT batches have literal parent stream IDs.
Therefore 285/285 NEARUSDT historical intent items are EXACTLY bound to
candidate source -> TOP5 -> trade intent -> EXECUTION INTENT by raw IDs.
12–14 Nov: 83/83 exact (12 Nov 27, 13 Nov 28, 14 Nov 28).
These are INTENTS, NOT exchange order fills or actual position count.
The 89 historical MODEL LONG events are a different stage/population.
Legacy model_evaluation_id count = 0, so exact MODEL -> SIGNAL ancestry
cannot be reconstructed for that old window (UNLINKED).

## Limits
Production services not restarted, new upstream metadata has zero current
production coverage. Independent Binance actual ORDER/POSITION verification
not performed. Existing Stage24 shared live risk veto remains on,
LONG2–4/SHORT2–4 not created. Historical user windows are research
labels only, not real trading restrictions.

Next Stage8: preserve source candidate and trace ID in IntentBridge
execution intent and PENDING/outcome telemetry without changing decisions;
independently verify Binance fills before claiming actual order lineage.
