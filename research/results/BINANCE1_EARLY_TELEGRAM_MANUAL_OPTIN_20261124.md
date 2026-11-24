# BINANCE1 early manual WATCH Telegram opt-in — 2026-11-24

## User-authorized scope

User explicitly requested early alerts because the system is notification-only
and NEVER automatically opens positions. Early alerts are now enabled in the
already-running standalone public-data 40-coin WebSocket service.

Existing LONG1/SHORT1 strong WATCH Telegram policy is unchanged.
New EARLY monitoring may originate from any of LONG1..4 and SHORT1..4,
depending on the current deterministic 10-symbol allocation of the common
40-symbol universe and the candidate direction.

## Telegram message and constraints

Message is explicitly marked:

- BINANCE1 / ERKEN İZLEME with the assigned strategy ID and symbol
- Direction LONG/SHORT, last completed 1m price, recent 3m/5m/15m movement
- Recent 3m relative quote volume and directional taker pressure
- Turkish local time, explicit high reversal risk warning
- GİRİŞ ONAYI / READY DEĞİL, manual check, no Binance auto order,
  account fee or target/stop verification

Automatic READY and exchange order authority are never enabled.

## Eligibility and failure safety

- Early candidate derived from a single completed 1m bar:
  EARLY_CANDIDATE_SHADOW with matching symbol, direction and timestamp.
- Taker-flow state may be FLOW_SUPPORTIVE or FLOW_MIXED.
  FLOW_OPPOSING, FLOW_EXHAUSTION_CAUTION, FLOW_UNVERIFIED are blocked.
  This is a safety-oriented research choice, not a calibrated edge.
- Candidate must be assigned to the bot ID corresponding to direction
  within 40-symbol 8-module universe.
- No stale, partial or >30sec-from-close input; no source time drift >2m.
- Explicit opt-in: TELEGRAM_EARLY_WATCH_ENABLED=1 AND both existing
  Telegram transport enable flags must be 1.
- Transport sends only to the pre-existing allowlisted Telegram Chat ID,
  with API success response verification. No token in repo or reports.
- Rate bound: **maximum six early notifications per rolling hour**
  across all 40 coins, minimum **three minutes globally** between
  early messages, and **two hours per symbol+direction**.
- Local early-only persistent state:
  run/signal_center/early_telegram_cooldown.json, 0600 file / 0700 dir,
  independent of standard strong-WATCH cooldown file.
  Corrupt state fails closed. No resend after restart of previously
  confirmed messages; failed sends are not counted.
- No new Binance REST/WebSocket data feed for early Telegram.
  Network activity is an occasional authorized Telegram send only.
- The early 5/15/30/60m MFE/MAE shadow logging is unchanged.

## Deployment verification

Systemd user drop-in:
~/.config/systemd/user/binance1-manual-watch.service.d/telegram-pilot.conf
has three flags TELEGRAM_SIGNAL_CENTER_ENABLED=1,
TELEGRAM_SIGNAL_CENTER_SEND_ENABLED=1,
TELEGRAM_EARLY_WATCH_ENABLED=1.

The user unit binance1-manual-watch.service was manually restarted
and verified ACTIVE, 40/40 valid coins, no unplanned systemd restarts.
Legacy binance1-supervisor/orch and long-supervisor/orch were inactive.
order_authorized=false, READY signals=0.

Unit still is not enabled for VM reboot auto-start, by earlier policy.
Manual WATCH strong alerts continue with their existing quality checks.

## Evidence and remaining limits

- 7 new early Telegram unit tests: gating, message explicit
  not-READY text, allowlist/assignment, 6/h cap, 2h cooldown,
  private persisted restart dedup, corrupt-file block,
  failed-send no false delivery, SHORT2 routing.
- Full 70-unit regression suite PASS, Stage22 exact intent and Stage24
  strict order guards PASS, no credentials committed.
- Prior multi-coin sample showed that early-move alerts reverse often.
  That is why Telegram messages explicitly warn and remain advisory.
- New real EARLY Telegram delivery has NOT yet been API-confirmed
  under the enabled deployment. Next qualifying event will be logged
  EARLY_WATCH_TELEGRAM with SENT or delivery error; no manufactured
  fake-market signal was sent just to generate a confirmation.

## Disable just early Telegram (keep strong WATCH)

Set Environment=TELEGRAM_EARLY_WATCH_ENABLED=0 in the user systemd
drop-in, daemon-reload and restart binance1-manual-watch.service via
scripts/manual_watch_control.sh restart. Never run shadow_start.sh,
which belongs to the legacy trading stack.
