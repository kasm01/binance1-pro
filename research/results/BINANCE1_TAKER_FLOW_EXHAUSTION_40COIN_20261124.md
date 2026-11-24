# Binance1 — 40-coin taker-flow and reversal-exhaustion SHADOW

Date: 24 November 2026. No Binance orders, no Telegram early signals or READY.

## Source / cost engineering

Binance USD-M Futures public 1m kline REST index 10 and kline WebSocket k.Q carry taker BUY quote-asset traded volume. Total quote traded volume is REST index 7 / WebSocket k.q. Taker sell quote notional is approximately total quote notional minus taker buy quote notional. This is AGGRESSOR volume, not resting order book and is NOT proof of imminent continuation, whale intent or liquidity at future execution.

Existing CLOSED-1m market bus now preserves verified taker_buy_quote_volume, where provided; it refuses negative, nonfinite, or >total values. Legacy synthetic 8-field candles remain compatible, but flow on missing fields becomes FLOW_UNVERIFIED rather than invented positive volume.

No extra WebSocket stream or recurring REST call is required: same 40 unique streams, one shared cache, all 8 direction strategies. Existing TELEGRAM WATCH policy is untouched.

## Research-only directional flow / exhaustion classifier

scanner/taker_flow_quality_shadow_v1.py:
- 65 strictly consecutive, completed 1m OHLCV bars, all with taker buy quote volume and valid source time.
- 3m, 5m, 15m aggressive buy-versus-sell directional imbalance. Positive means taker flow supports the requested LONG or SHORT.
- FLOW_OPPOSING when strong opposite taker pressure persists in 3m or 5m; FLOW_EXHAUSTION_CAUTION when 3m pressure fades vs 15m, or last closed candle shows an opposing wick/weak continuation.
- FLOW_SUPPORTIVE when 3m/5m directional pressure strong and 15m not opposite, subject to candle continuation; otherwise FLOW_MIXED.
- Fixed thresholds here are exploratory hypotheses, not learned parameters or evidence of future trading edge.
- All result states have ready=false, telegram_ready=false, order_authorized=false. No real Telegram message is produced by this classifier.

## 40-coin recent historical research

One-shot 40 public 1m kline requests + time request.
40/40 current live universe symbols returned valid source klines.
Approximately 12.5 hours per symbol, as-of closed 1m candles only.
173 non-overlapping-by-60m-per-direction early candidate episodes had a complete future 15m path.

| Early candidate flow class | N | 15m directional reversal | Mean terminal direction return |
|---|---:|---:|---:|
| Supportive | 113 | 68 (60.2%) | -0.2134% |
| Mixed | 45 | 27 (60.0%) | -0.1936% |
| Opposing | 6 | 5 (83.3%) | -0.2422% |
| Exhaustion caution | 9 | 9 (100%) | -0.5152% |
| All | 173 | 109 (63.0%) | -0.2249% |

Supportive alone does not demonstrate positive price followthrough.
Opposing and exhaustion appear risky in this narrow sample, but groups
of 6 and 9 are too small for reliable probabilistic conclusions.

The sample is short and highly cross-coin correlated; time-half
descriptions are in the accompanying JSON for basic sensitivity only,
not out-of-sample evidence. The same period was used to inspect the
model and all statistics are exploratory. No commissions, spread,
market impact, slippage, funding or real execution timing are included.
These are not realized P&L or leverage-based ROIs.

## Live integration

- Normal early candidate detection and normal strong WATCH remain unchanged.
- Per early candidate, compute flow SHADOW from the single common CLOSED-1m source and count classification.
- If a new early episode is registered, also save its flow class, reason and 3m imbalance alongside 5/15/30/60m outcome telemetry in the private run/signal_center/early_watch_outcomes.json.
- A missing/invalid flow source is marked FLOW_UNVERIFIED and never causes Telegram sending or promotion.
- No extra Binance REST calls beyond existing conditional execution-cost quote logic. No new timers or services.

## Next validation

Collect multiple days of actual live early episodes with persisted
flow state. Compare same symbol/direction/time cohorts,
block-bootstrap by day and coin group, then test fixed rules
out-of-time. Incorporate real fee tier, costs and delayed fills
before proposing READY. Do not promote supportive taker flow
to actionable manual entries based on this sample.
