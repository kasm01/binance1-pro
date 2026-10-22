# Stage 5 Model Readiness Audit — 2026-10-22

## Architecture status
Stage 4 isolation is complete for LONG1/SHORT1: strategy-owned Redis namespaces, logs, PIDs, service identities and shared market-data separation are in place. Production remains disabled (`DRY_RUN=1`, `ARMED=0`, `LIVE_KILL_SWITCH=1`; orch/supervisor inactive).

## Methodology correction
Frozen full-sample model replay was retained only as candidate discovery, not promotion evidence, because replaying a model trained through 2026-09-14 over earlier bars is not causal OOS. Promotion decisions now use train -> validation -> unseen test/forward chronology.

## LONG2 readiness
Frozen-model discovery initially favored DOGE and AVAX, but both failed real forward checks. Architecture-consistent causal walk-forward then showed:
- DOGE: 1/4 positive OOS folds; mean OOS about -4.83%, worst fold about -26.06%.
- AVAX: 3/4 positive fold means but one catastrophic OOS fold about -39.43%; mean OOS about -7.43%.
- LINK: unstable with an OOS fold about -33.68%.
- SOL generic model: 4/4 positive fold means, but latest deployment simulation failed validation promotion: threshold 0.50 had excessive DD (~-18.1%); cleaner thresholds had too few trades.

A LONG economic entry-quality model (60m MFE >= 0.60%, MAE <= 0.75%) improved SOL but still had a regime-break fold around -13.15% / DD -27.44%. Decision: LONG2 = NO_DEPLOY. Required next work is score normalization/regime/promotion stability, not service cloning.

## SHORT2 readiness
V5-style classifier screening showed good entry-quality lift:
- SOL: test AUC ~0.730, hit-rate lift ~2.15x.
- DOGE: test AUC ~0.725, hit-rate lift ~2.13x.
- LINK: lift ~1.79x.
- AVAX: lift ~1.74x.

But lifecycle-consistent causal walk-forward was not stable:
- SOL: 2/4 positive test folds; worst test ~-18.20%, worst DD ~-30.54%.
- DOGE: 1/4 positive test folds; mean test ~-2.75%, worst DD ~-29.00%.

Applying a validation promotion gate leaves SOL with no eligible deployment fold. DOGE has only one historically eligible fold, insufficient for lock.

Final DOGE deployment simulation used train through 2026-08-15, validation 2026-08-15..2026-09-14 and reserved 2026-09-14..2026-10-11 as forward. All validation profiles failed before forward was consulted. Best top-2% profile: return ~-3.25%, PF ~0.896, DD ~-15.74%, 27 closes. Decision: SHORT2 DOGE = NO_DEPLOY.

## Stage 5 decision
Do not clone LONG2-4 / SHORT2-4 yet. Infrastructure is ready, alpha engines are not. Next R&D should target SIGNAL NORMALIZATION + MODEL SCORE GATE + regime-aware promotion, then rerun lifecycle-consistent causal walk-forward and a locked forward test. Only a profile passing validation before forward exposure may become a shadow candidate.

## Cost discipline
No permanent new market-data service was added during candidate research. Forward AVAX/SOL data downloads were one-off public historical calls. Reused cached 1m/3m data wherever available. No production routing was enabled.
