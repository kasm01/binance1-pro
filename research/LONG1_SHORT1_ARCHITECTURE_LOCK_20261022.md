# LONG1 + SHORT1 Architecture Research Lock — 2026-10-22

## Status
RESEARCH LOCK / SHADOW ONLY. This is not production authorization.

## Shared architecture
MODEL → SIGNAL NORMALIZATION → MARKET CONTEXT → MODEL SCORE GATE → SNIPER → ENTRY CONFIRMATION → PENDING REVALIDATION → EXECUTION RISK → CENTRAL RISK MASTER → FINAL SAFETY → ORDER → POSITION LIFECYCLE → TELEMETRY/OUTCOME FEEDBACK.

One strategy engine = one coin + one direction + one model + max one open exchange position. No averaging-down, no L2/L3 scale-in. Parallelism comes from LONG1..4 and SHORT1..4, not layers on one strategy slot.

## LONG1 locked research shape
- NEARUSDT LONG.
- Single position; `LONG_SCALE_IN_ENABLE=0`, `LONG_MAX_ENTRY_LAYERS=1`.
- Dynamic model gate base 0.525, recovery floor 0.5114, ATR-rank >=0.60, reversal structure close_loc>=0.25 OR lower_wick_frac>=0.25.
- New-LONG exhaustion research rule: completed flow60 >= +0.20; no mandatory positive flow15 hard confirmation.
- Lifecycle research alignment: TP arm +4% ROI, giveback 0.24%, stop confirm 30s, catastrophic -3.50% price.
- Corrected causal single-position + flow20 reference: mean return +32.69%, PF 1.2055, mean DD -20.63%, worst DD -23.96% across six seeds.
- LONG money-flow/context/hazard remains shadow/telemetry before routing promotion.

## SHORT1 locked research shape
- INJUSDT SHORT, single position.
- V49B state-machine research base remains a historical single-engine reference, not future portfolio DD authority.
- Money-flow exhaustion: flow60 <= -0.20 blocks NEW SHORT only.
- Existing causal OI confirmed-build context multiplier x0.50.
- V50 context-risk candidate: if at least two of {flow60>0, completed flow15>0, prior OI15>0}, multiply entry notional by x0.50. This is sizing only, never hard veto.
- Standalone V50 dynamic result: +254.37%, PF 1.2679, max DD -15.49%; May -3.65%, July -1.76%, September +1.69%; 2 negative months.
- No May-specific NOT_APPLICABLE/micro hard gate; full-year expectancy does not justify it.
- V50 is now enabled only in the non-routing SHORT lifecycle shadow for forward evidence.

## Central Risk Master research lock
- Portfolio DD authority belongs centrally; strategy engines must not independently own global portfolio DD once central execution is integrated.
- MTM research candidate: REDUCED trigger 12%, RECOVERY threshold 6%, NORMAL 1.00, RECOVERY 0.70, REDUCED 0.50, two recovery successes.
- Research caps for current LONG1+SHORT1 stage: gross 1.00x, long 0.50x, short 0.50x, abs-net 0.50x, symbol 0.50x.
- Central core now supports minute/tick MTM state updates and separate close-time recovery-success accounting.
- `production_authorized=False` is mandatory for all current shadow/research profiles; numeric caps alone cannot mark a profile production-ready.

## Shared MTM integration result
Central 12/6 + SHORT V50, with local SHORT DD governor removed from sizing authority:
- six-seed mean return +197.64%
- minimum seed +180.15%, maximum +211.69%
- PF 1.2694
- mean MTM DD -11.54%, worst -11.91%
- realized DD mean -10.93%
- zero rejected opens
- Central 12% DD state never triggered in any seed; it remained a portfolio safety net.
- 13 monthly rows: 12 positive, 1 negative.
- April +3.73%, May +6.84%, July +1.75%, September +12.66% average.

## Freeze rule
Do not add new score/flow/OI/micro thresholds to LONG1 or SHORT1 solely to improve historical backtest months. Changes after this lock require one of: bug/correctness fix, forward shadow evidence, cost/safety issue, or a new engine/coin requiring a separately validated profile.

## Required next stage before cloning
Complete Redis / log / PID / service / state isolation audit. LONG2/SHORT2 must not be cloned until every strategy-owned key, stream, state file, PID/service identity, log destination and recovery state is namespaced by strategy ID and central/shared resources are explicitly separated.