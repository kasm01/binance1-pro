# LONG1 + SHORT1 Marked Exposure / Daily Risk Decision — 2026-10-22

## Scope
Research/shadow only. Production remains unauthorized. Re-audit focused on daily return/loss behavior, mark-to-market exposure correctness, and Central Risk headroom.

## Correctness fix
Previous portfolio replay kept open-position exposure notional fixed at entry while equity moved with MTM. Futures exposure must be marked as qty x current mark. V4 replay now rebuilds PositionExposure notionals every minute from mark price and CentralRiskMaster exposes continuous exposure health: OK / WARNING / BREACH.

## Marked baseline (Central DD12/R06 + SHORT V50, six seeds)
- Mean return +197.6531%; min +180.1898%; max +211.6893%.
- PF 1.2695.
- Mean MTM DD -11.5593%; worst -11.9143%.
- Gross max 1.03269x; abs-net max 0.53910x.
- Mean exposure BREACH 60,529.7 minutes; WARNING 42,150.2 minutes.
- Alpha result is essentially unchanged versus prior replay; risk telemetry is more accurate.

## Operational headroom screen
A 4% central sizing buffer (0.96 multiplier; equivalent to 0.48 engine budget when raw request is 0.50 equity) was selected over 0.49 after seed1 screening because it materially reduced tail-day classes and marked exposure drift.

Six-seed H048 result:
- Mean return +185.5956%; min +169.5386%; max +198.5216%.
- PF 1.2690.
- Mean MTM DD -11.1012%; worst -11.4570%.
- Gross max 0.99445x; abs-net max 0.51672x.
- Mean BREACH 3,412.2 minutes: ~94.4% lower than marked baseline.
- No cap-limited/rejected opens in the H048 replay because requested sizing already carried the headroom.

## Daily distribution after H048
361 days: 198 positive, 110 negative, 53 flat. Sign counts are unchanged; loss magnitudes improve.
- Mean daily return +0.30155%; median +0.10316%.
- Average negative day -1.06381% vs marked H050 -1.10881%.
- Worst day -6.04673% vs marked H050 -6.29121%.
- <= -1%: 43 vs 44 days.
- <= -2%: 16 vs 17 days.
- <= -3%: 6 vs 7 days.
- <= -5%: 1 vs 3 days.
- All 110 negative days improved versus H050; zero negative days worsened.

## Negative-day attribution
84/110 negative days are SHORT1-dominant; 26/110 LONG1-dominant. Only 10 days have both LONG1 and SHORT1 realized contribution negative.
Main negative-day loss source is SHORT1 soft_stop_1m_confirm; this is partially offset by profitable SHORT1 tp_giveback exits. Historical hard-gating SHORT1 is not justified because SHORT1 remains the dominant annual alpha source and V50 sizing already improved weak regimes.

## Monthly check
13 monthly rows: 12 positive, 1 negative. Arithmetic mean monthly return +8.7091%, median +6.6204%. December 2025 remains slightly negative (-0.3266%); January 2026 +0.7093%. May +6.6204%, September +12.1653%.

## Architecture decision
Keep LONG1/SHORT1 alpha thresholds locked. Adopt CentralRiskConfig.operational_headroom_multiplier=0.96 in the shadow research profile and continuous marked-exposure health telemetry. This is a central risk/sizing correction, not a new alpha filter. Keep production_authorized=False and order routing off.
