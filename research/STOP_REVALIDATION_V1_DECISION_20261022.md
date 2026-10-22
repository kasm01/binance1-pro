# STOP REVALIDATION V1 — Decision (2026-10-22)

## Scope
Evaluate whether LONG1/SHORT1 soft-stop losses can be reduced by causal stop revalidation rather than blindly widening stops.

## Baseline observations
- LONG1 winners rarely approach the current stop: only ~2.0% of winners reached >=3% adverse excursion; none reached 3.5%.
- SHORT1 winners rarely approach the current soft stop: ~0.7% reached >=4% adverse excursion.
- LONG stop losses hold materially longer than winners; SHORT separation is stronger (stop median ~202m vs winner median ~57m).

## Causal stop-revalidation feature audit
Features at stop use only completed/prior data: position age, completed flow15/flow60, ret5/ret15, prior candle direction, and prior OI snapshot where available.
- LONG1 soft stops: 54 events; recover-before-catastrophic base rate 16.7%. No stable interpretable causal rule found.
- SHORT1 soft stops: 246 events; recover-before-catastrophic base rate 22.4%.
- SHORT age <=120m lifted recovery rate to ~29.7% with similar early/late behavior, but precision remained too low for full rescue.

## SHORT partial rescue test
Policy: age <=120m; close 50% at soft stop, hold 50% for <=120m; exit residual at entry recovery, +6% catastrophic, or timeout.
- Eligible: 74 / 246.
- Outcomes: 41 catastrophic, 22 timeout, 11 recovery.
- Mean stop result worsened from ~-4.082% to ~-4.175%.
- Incremental result ~-99 USDT on baseline notionals.
Decision: REJECT.

## LONG partial rescue post-hoc
Policy: close 50% at soft stop; hold 50% <=120m; entry recovery / -3.5% catastrophic / timeout.
- Six-seed post-hoc delta positive in all seeds, mean +0.098 pp per soft-stop event.
- This test ignores engine-slot opportunity cost and therefore is discovery only.

## LONG full lifecycle replay
120m rescue, full lifecycle / single-slot behavior:
- Seed1 +35.51%, DD -25.28%
- Seed2 +32.14%, DD -22.22%
- Seed3 +40.60%, DD -20.23%
- Seed4 +24.88%, DD -25.54%
- Seed5 +47.18%, DD -18.26%
- Seed6 +26.44%, DD -22.53%
Relative to locked LONG1 baseline, 3 seeds improved return and 3 worsened; maximum drawdown worsened in all six seeds.

60m cost-controlled screen:
- Seed1 +34.81%, DD -25.20% (return improves, DD worsens).
- Seed3 +42.26%, DD -19.61% (return worsens, DD worsens).
Decision: REJECT.

## Final decision
- Keep current LONG1 and SHORT1 stop distances and catastrophic boundaries unchanged.
- Do not deploy STOP_PENDING / partial-rescue logic.
- Do not blindly widen stops.
- Continue with the locked Central Risk operational headroom and current stop confirmation logic.
- Next diagnostic priority: inspect the worst loss days / stop clusters, but treat stop settings as locked unless new causal evidence emerges.
