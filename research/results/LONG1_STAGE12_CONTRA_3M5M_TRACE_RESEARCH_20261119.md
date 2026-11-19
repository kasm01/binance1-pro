# LONG1 Stage12 — Contra-Trend 3m/5m confirmation and trace

19 Kasım 2026. NEARUSDT LONG1. Research only; central Risk Master NO-GO.
No SHORT1, production service, order, .env, or risk guard modifications.

## Actual runtime guard
Original core/long_contra_guard.py snapshot and five_minute_recovered
functions were preserved. Context must be fresh and valid. Contra origin
remains pending until a fresh independent intent, newer closed 3m,
positive 3m return with recovered 15m flow, and favorable consecutive
FULLY CLOSED 5m prices. Old origin cannot authorize reentry. Final
Safety and central Risk Master still have their own veto.

Stage11 default-OFF observer now records contra_trend stage into bounded
telemetry:long1:entry_decision_trace:v1 stream ONLY if
LONG1_ENTRY_DECISION_TRACE_SHADOW_ENABLE=1. Default remains disabled.
The trace includes context as-of status, 3m close timestamp, independent
new-intent proof and actual 5m recovery flag. Full recovery flag can
be true ONLY after the runtime guard confirms fresh intent, as-of
context, and completed 5m recovery. It never grants order authority.
Missing full MODEL candle identity is explicitly marked unknown.
Observer failures cannot change the guard decision.

## Binance archival proxy research
All 103 MODEL LONG time observations were compared with previously
SHA-256 verified Binance 1m closed bars. Grouped UTC 3m structure and
5m consecutive full close recovery were tested under a 30-minute
future observation window, not as an entry signal at origin.

| Retrospective reference | MODEL | Contra proxy at origin | Proxy recovery within 30m | No recovery |
|---|---:|---:|---:|---:|
| LONG_TARGET | 11 | 10 | 10 | 0 |
| LONG_AVOID | 70 | 57 | 29 | 28 |
| UNLABELLED | 21 | 10 | 9 | 1 |
| CONFLICT_NO_TRADE | 1 | 0 | 0 | 0 |

IMPORTANT: reconstructed taker flow and 3m mean/upfrac proxy
are NOT the same as actual historical live shadow market context.
Real new intent lineage, live partial 1m Sniper/Entry confirmation,
whale, and final execution risk were not reproduced; there are
ZERO authenticated new historical trade approvals from this replay.
30m hindsight recovery cannot be applied to earlier trading decisions.
Retrospective wanted/avoid labels are not an order whitelist.
Seven conflicting reference segments remain NO_TRADE.

## Tests
- test_long1_stage12_contra_guard_audit_isolated.py uses real guard,
  isolated Unix-socket Redis and mocked Binance 5m GET. It tests
  stale-origin intent veto, negative 3m/15m veto, failed 5m
  confirmation, later fresh-intent successful Contra gate,
  observer-error immunity and default-OFF zero writes.
- test_long1_entry_decision_shadow_observer_stage11.py
- test_long1_stage8_exec_pending_outcome_isolated.py
- test_long1_stage16_pending_safety_offline.py
- test_stage24_live_guard_long_strict_v1.py

Output: LONG1_STAGE12_103_BINANCE_CLOSED3M5M_CONTRA_PROXY_20261119.json.
Code: replay_long1_contra_3m5m_full_closed_103_v1.py.
The new Stage12 trace is forward-only, default-off and has no Binance
POST or additional network polling.
