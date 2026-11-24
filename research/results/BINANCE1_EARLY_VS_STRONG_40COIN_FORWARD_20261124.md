# Binance1 — 40-coin Early vs Strong WATCH forward outcomes

24 November 2026. PUBLIC MARKET DATA ONLY. No Telegram early alerts or Binance orders.

## Goal
Measure whether 3m early movement candidates found before 15m strength
have more favorable follow-through than the existing strong WATCH filter.
Compare identical CLOSED 1m OHLC forward horizons without mistaking candle
high/low as executable profits or bot ROI.

## Data
- Live market universe (40 unique currently selected USDT-M perpetual symbols).
- One-shot public GET /fapi/v1/time + 40 GET /fapi/v1/klines
  with limit=750, 1m -> 41 public REST requests.
- 40/40 coin queries returned valid consecutive closed candles (749 each).
- The period is only the latest ~12.5 hours of public exchange history
  and must not be called a broad cross-regime backtest or out-of-sample proof.
- One signal snapshot per CLOSED 1m; same symbol + same direction
  60min episode cooldown within each research method.
- 15m future direction-signed close, high/low MFE/MAE (underlying
  price %, no leverage, fees, funding, slippage or actual trading).
- Comparison is descriptive: early and strong candidates can be at
  different times on the same symbol and overlap with each other.

## Full 40-coin evidence

| Metric | Early 3m shadow | Existing strong WATCH |
|---|---:|---:|
| Episodes with 15m forward path | 171 | 155 |
| 15m terminal reversal | 107 (62.6%) | 86 (55.5%) |
| Mean 15m directional close | -0.2250% | -0.1451% |
| Mean 15m candle-path MFE | +0.7712% | +1.0762% |
| Mean 15m candle-path MAE | -0.9830% | -1.2642% |

Among 155 strong-WATCH episodes, 65 had a same-direction
early episode occurring within the prior 30 minutes. Median lead
in those matched events is 2 minutes. Matches are conditional;
do not infer that early detection precedes all strong WATCH events.

The earlier limited 12-coin sample looked even worse for the
early method (38/50 15m reversed) but it is only a subset, not
a second independent validation.

**Interpretation**: The first early 3m thresholds produce more
reversals and more negative average 15m directional close than the
strong 15m WATCH filter in this short sample, while sometimes
identifying the movement earlier. Neither method is ready for
unfiltered trading recommendations. All thresholds are research
hypotheses and not calibrated predictive probabilities.

## Live early Outcome Feedback integration

- Existing single Binance 40-symbol websocket and strong-WATCH
  outcome file remain unchanged.
- New separate private JSON outcome ledger:
  run/signal_center/early_watch_outcomes.json
  (0700 directory and 0600 file).
- scanner/watch_outcomes_v1.py: additional observe_early():
  requires matching symbol, direction, closed-candle timestamp,
  EARLY_CANDIDATE_SHADOW and both READY/order flags false.
- Same 5/15/30/60m exact consecutive closed-1m path evaluation,
  per symbol/direction 60m episode dedup, persistent across
  service restarts, invalidation on source gap or universe removal.
- runner invokes observe_early for all 40 symbols on qualifying
  closed bars, advances pending outcomes on later closed bars,
  and exposes early_outcome_telemetry in private status JSON.
- Early event logging at most once per 30m/symbol/direction.
- **Early Telegram send=FALSE unconditionally**. The existing
  LONG1/SHORT1 Telegram policy is independent; no READY and no
  trade/order authority.
- 1000 events per ledger + 200 pending max, intentionally
  bounded; if full, no further observations until future
  retention/archiving work. Do not silently delete evidence.

## Method limitations and next step

Observation sample is short; 40 symbols can be correlated in
a market-wide move, and series values from the same symbol are
not statistically independent across methods. No confidence
interval or multiple-hypothesis adjustment is yet calculated.
The methods' thresholds and symbol membership may also drift.
No measured transaction fees, spread at the historical entry,
or later achievable quotes are present.

Collect longer forward periods for multiple distinct market
regimes; use time-blocked/coin-clustered evaluation, split
fixed discovery period vs validation, compare alerts matched
on symbol+time and account for missing-data censored events.
Never automatically activate an early Telegram signal from
this preliminary cross-sectional snapshot.
