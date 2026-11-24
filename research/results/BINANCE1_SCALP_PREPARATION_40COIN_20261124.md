# 30–45m Market Preparation + 1–15m Scalp — SHADOW research

Date: 24 November 2026. No new Telegram signals, READY or automatic Binance orders.

## Implementation

scanner/scalp_preparation_shadow_v1.py classifies CLOSED 1m prices and
Binance taker-buy quote-volume context into:
- TREND_CONTINUATION: prior 30–45m direction supported by 15m taker
  flow, without strong opposing recent pressure or late 5m extension
- EARLY_REVERSAL: historical 45m trend but short-horizon opposing
  taker pressure and price structure suggests reversal preparation
- NO_PREPARATION: weak or ambiguous evidence
- PREPARATION_UNVERIFIED: missing taker source, invalid / partial
  1m bar, source gap, or less than 90m contiguous history.

These are exploratory deterministic heuristics; they do not
forecast with calibrated probabilities or predict an exact start.
The runner logs SCALP_PREPARATION_SHADOW at most once per 30m
per symbol, direction and mode. No extra Binance data stream,
new recurring REST calls, new service, or cost subscription.
Existing Telegram and 8 directional group allocation untouched.

## 40-coin retrospective observation

41 public Binance REST requests (one server time + 40 klines).
40 / 40 coins valid on final pass; ~12.5 hours per coin.
Closed-bar-only direction preparation matched independently
observed early / strong momentum events in the preceding
5–45 minutes. 60m same-direction episode dedup.

| Trigger | Preparation | Episodes | Mean 5m close | Mean 15m close |
|---|---|---:|---:|---:|
| EARLY | None | 33 | -0.0441% | -0.1078% |
| EARLY | TREND_CONTINUATION | 89 | -0.0242% | -0.1107% |
| EARLY | EARLY_REVERSAL | 40 | -0.4502% | -0.5759% |
| STRONG | None | 29 | +0.0375% | +0.2496% |
| STRONG | TREND_CONTINUATION | 79 | +0.0049% | +0.0459% |
| STRONG | EARLY_REVERSAL | 25 | -1.3551% | -1.4723% |

162 early, 133 strong (295 total). Median earliest historical
preparation within matched 5–45m window: approximately
33–38m before the trigger. This is RETROSPECTIVE MATCHING
conditional on a known trigger; it does NOT prove the system
would anticipate an impulse 30–45 minutes in advance.
Without evaluating ALL preparation episodes (including ones
not followed by an impulse), no precision/false alarm rate
or predictive advantage can be claimed.

EARLY events overall: mean 5m -0.1334%, 15m -0.2249%.
STRONG events overall: mean 5m -0.2436%, 15m -0.1951%.

## Limitations, next development

This sample is ~12.5h, highly coin-correlated and often shares
market regimes. Forecast accuracy and forward event base rate
NOT verified. No trade fills, spreads/commissions/slippage,
funding, 3x ROI, intrabar timing or profit-lock modeling.
1m closed triggers can remain late for 1–3m moves.

EARLY_REVERSAL-prepared cases are currently particularly poor:
we do not promote such labels to Telegram or READY.
Continue with event-first study: log first preparation
state transitions, then look at the future 1/3/5/10/15/30/45m
whether an impulse materialized, including no-move cases.
Only then assess 1–15m scalp entry triggering.
