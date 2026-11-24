# Binance1 / 40-coin manual monitoring — Execution Cost & Risk SHADOW

24 Nov 2026. This is research-only: automatic orders and Telegram READY remain disabled. Existing LONG1/SHORT1 strong WATCH notifications are unchanged.

## Public data

GET /fapi/v1/ticker/bookTicker?symbol=SYMBOL (USD-M Binance). No signed endpoints, account key, real orders or fee account lookup.

A quote is requested only after the 3/5/15/60m context and 1m entry SHADOW gate yields COST_PENDING. A global rate gate allows at most 1 best-bid/ask REST request every 15 seconds across all 40 symbols. 2.5s HTTP timeout, 1.5s response latency threshold and 3.5s maximum candidate context age. No repeat 40-symbol level2 polling. Quote does not prove exchange update time or achievable manual fill.

## Research assumptions (not verified actual fee tier or slip)

- Mid = (bid+ask)/2.
- Spread bps = 10000*(ask-bid)/mid.
- Hypothetical round-trip friction = spread bps + 2*(5 bps fee per side + 5 bps hypothetical slippage per side).
- Fee 5 bps per taker fill is a Binance regular-tier FAQ example; NOT personalized account pricing.
- Slippage 5 bps each side is an assumption; never a guaranteed upper bound.
- The indicative notional is 100 USDT, solely for best-quote depth research. Best bid AND ask quantities must each carry >=3x this notional.
- Spread >12 bps -> COST_REJECT.
- Nominal protective stop budget for comparing costs is 2x 1m ATR14; friction/stop budget >0.35 -> COST_REJECT.
- Passing any of these rough tests yields COST_ESTIMATE_PASS but READY remains false, telegram_ready false, order_authorized false. No valid stop/target price, funding, limit order book depth, real fill or R:R has been proven.

## Real public quote connectivity

Single Binance USD-M public quote request for AIOTUSDT returned HTTP 200 in about 254 ms. Best-price spread at observed instant ~6.885 bps; with an expressly artificial context, output COST_REJECT. It is a technical quote endpoint test, not actual AIOT trade signal or validated entry.

## New components

- scanner/execution_cost_shadow_v1.py: pure fail-closed bid/ask, top-size and estimated friction comparisons.
- scanner/cost_quote_public_v1.py: bounded authenticated-free GET, stale/response checks, no output READY.
- scanner/manual_watch_runner_v1.py: only COST_PENDING candidates query quote, asyncio.to_thread to avoid waiting on HTTP inside WebSocket reader, global 15s rate gate, adds short-lived cost details to private status snapshot and WATCH_PREVIEW log; normal Telegram WATCH dispatch is unchanged.
- tests/test_execution_cost_shadow_v1.py: eligibility, NaN/stale/wrong identity, spread, shallow quotes, cost budget, zero-order no-send and shadow status.

43 unit tests PASS. Existing Stage22 and Stage24 strict order safety regression PASS.

## Future tasks

First observe bounded quote calls in live logs and ensure 40-symbol stream health. Then gather forward outcomes for false alarms and calculate impact of real fee tier, funding and execution; native 3m/5m/15m/1h reference checks and verified RR. No READY until there is independent validated proof, and no automated Binance trade authority in this project.

Sources: Binance official USD-M Futures bookTicker docs, Binance Futures fee structure FAQ.

## Follow-up: Restart-safe Telegram WATCH deduplication

A real operational bug was observed during testing: a manual service
restart reset the in-memory 2-hour Telegram cooldown. Consequently,
a previously delivered ELSAUSDT SHORT1 WATCH was sent again shortly
after restart. This was a **research WATCH**, not READY or an order.

Fix: SignalDispatcher now optionally persists the last confirmed
send state to a root-local JSON file:
run/signal_center/telegram_cooldown.json
with private 0600 file and 0700 directory permissions.
When the service restarts, it loads this per-strategy/per-symbol
cooldown and suppresses duplicates for 2 hours.
Corrupted persisted state fails CLOSED (no Telegram delivery).
Only true API-confirmed sends are written to the state file;
failed API responses never mark delivery.

The initial state was seeded from confirmed Telegram SENT journal
events in the last 2 hours (one eligible LONG1/SHORT1 key) before
the updated service was restarted. This is runtime state, NOT
committed to GitHub, and no Telegram secret is included in reports.

3 additional unit tests verify persistence across process restart,
corrupt-state fail closed, and no state after failed send.
Total 46 unit tests PASS, Stage22/Stage24 strict order safety PASS.
Actual service checked ACTIVE with 40/40 valid coin sources,
no startup restarts, order_authorized false.
