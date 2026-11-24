# Binance1 — WATCH forward MFE/MAE outcome ledger / 24 Nov 2026

## Scope and integrity

40 unique USD-M perpetual coins, single existing closed 1m WebSocket
shared by LONG1-4 and SHORT1-4, without any extra Binance market
data requests. Record strong WATCH/EXTREME_WATCH at its own closed
1m reference price. Separate episodes per symbol+direction by 60 minutes,
so 5 consecutive WATCH updates do NOT become 5 independently counted
signals. Episode record keeps direction, signal status, context state,
reason, observed close timestamp/price. No READY or exchange orders.

Follow only **future closed 1m** OHLC, strictly consecutive 60000ms
timestamps, and calculate directional path excursions 5/15/30/60m.
LONG: MFE max(future high/reference -1), MAE min(future low/reference -1).
SHORT: MFE (1-min(future low/reference)), MAE
(1-max(future high/reference)); direction-signed terminal close return.
No intra-candle order of high/low is inferred. All paths label
not_fill_or_ROI=true. They are NOT leverage ROI, exchange fills,
realized P&L, achievable exit quotes, fees, or net trader profits.

On data gap/missing future bars, mark episode INVALID instead of
pretending complete. End of horizon remains PENDING until enough
real closed bars arrive. Coinbase or third-party feed not needed.

## Offline historical NEARUSDT as-of test

Stored 8640 historical 1m bars, scan every 5 minutes:
68 strong WATCH observations -> 41 deduplicated independent
60-minute-separated reference episodes. All 41 obtained complete
60-minute closed OHLC paths, no gaps in this stored sample.

Horizon / average favorable high-low path / average adverse path /
direction-signed final close (all raw percent of underlying):
- 5m: +0.4554% MFE, -0.3674% MAE, -0.0209% terminal
- 15m: +0.6109% MFE, -0.5749% MAE, -0.0955% terminal
- 30m: +0.7828% MFE, -0.7921% MAE, -0.1766% terminal
- 60m: +1.0887% MFE, -1.0799% MAE, +0.0386% terminal

The first three average terminal directional returns are negative.
This is not calibrated performance, strategy proof or a true walk-forward
independent-coin backtest. NEAR was an archived test asset and may be
excluded by current top-15 universe logic. No costs, stop timing, slippage,
market impact, maker/taker discounts or funding are included.
No realized trade or target fill was assumed, even though candle
high/low spans show theoretical extremes. No automatic orders.

## Implemented

scanner/watch_outcomes_v1.py:
- OutcomeLedger persisted local private JSON at
  run/signal_center/watch_outcomes.json (0700 folder/0600 file).
- Duplicate episode guard: 60m same symbol + direction;
  cumulative 5/15/30/60m exact future closed path;
  1000-record bounded ledger and max 200 pending;
  corrupt or oversize state fails closed (telemetry only).
- On source gap mark pending episode invalid, no fake forward return.
- On disappearing dynamic universe, invalidate removed symbols'
  pending outcomes rather than silently finalizing or losing them.
- Restart-safe, persist checkpoints on new episode, outcome and invalidation.
- A completed record is not an exchange execution; no READY promotion.

scanner/manual_watch_runner_v1.py:
- One outcome tracker for all symbols and all 8 direction instances,
  separate from 2-bot Telegram WATCH pilot; tracker does not send Telegram.
- Feed closed bars to OutcomeLedger for MFE/MAE checkpoints.
- Link each strong WATCH to its context decision and source timestamp.
- Private status JSON now has outcome_telemetry summary;
  WATCH_PREVIEW journal has outcome_tracking classification.
- No new network endpoints and no change to WATCH notification thresholds.

Test suite:
- 5 new unit tests: LONG/SHORT direction math,
  exact forward timestamps/no lookahead,
  60m duplicate suppression, restart persistence,
  incomplete data invalidation and fail-closed corrupt state.

## Next measurement

Run live for enough time to observe full 60m horizons for multiple
different coins/regimes. Track forward MFE/MAE distribution rather than
only averages; add block bootstrap over independent episodes, fee and
spread hypotheses, post-signal entry delay. No READY until validation
on an out-of-sample time period and independently verified trading costs.
