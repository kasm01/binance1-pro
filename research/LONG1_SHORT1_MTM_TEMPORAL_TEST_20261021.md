# LONG1 + SHORT1 Central Risk MTM V2 — Daily / Weekly / Monthly Test

Date: 2026-10-21
Status: RESEARCH / SHADOW ONLY. No production routing authority.

## Test basis
- LONG1: corrected causal single-position + completed flow60 exhaustion >= +0.20 block.
- SHORT1: V49B R70/W2 source trade stream.
- Shared portfolio start equity: 1000 USDT.
- Strategy budget: 50% LONG1 / 50% SHORT1.
- Entry-time caps: gross 1.00x equity, long 0.50x, short 0.50x, abs-net 0.50x, per-symbol 0.50x.
- Open fee: 0.04% charged immediately; source net trade economics preserved at close.
- MTM: minute-by-minute 1m close valuation of all open positions.
- Common market-price coverage: 2025-10-01 through 2026-10-11; effective shared trade window approximately 2025-10-13 through 2026-10-08.
- October 2025 and October 2026 monthly rows are partial months.
- Six LONG execution seeds tested against the same SHORT stream.

## MTM scenario summary
| Scenario | Mean return | Min seed | PF | Mean MTM DD | Worst seed DD | Return std |
|---|---:|---:|---:|---:|---:|---:|
| STATIC | +179.14% | +162.71% | 1.1980 | -15.95% | -16.32% | 11.82 |
| DD 8/4 | +115.33% | +103.48% | 1.1821 | -12.69% | -13.00% | 11.48 |
| DD 10/5 | +129.54% | +104.16% | 1.1792 | -12.80% | -13.05% | 18.91 |
| DD 12/6 | +140.98% | +128.35% | 1.1766 | -14.14% | -14.42% | 10.39 |
| DD 14/7 | +156.36% | +141.79% | 1.1899 | -15.17% | -15.56% | 10.66 |

## Interpretation
8/4 is too aggressive for the diversified portfolio. Relative to 10/5 it saves only about 0.10 percentage-point additional mean DD while losing about 14.2 percentage points of mean return. 10/5 gives the best simple return-cost per DD improvement, but is highly path/seed sensitive (return std about 18.9) and turns both May and September negative on average. 12/6 is the most balanced current research candidate: materially stronger minimum seed return and much lower seed dispersion than 10/5, while still reducing MTM DD versus STATIC. 14/7 preserves return better but provides only modest DD protection.

## Daily distribution
Across the 361-day effective window the sign pattern is identical across sizing-state scenarios because Central Risk changes size, not source trade direction: 190 positive days, 118 negative days, 53 flat days.

For DD12/R06:
- Positive days: 190 / 361 = 52.63%.
- Mean daily return: +0.2564%; median +0.0575%.
- Worst day: 2026-02-06, mean -5.2142%.
- Best day: 2026-06-04, mean +6.5716%.
- Days with mean return <= -3%: 10.
- Days with mean return <= -5%: 3.
- Days with worst intraday DD <= -5%: 11.
- Days with worst intraday DD <= -8%: 1.

STATIC comparison:
- Worst day: 2025-11-10, -6.5403%.
- Best day: 2026-06-04, +6.6382%.
- Worst daily intraperiod DD: -8.7016%.

## Weekly distribution
For DD12/R06:
- 52 ISO weeks: 35 positive, 17 negative.
- Positive-week rate: 67.31%.
- Mean weekly return: +1.7940%; median +0.7124%.
- Worst week: 2026-W21, -6.8654%.
- Best week: 2026-W23, +19.1238%.
- Weeks <= -3%: 2; weeks <= -5%: 2.
- Weeks with worst intraperiod DD <= -5%: 15; <= -8%: 7.

Notable weak weeks under DD12/R06:
- 2026-W21: -6.8654%, worst week DD -8.2787%.
- 2026-W38: -6.5369%, worst week DD -10.6281%.
- 2026-W39: -2.7989%, worst week DD -8.6868%, global DD reached -12.5724%.

## Monthly distribution
DD12/R06 has 13 calendar rows including two partial Octobers: 10 positive months and 3 negative months. Mean monthly return is +7.478%; median +3.178%.

