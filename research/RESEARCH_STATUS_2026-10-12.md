# Research Status — 2026-10-12

## Scope
Research-only. Production bot remains OFF. No production order/risk/env behavior changed.

## Architecture policy
- LONG research may progress through normal promotion rules.
- SHORT strategy-layer evidence is RESEARCH_ONLY until SHORT refactor is complete.
- SHORT execution/microstructure research may continue because it is mostly strategy-independent.

## Execution data integrity
- execution_l1 schema v2 uses disjoint snapshot-interval trades.
- LONG queue consumption uses aggressive sells at/through the bid limit.
- SHORT queue consumption uses aggressive buys at/through the ask limit.
- Rolling t1 volume is retained only for compatibility, not queue fill authority.
- Queue fill promotion uses conservative lower-bound fills; price-through upper bounds are diagnostic only.
- Visible cancellation/replenishment are measured but not credited as fills.

## Current execution conclusion
- No CANDIDATE or PRODUCTION_ELIGIBLE execution policy exists.
- Maker benefit is decomposed into WAIT_TIMING + MAKER_INCREMENTAL.
- maker_incremental <= 0 is rejected for promotion.
- Queue results require robust size scenarios, positive CI, safe adverse-selection markouts and multiple future validation blocks.

## Adaptive timeout hypothesis
Frozen exploratory policy:
- rv30 <= 6.059917 bps -> wait 2s
- otherwise -> wait 1s
- queue_mult = 1.0, maker fee stress = 2 bps
- discovery validation block = 82951

This policy is NOT production-valid. Thresholds must not be retuned on each new block.
OOS validator: research/scalp/validate_shadow_adaptive_timeout_oos.py
Current validator state: NO_FUTURE_VALIDATION_BLOCKS.

## Live-signal execution comparison
When production is intentionally re-enabled later, verified MARKET fills can be mapped to shadow L1 via:
- shadow:telemetry:execution_compare_anchor
- trade_id / intent_id / order_id / client_order_id
Analyzer compares MARKET vs maker-first and, after outcome, net PnL/ROI using the same real exit price.

## Stop condition for research expansion
Do not add more execution features now unless a concrete data-quality issue is found.
Continue collecting v2 shadow data and validate the frozen policy on future 6h blocks.

## Next engineering priority
Return to bot architecture work, especially SHORT refactor into the target pipeline:
MODEL -> SIGNAL NORMALIZATION -> MARKET CONTEXT -> MODEL SCORE GATE -> SNIPER -> ENTRY CONFIRMATION -> PENDING REVALIDATION -> EXECUTION RISK -> FINAL SAFETY -> ORDER -> POSITION LIFECYCLE -> TELEMETRY/OUTCOME.
