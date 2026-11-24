# Binance1: Late WATCH investigation & early-move SHADOW

24 November 2026. Manual monitoring only, NO READY and NO automated Binance orders.

## Actual Telegram WATCH notifications examined

Extracted API-confirmed SENT events (not all WATCH_PREVIEW log rows)
from the single VM's systemd journal, compared with public Binance
USD-M 1m klines. Signal reference = latest fully closed 1m bar
immediately before journal send time. Future paths use ONLY closed bars
that were available at the retrospective observation; not ongoing bars.

Times below UTC; Istanbul time = UTC+3.

- ELSAUSDT SHORT at 17:20:00: prior directional 15m -2.0358% underlying
  move; 5m directional close +0.167%, 15m -0.346%. Intra-15m worst
  adverse price movement -0.573% (SHORT).
  Context = ENTRY_PENDING / late_extension_over_3atr.
- ELSAUSDT SHORT at 17:21:00: prior 15m -2.2186%; next 5m directional
  close -0.215%, 15m -0.263%, 15m MAE -0.561%.
  Context = ENTRY_PENDING / last_closed_1m_not_directionally_confirmed.
  Duplicate actual Telegram send was caused by process restart before
  persistent cooldown was installed.
- SYRUPUSDT SHORT at 17:24:03: prior 15m -1.7066%; next 5m directional
  close -0.758%; next 15m directional close -0.813%, 15m
  worst adverse -1.474%.
  Context = ENTRY_PENDING / late_extension_over_3atr.
- ZROUSDT LONG at 17:34:00: prior 15m +1.3067%; next 5m +0.086%;
  public quote said COST_REJECT / shallow_best_quote. Subsequent
  15m not yet complete at evidence time.
- AIOTUSDT SHORT at 17:37:00: prior 15m -4.160%; next 3m
  directional close -0.384%; next 5m and 15m unavailable at
  evidence time. Context ENTRY_PENDING / late_extension_over_3atr.

These 5 Telegram sends are small overlapping real observations, NOT
5 independent profitable/unprofitable trades. They show that several
strong WATCH notifications were sent AFTER context already reported
a late or unconfirmed entry. Critically, the original WATCH dispatcher
had ignored context/cost because watch was merely advisory.

## Operational safety fix deployed

tg_bot/pilot_watch_alert_v1.py now requires for a Telegram strong-WATCH
notification:
- Explicit per-event, same timestamp CONTEXT state COST_PENDING,
  matching symbol and LONG1/SHORT1 direction, no READY or order authority;
- Existing strong-watch/EXTREME_WATCH gate with closed source proof;
- No COST_REJECT for same candidate.
- Entry/context PENDING, rejected, unverified or absent gate -> NO
  strong-WATCH Telegram notification.

This is a **quality gate for notification**, not a newly verified
READY. Actual cost estimate still may be unknown, and any alert is
for manual research only. Valid strong WATCH outcome telemetry continues
to collect even if Telegram message is withheld.

Historically, all five SENT examples above would be filtered under
the updated policy: four ENTRY_PENDING, one COST_REJECT. This
post-hoc explanation is not an independently proven forward improvement.

## New earlier movement research stage (NOT Telegram)

scanner/early_motion_shadow_v1.py:
- Examines latest consecutive 65 CLOSED 1m bars.
- 3m directional return > max(0.45%, 2.3x pre-move realized RMS
  sigma * sqrt(3)), and 3m/5m returns agree.
- Last 3m quote volume >1.8x prior median baseline.
- Last closed candle directionally aligned and body >=30% range.
- Caution against already >2.25% 15m directional move and opposing
  >0.8% 60m move.
- Logs EARLY_CANDIDATE_SHADOW at most once per 30m/symbol/direction
  while still processing each closed candle. Never sends Telegram,
  never READY, never order.
- Thresholds are **research hypotheses**, not calibrated or validated.

## Exploratory historical one-symbol comparison

NEARUSDT stored Nov 10-15: 8640 closed 1m bars.
Two scanning regimes evaluated each 1m with 60m per-direction
episode dedup on the same symbol, each snapshot as-of candle close.

- Early SHADOW: 66 distinct episodes; 15m future directional
  close mean -0.0773%, mean MFE +0.5679%, mean MAE -0.5946%.
  34/66 ended 15m against candidate direction.
- Strong WATCH: 57 distinct episodes; 15m future directional
  close mean -0.1091%, mean MFE +0.6203%, mean MAE -0.5722%.
  35/57 ended against direction after 15m.
- For 33 of the 57 strong-watch episode starts, a same-direction
  early episode existed in the previous 30 minutes. This does NOT
  prove the new signal is uniformly ahead in every event.

Warning: This is **one symbol / one historical period**, not an
out-of-sample profitable performance comparison. Episodes can overlap
across methods, and the early-stage thresholds were chosen after
seeing live late alerts, increasing data-snooping risk. No fills,
fees, funding or actual order book costs are included.
Do not activate early alerts based on this one sample.

## Monitoring

- Continue live 40 coin shared WebSocket with original strong WATCH
  scanner, preserve context and cost logging, record MFE/MAE even when
  a notification is filtered.
- New early events are log-only, no extra Binance REST or WebSocket.
- Monitor count of filtered late alerts, early event reversal metrics,
  compare cross-symbol out-of-time before changing alert policy.
- READY and automated futures trading must remain disabled.