Full DD12/R06 monthly mean returns:
- 2025-10 partial: +26.22%
- 2025-11: +3.11%
- 2025-12: -1.90%
- 2026-01: -1.54%
- 2026-02: +9.02%
- 2026-03: +6.64%
- 2026-04: +4.46%
- 2026-05: +1.14%
- 2026-06: +33.29%
- 2026-07: +3.18%
- 2026-08: +13.56%
- 2026-09: -2.11%
- 2026-10 partial: +2.15%

Best full month: June 2026, +33.29%. Worst monthly mean: September 2026, -2.11%. Worst seed-level intramonth DD under DD12/R06: -14.42% (November 2025).

## Critical-month deep dive
### April 2026
DD12/R06: +4.46% mean, seed range +3.85% to +4.82%, PF 1.453, worst intramonth DD -3.57%. 17 positive days, 5 negative, 8 flat. Worst day Apr-02 -1.59%; best Apr-26 +2.34%. No <= -3% day. Central DD state is effectively inactive here.

### May 2026
STATIC: +2.21% mean; DD12/R06: +1.14% mean, seed range -2.51% to +4.12%, PF 1.011, worst intramonth DD -12.40%. 17 positive days, 12 negative, 2 flat. Worst day May-18 -5.01%; best May-30 +2.97%. Four days <= -3%; five days had worst daily DD <= -5%.
Strategy contribution under DD12/R06: LONG1 +100.78 USDT mean, SHORT1 -83.10 USDT mean. Weakness is SHORT-led but LONG diversification keeps the month positive on average.
Key ISO weeks: W20 +5.54%, W21 -6.87%, W22 +2.37% with global DD reaching -12.40%.

### July 2026
DD12/R06: +3.18% mean, seed range +3.02% to +3.40%, PF 1.466, worst intramonth DD -2.73%. 14 positive days, 9 negative, 8 flat. Worst day Jul-03 -2.22%; best Jul-06 +2.25%. No <= -3% day.
Strategy contribution: LONG1 +72.36 USDT, SHORT1 -7.04 USDT mean. July is healthy and low-risk despite SHORT being mildly negative.

### September 2026
STATIC: +1.14% mean; DD12/R06: -2.11% mean, all six seeds negative (-3.07% to -0.84%), PF 0.968, worst intramonth DD -12.57%. 16 positive days, 12 negative, 2 flat. Worst day Sep-19 -4.09%; best Sep-09 +2.56%. Only one day <= -3%, showing that the monthly loss is cumulative rather than a single crash.
Strategy contribution under DD12/R06: LONG1 +191.15 USDT mean versus SHORT1 -238.22 USDT mean. September is therefore primarily a SHORT-side portfolio problem, not a LONG failure.
Key ISO weeks: W37 +6.77%, W38 -6.54%, W39 -2.80%, W40 +1.52%. W38-W39 is the main damage cluster.

## Architecture conclusion
- Do not promote the SHORT-local 8/4 DD state to portfolio production.
- Keep Central Risk Master NORMAL/RECOVERY/REDUCED architecture.
- DD12/R06 is the current balanced MTM research candidate, not a production lock.
- DD10/R05 remains a more protective alternative but is materially less seed-stable and makes May/September weaker.
- Entry-time exposure caps remain sensible at gross 1.00x / side 0.50x / abs-net 0.50x / symbol 0.50x for LONG1+SHORT1 research.
- Because notional is fixed after entry, gross/equity can drift above 1.00x during adverse MTM; observed maximum was about 1.022x. The runtime Central Risk service therefore needs continuous open-position exposure telemetry, not entry-time checks only.
- September requires separate SHORT-side analysis before final Central Risk calibration; simply tightening portfolio DD sizing can suppress profitable LONG recovery while leaving the bad SHORT regime unresolved.

## Output files
Directory: `research/results/LONG1_SHORT1_CENTRAL_RISK_MTM_V2_20261021/`
Contains per-seed minute curves and closes, daily/weekly/monthly tables, aggregate temporal tables, critical-month daily detail, strategy contribution analysis, and scenario summaries.
