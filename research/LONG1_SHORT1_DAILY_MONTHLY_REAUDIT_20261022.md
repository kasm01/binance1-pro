# LONG1 + SHORT1 Daily / Monthly Re-audit — 2026-10-22

## Scope
Re-ran the locked shared portfolio scenario `MTM_DD12_R06_SHORTV50` using the current deterministic simulator and then decomposed daily/monthly outcomes by seed and strategy. Production remained disabled throughout.

## Reproducibility
Before/after SHA-256 hashes were identical for `summary_aggregate.csv`, `MTM_DD12_R06_SHORTV50_daily_aggregate.csv`, and `MTM_DD12_R06_SHORTV50_monthly_aggregate.csv`. The six-seed rerun exactly reproduced the prior result.

## Locked shared result
- mean return +197.6445%
- seed range +180.1522% to +211.6943%
- PF 1.2694
- mean MTM DD -11.5449%; worst -11.9131%
- realized DD mean -10.9287%
- mean cap-limited opens 74.5; rejected opens 0
- Central DD12/R06 state changes 0 in all six seeds
- gross/equity max 1.0200x and abs-net/equity max 0.5198x due adverse MTM denominator drift

## Daily distribution
361 effective days: 198 positive, 110 negative, 53 flat. Positive-day rate 54.85%. Mean daily return +0.3139%, median +0.1077%. 5th percentile -1.6940%, 1st percentile -3.7346%. Worst day -6.2939%, best +6.2383%. 44 days <=-1%, 17 <=-2%, 7 <=-3%, 3 <=-5%. Six days had intraday DD <=-5%; none reached -8% intraday DD.

Worst days include 2026-05-29 -6.2939%, 2025-11-10 -5.1206%, 2026-05-23 -5.0923%, 2026-02-06 -4.0410%, 2026-05-18 -3.5302%, 2025-11-08 -3.5281%, and 2025-11-07 -3.1057%.

All seeds share a maximum four-day losing streak on 2025-12-06 through 2025-12-09; compounded loss is about -2.42% to -2.53% depending on seed.

## Drawdown clusters
The global worst DD occurs in two regimes:
- seeds 1/3/4/6: peak 2026-05-22 19:45 UTC -> trough 2026-05-25 18:07 UTC, DD about -10.84% to -11.91%; recovery about 8.0-8.65 days after trough.
- seeds 2/5: peak 2025-11-06 16:44 UTC -> trough 2025-11-10 23:16 UTC, DD about -11.67%; recovery about 8.8 days after trough.

May 22-29 mean realized attribution per seed: LONG1 -41.31 USDT, SHORT1 -25.15 USDT. November 6-10: LONG1 +0.48 USDT, SHORT1 -94.96 USDT. December 6-9: LONG1 +1.68 USDT, SHORT1 -41.95 USDT.

## Monthly distribution
13 monthly rows, including partial October endpoints: 12 positive and 1 negative. Mean monthly return +9.0818%, median +6.8390%. Eleven months are positive in all six seeds. December 2025 is the sole negative mean month at -0.3562%; January 2026 is +0.7184% mean but splits 3 positive / 3 negative seeds.

Monthly mean returns: Oct-2025 +19.1966%; Nov +10.6319%; Dec -0.3562%; Jan-2026 +0.7184%; Feb +7.1462%; Mar +5.9247%; Apr +3.7258%; May +6.8390%; Jun +32.8790%; Jul +1.7477%; Aug +13.4568%; Sep +12.6550%; Oct-2026 partial +3.4978%.

Strategy realized monthly attribution highlights: Dec LONG1 -79.52 vs SHORT1 +74.80 USDT/seed; Jan LONG1 -108.64 vs SHORT1 +117.67; May LONG1 +103.61 vs SHORT1 +3.26; July LONG1 +77.36 vs SHORT1 -38.74; September LONG1 +234.84 vs SHORT1 +99.03.

## V50 effect versus base SHORT
V50 materially improves the important weak regimes: Nov +7.52pp return and +2.72pp DD improvement; Dec +1.54pp and +2.32pp; Jan +2.26pp and +1.97pp; May +5.70pp; September +14.77pp and +4.53pp DD improvement. It costs return in Oct-2025 (-7.03pp), Feb (-1.87pp), Mar (-0.72pp), Apr (-0.73pp), July (-1.43pp), and slightly Aug (-0.10pp), but the annual portfolio improvement is large.

## Strategy-level annual attribution
Mean realized PnL/seed: LONG1 +558.50 USDT, PF 1.2619, ~429 closes, 81.20% winning closes. SHORT1 +1,431.04 USDT, PF 1.2727, 1,078 closes, 77.55% winning closes. On 110 negative portfolio days, SHORT1 is the more-negative realized contributor on 70 days, LONG1 on 26 days; both are negative on only 10 days. This supports context sizing rather than a new global SHORT hard veto.

## Central Risk DD11 experiment
A focused DD11/R5.5 V50 test was stopped after seed1 because it was already dominated: return fell from +191.5239% to +156.7161% while worst MTM DD remained exactly -11.6608%. It caused 14 state changes and 26,192 REDUCED minutes. Lowering the minute-close threshold does not solve instantaneous drawdown crossing and materially suppresses recovery/alpha.

## Decision
No evidence supports changing LONG1 or SHORT1 strategy thresholds after the lock. Keep SHORT1 V50 context sizing and LONG1 current gates. Keep Central Risk DD12/R06 as the current research candidate rather than lowering to 11%.

Before production, two engineering items remain mandatory: (1) Central Risk MTM updates must run continuously/tick-level so a threshold crossing is acted on before another minute closes; (2) exposure ratios must be continuously monitored/rebalanced/frozen because gross/equity and abs-net/equity can drift above nominal entry caps when MTM equity falls. These are runtime safety corrections, not new alpha filters.

Forward shadow should continue collecting evidence on SHORT1 V50 adverse context and LONG1 hazard/revalidation. Historical month-specific filters should not be added without forward evidence.
