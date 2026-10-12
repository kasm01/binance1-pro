# LONG1 NEARUSDT — FINAL LOCKED RESEARCH PROFILE

Date: 2026-10-12
Status: RESEARCH LOCKED / PRODUCTION NOT STARTED

## Architecture
MODEL → SIGNAL NORMALIZATION → MARKET CONTEXT → MODEL SCORE GATE → SNIPER → ENTRY CONFIRMATION → PENDING REVALIDATION → EXECUTION RISK → FINAL SAFETY → ORDER → POSITION LIFECYCLE → TELEMETRY / OUTCOME FEEDBACK

## Final candidate settings

- Symbol: NEARUSDT
- Side: LONG
- Base model threshold: 0.525
- Dynamic recovery floor: 0.5114
- ATR-rank recovery condition: >= 0.60
- Recovery condition: close_loc >= 0.25 OR lower_wick_frac >= 0.25
- Max entry layers: 3
- Normal-mode sizing: 1.00x + 0.50x + 0.50x equity notional (max 2.00x)
- Leverage: 3x
- Approx max margin use at full 3 layers: 66.7% of equity
- Equity DD governor trigger: -8% from equity peak
- Reduced-mode sizing: 0.50x + 0.10x + 0.10x equity notional (max 0.70x)
- Return to normal sizing: equity DD recovers to -4%
- ROI arm: +4.0%
- ROI giveback: 0.24%
- Normal SL trigger: -2.99% price
- Dynamic stop confirmation: 30 seconds
- Catastrophic stop: -3.50% price
- Negative stall: OFF
- Profit stall minimum: +0.10% price
- Same-symbol add interval / cooldown: 180 seconds
- Fee assumption: 0.04% taker per side

## Final validation summary

| Horizon | Mean Return | Worst Seed | Best Seed | Mean Entries | Win Rate | Profit Factor | Mean Closed DD | Worst Closed DD | Mean Fees |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 6 months | +96.14% | +78.21% | +111.05% | 248.8 | 87.88% | 2.01 | -15.24% | -16.13% | 191.06 USDT |
| 1 year | +87.41% | +45.67% | +117.55% | 655.3 | 82.83% | 1.43 | -26.62% | -28.39% | 278.04 USDT |
| Forward ~27d | +15.48% | +9.53% | +24.55% | 26.7 | 86.84% | 2.61 | -8.31% | -9.51% | 17.37 USDT |

## Interpretation

- The previous conservative profile produced roughly +17.9% over one year and was economically weak after infrastructure and trading costs.
- Raising the ROI arm to 4.0% materially improved payout per winner.
- Increasing notional while keeping leverage at 3x improved capital efficiency, but raw 2.0x sizing caused unacceptable drawdown; the equity-drawdown governor reduced this risk materially.
- The final profile remains LONG-only and still suffers during prolonged bearish regimes. Portfolio completion therefore requires a SHORT side rather than further overfitting LONG1.
- Historical and forward results are simulations, not guarantees of live performance. Funding, slippage, partial fills and exchange microstructure are not fully modeled.

## Freeze decision

LONG1 parameter optimization is frozen at this profile. Do not change threshold / TP / stop / layer logic without a new controlled A/B study.
Next workstream: SHORT reference bot optimization, then multi-coin LONG/SHORT portfolio risk governor.
