# Binance1 LONG1/SHORT1 — Market Context & Entry Confirmation SHADOW

Date: 24 Nov 2026. Manual-only. No trade orders and **no Telegram READY**.

## Scope and correctness
The existing one-WebSocket 40-coin closed-1m source remains the canonical data feed.
New module scanner/context_entry_shadow_v1.py evaluates at least 125 **consecutive
closed 1m** OHLCV candles. Signals are evaluated exclusively at their real
observation time, with stale/partial/gap/invalid input rejected. Cache increased
from 80 to 180 bars per coin; public REST bootstrap uses up to 180 1m candles
per coin (still 40 unique streams, not one feed per strategy).

The 3m, 5m, 15m and 60m returns are **rolling spans** constructed from
closed 1m bars; they are NOT claimed to be native fully closed Binance
3m/5m/15m/1h bars. The 60m horizon must confirm the requested direction,
so 1m recoveries cannot automatically justify counter-trend entries.

## Shadow rules (research hypotheses, NOT calibrated for trading)
- Existing strong WATCH trigger remains first-pass; contradictory direction
  is filtered and all WEAK observations are rejected.
- Rolling 15m and 60m must point in candidate direction;
  3m and 5m must not contradict: otherwise CONTEXT_PENDING.
- Last 1m candle must align with direction and body/range >= 0.25;
  otherwise ENTRY_PENDING.
- One-minute ATR(14) from *already closed* bars; 20m mean extension in
  units of ATR must be <=3 and >=-0.5; very late chasing or
  unfavorable mean dislocation is ENTRY_PENDING.
- Last 3 minutes cannot reverse the candidate direction.
- Even if all above pass: **COST_PENDING** because 40-coin core does not
  provide live bid/ask spread, verified trading fee tier, achievable manual
  fill/slippage, funding nor liquidity-based risk/reward. It MUST NOT
  emit READY until independent evidence is validated.
- Every assessment explicitly has ready=false,
  telegram_ready=false, order_authorized=false.

This is a **research shadow alongside**, not a change to the established
LONG1/SHORT1 strong-WATCH Telegram alert logic. Some WATCH alerts may still
arrive; those messages are not entry confirmations. When WATCH fires,
logs include context_shadow_state and context_shadow_reason. Local status
snapshot contains research_context_state/reason for current watches;
Telegram /signals read-only formatter can show them in future.

## Backward test — stored historic NEARUSDT market bars
From 8640 historical one-minute bars across Nov 10-15:
every 5 minutes, 160 closed 1m candles were evaluated as-of.
58 WATCH observations (not independent opportunities or fills):
- 41 ENTRY_PENDING:
  - 20 late_extension_over_3atr
  - 21 last_closed_1m_not_directionally_confirmed
- 9 CONTEXT_PENDING:
  - 6 short_horizon_not_aligned
  - 3 opposing_15m_or_60m_trend
- 8 COST_PENDING:
  - no verified spread / fee / slippage cost yet
- 0 READY, 0 real trades, no simulated P&L inferred.

All thresholds are initial research hypotheses: this sample does
not establish performance, hit rate, generalization, or profitability.
Coin NEAR was only historical test data, not necessarily in 40-coin
live universe (first 15 by 24h volume excluded).

## Reliability and next steps
- Cold startup no replay/stale signal promotion.
- Telegram pilot send remains restricted to LONG1/SHORT1 strong WATCH,
  current opt-in only, no READY or BUY/SELL.
- Live Binance order and legacy supervisor services remain off.
- Next: real bid/ask spread via conditional public bookTicker only for
  surviving candidate, spread/fee/slippage and R-multiple cost checks,
  then walk-forward false-positive/overfitting assessment before
  user-visible READY can ever be considered.
- Only once those tests pass should the new READY branch be separately
  authorized. Never use fake proof booleans to bypass it.
