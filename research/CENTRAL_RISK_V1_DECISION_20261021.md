# Central Risk V1 Decision — 2026-10-21

Status: RESEARCH / SHADOW ONLY. Production routing unchanged.

## Architecture work completed
- LONG same-symbol averaging-down disabled: one strategy slot -> one position.
- LONG completed 15m/60m taker-flow telemetry added from existing 3m kline response; no extra request.
- LONG `flow60 >= +0.20` exhaustion candidate is shadow-only and never closes an existing position.
- Canonical causal `entry_market_context.v1` ported to LONG: completed 15m price response + taker flow + strictly-prior 5m Binance USD-M OI.
- NEAR OI collector cost: one public `openInterestHist(limit=5)` request / 5 minutes = 288/day.
- LONG model-shadow reuses existing 3m response and direct SGD artifact; no extra market-data request/process.
- LONG 5s/20s/30s hazard mirror reuses existing NEAR trade/depth/bookTicker WS; no extra WS. Outcome labels: 1m/3m/5m return, MFE, MAE.
- Common pure `orchestration/risk/central_risk_master.py` created; no executor is wired to it yet.

## Causal simulator correction
A same-minute research replay bug was found: lifecycle price samples earlier than randomized entry progress could be evaluated after entry. Five of six seeds had one `exit < entry` trade. The rebuild simulator now filters first-minute lifecycle samples to `sample_progress >= entry_progress` and asserts `exit > entry` for every trade.

Corrected LONG1 single-position + flow60(+0.20) six-seed reference:
- mean return: +32.6938%
- mean PF: 1.20550
- mean realized/closed-equity DD: -20.6314%
- worst seed DD: -23.9588%
The correction did not materially alter the prior +32.67% economic conclusion, but it is required for correct cross-strategy event ordering.

## LONG1 + SHORT1 overlap / exposure
Using corrected LONG1 single-position flow20 and SHORT1 V49B R70/W2:
- simultaneous LONG1+SHORT1 active time: mean 2.3411%
- at least one active: mean 44.7363%
- flat: ~55.2637%
- under 50/50 strategy budgets, time-weighted gross p90 = 0.25x portfolio equity
- gross p95/p99 = 0.50x
- observed gross max = 1.00x during rare simultaneous full-budget exposure
- observed absolute net max = 0.50x because the two engines are opposite directions

Research-only two-bot exposure-cap candidate:
- gross <= 1.00x portfolio equity
- LONG <= 0.50x
- SHORT <= 0.50x
- abs net <= 0.50x
- per-symbol <= 0.50x
These are NOT the final 8-bot caps; LONG2-4/SHORT2-4 correlation and same-direction clustering must be simulated first.

## External Central Risk replay
Method:
- remove local DD sizing by normalizing each source trade as `net_pnl / source_notional`;
- preserve fee-inclusive trade economics;
- SHORT market-context multiplier reconstructed independently from V49B entry-time sizing mode (context 1.0 or 0.5);
- apply shared portfolio equity, 50/50 strategy budgets, central state multiplier, market-context multiplier and exposure caps at entry;
- close PnL scales linearly with centrally allowed notional;
- realized-equity state only; this is not yet minute-by-minute MTM replay.

Corrected six-seed results:
| Scenario | Mean return | Mean PF | Mean DD | Worst DD | Mean cap-limited opens | Rejects |
|---|---:|---:|---:|---:|---:|---:|
| EQ50 static | +182.76% | 1.1939 | -15.32% | -15.68% | 15.3 | 0 |
| Central V49, gross 1.00 | +123.28% | 1.1769 | -12.28% | -12.58% | 8.7 | 0 |
| Central V49, gross 0.75 | +113.40% | 1.1959 | -13.13% | -13.31% | 83.0 | 0 |
| Central V49, gross 0.60 | +118.13% | 1.2133 | -13.18% | -13.90% | 146.7 | 0 |

Decision: gross 1.00x is the best current two-bot cap candidate. Tighter 0.75/0.60 caps intervene much more often without improving realized DD.

## Portfolio DD threshold sweep
With gross=1.00, side/net/symbol=0.50, RECOVERY=.70, REDUCED=.50, two recovery successes:
| DD reduce / recover | Mean return | Mean PF | Mean DD | Worst DD |
|---|---:|---:|---:|---:|
| 8% / 4% | +123.28% | 1.1769 | -12.28% | -12.58% |
| 10% / 5% | +134.09% | 1.1745 | -12.80% | -13.08% |
| 12% / 6% | +140.70% | 1.1700 | -14.07% | -14.56% |
| 14% / 7% | +158.52% | 1.1852 | -15.03% | -15.14% |
| static reference | +182.76% | 1.1939 | -15.32% | -15.68% |

Decision: do NOT promote SHORT's 8%/4% DD thresholds directly to portfolio Central Risk. In a diversified LONG1+SHORT1 portfolio, 8/4 is too expensive in return for the realized-DD improvement. 14/7 barely improves DD. Final central DD triggers require a true mark-to-market shared-equity replay; keep state-machine architecture but leave portfolio thresholds provisional.

## Runtime sizing note
`PER_POSITION_BALANCE_PCT=0.50` in current LONG runtime truly means 50% of available balance notional; leverage is not multiplied into that notional calculation. Do not simply change this to 1.00 before central allocation exists. In the final architecture the Central Risk Master must issue each engine's allowed notional/budget; strategy engines must not independently claim a percentage of global account equity.

## Safety / promotion
- Central Risk core is pure/research only; not connected to order routing.
- LONG flow/OI/hazard remain shadow/telemetry only.
- Production orch/supervisor remain stopped while this research runs.
- Before production integration: build true MTM shared-equity replay, calibrate portfolio DD thresholds, then test 8-engine allocation/correlation caps.
