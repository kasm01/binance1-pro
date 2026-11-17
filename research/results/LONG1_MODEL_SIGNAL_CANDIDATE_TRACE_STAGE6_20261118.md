# LONG1 trace lineage Stage 6 — MODEL -> SIGNAL -> CANDIDATE
Date 2026-11-18 TRT. Binance bot services/timers stayed OFF. No live order,
no config changes, no production Redis writes, no extra collector service.

## What was found
- HeavyEngine `main.py` previously emitted SignalEvent `event_id` UUID
  but not model close ID or unique per-model-evaluation ID.
- Existing `[MODEL-SCORE]` close_id was derived from
  `int(time.time() // 180)`: a 180-second wallclock bucket, **NOT**
  authenticated 3-minute Binance closed-candle identity.
- Aggregator received actual Redis signal stream ID and `event_id`,
  but candidate top-level payload retained neither. With
  `CANDIDATE_INCLUDE_RAW=0` the raw signal was omitted, losing lineage.
- Exact intent->exec joins and outcome joins from Stage5 were previously
  verified on retained Redis; do not change those paths in this stage.

## Actual production code changed (all additive metadata)
- `orchestration/trace/long1_lineage_v1.py`: small pure provenance helper.
  Model evaluation UUID (unique per `run_once`), small field validation,
  and signal source transport SHA parent; no DB or order side effects.
- `main.py`: creates a single model_evaluation_id per run_once and one
  model_close_id wallclock bucket. Passes identical values to shadow,
  production and direct model Signal payload builders (each stream still has
  its own signal event_id); adds evaluation ID to existing once-per-bucket
  MODEL-SCORE log line. Labels wallclock bucket explicitly:
  `model_close_id_kind=wallclock_bucket_180s`.
- `orchestration/aggregator/aggregator.py`: ONLY NEARUSDT candidate adds
  `source_signal_stream`, `source_signal_stream_id`,
  `parent_trace_id`, `parent_signal_event_id`, plus model_evaluation_id
  and model_close_id+kind only from explicit HeavyEngine signal metadata.
  Works when RAW=0; NEVER infers parent from close bucket, time, score or
  dedup key. No score, cooldown, market context, entry or order decision change.
- `research/trace/long1_model_candidate_lineage_verifier_v2.py`:
  explicit two-record verifier `EXACT_SOURCE_AND_EVALUATION` only when
  actual observed source stream ID, signal event ID, evaluation ID and
  wallclock bucket agree; else UNLINKED. Always advisory_only and
  can_open=False.
- Did NOT invent the downstream candidate->intent link; source candidate
  correlation still needs separate Stage7 inspection/integration.

## Tests
- `test_long1_model_signal_candidate_lineage_stage6.py`:
  Actual AST-extracted HeavyEngine and Aggregator payload builders PASS,
  raw disabled, shadow/production siblings have distinct signal IDs but
  shared evaluation ID, strategy scores untouched, legacy source not guessed.
- `test_long1_signal_candidate_stream_stage6_isolated.py`:
  Actual HeavyEngine producer, Redis XADD signal+candidate, SignalEvent.normalize
  and Aggregator candidate methods, separate local socket port 0. PASS
  exact parent signal transport ID, source event ID, evaluation ID and
  wallclock bucket metadata; no production Redis writes.
- `test_long1_model_candidate_lineage_verifier_v2.py`:
  1 exact synthetic positive, 13 intentional UNLINKED negative; no
  heuristic positive claims.
- `test_long1_trace_contract_v1.py`:
  historical Stage5 13 strict validations still PASS.
- `audit_long1_stage6_predeployment_readonly.py`:
  actual production Redis read-only 2,473 signal and 894 candidate rows
  in current retention. As expected, 0 candidates with new parent or
  model evaluation fields while both bot services remain stopped. This is
  a pre-deployment baseline, NOT evidence of a running new pipeline.
- All live OPEN gates stay on fail-closed shared Risk Master VETO,
  production order and position source unmodified.

## Known limitations and next step
1. Existing model_close_id is explicitly wallclock-derived. If exact
   exchange closed candle is required, add a separately verified
   Binance kline open/close timestamp identity and do NOT substitute bucket.
2. Observed Redis source transport + upstream payload equality is strict
   provenance, not independent producer authenticity or exchange order fill.
3. Stage6 code has NOT been exercised by an actual running live bot:
   no service restarted. Controlled dry replay with all orders blocked and
   no new auto-enabled services is required before claiming production
   coverage.
4. Candidate -> TopSelector -> trade_intents_stream_long1 still needs
   explicit immutable `source_candidate_id/source_candidate_stream_id`
   and continuation into existing intent_id, without guessing.
5. Use only additional compact fields; do not add continuous price-tick
   telemetry, new recurring Redis writes or expensive full raw payloads.
6. LONG1+SHORT1 live joint risk authority remains NO-GO. Do not restart
   trading or fan out LONG2-4/SHORT2-4.
