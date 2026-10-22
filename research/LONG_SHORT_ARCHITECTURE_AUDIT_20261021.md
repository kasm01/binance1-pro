# LONG1 / SHORT1 Architecture Audit — 2026-10-21

## Target architecture
MODEL -> SIGNAL NORMALIZATION -> MARKET CONTEXT -> MODEL SCORE GATE -> SNIPER -> ENTRY CONFIRMATION -> PENDING REVALIDATION -> EXECUTION RISK -> FINAL SAFETY -> ORDER -> POSITION LIFECYCLE -> TELEMETRY / OUTCOME FEEDBACK

Global portfolio policy: one bot = one coin = one side = at most one open position. No same-symbol scale-in / averaging-down. Cross-bot coordination belongs to CENTRAL RISK MASTER.

## SHORT1 — current advanced research/shadow stack
- Coin: INJUSDT, SHORT, coin-specific 3m economic model; 1m confirmation/lifecycle context.
- Single position; no L2/L3 averaging.
- Hard score ~0.540; contextual soft band 0.530-0.540 only under validated SHORT-build context in research.
- Entry confirmation: previous completed 1m green + current 1m red reversal >=0.01%.
- 60m taker money-flow exhaustion: flow60 <= -0.20 blocks NEW SHORT only.
- Entry-time 15m price/flow/OI context available; confirmed directional build can reduce size x0.50.
- Stop-only same-symbol re-entry lock: 15m.
- Dynamic stop and catastrophic stop research refined.
- Entry Hazard V44 captures 5s/20s/30s aggressive flow plus order-book depth/microprice/absorption; currently telemetry-only in live shadow service.
- V49B research recovery: REDUCED -> RECOVERY(0.70) -> NORMAL after 2 successful RECOVERY trades; recovery stop -> REDUCED.
- V49B state machine has now been ported to the non-routing SHORT lifecycle shadow and self-tested. Trading services remain OFF.

## LONG1 — pre-audit state
- Coin: NEARUSDT, LONG.
- Base threshold 0.525; dynamic recovery floor 0.5114 using ATR-rank + candle recovery structure.
- Sniper / entry confirmation / pending revalidation / execution risk / final safety are present.
- LONG market-context resolver carries candle structure, ATR, spread, confidence, micro/liquidity score and whale context.
- It did NOT contain the SHORT-style causal taker money-flow exhaustion authority or entry-time 15m price/flow/OI sizing contract.
- Runtime env had scale-in enabled with max 3 layers.

## Critical scale-in finding
Historical final-candidate LONG entries contain 1,009 layer-2/3 additions across six execution seeds.
- 958 / 1,009 = 94.95% of additions occurred while the existing LONG was underwater.
- L2 median pre-add PnL approximately -0.62%.
- L3 median pre-add PnL approximately -1.24%.
- Worst additions occurred near -3.2% open-position price PnL.
Therefore the old LONG layer engine was primarily averaging-down, inconsistent with the agreed SHORT/global architecture.

## Controlled LONG A/B — 1 year, six execution seeds
| Variant | Mean return | PF | Mean DD | Worst DD | Mean entries |
|---|---:|---:|---:|---:|---:|
| Old locked 3-layer | +87.41% | 1.4277 | -26.62% | -28.39% | 655.3 |
| Single position | +29.69% | 1.1853 | -21.34% | -25.51% | 431.8 |
| Single + flow60 >= +0.10 veto | +29.70% | 1.1875 | -20.35% | -23.81% | 424.8 |
| Single + flow60 >= +0.15 veto | +31.95% | 1.1985 | -20.10% | -23.37% | 428.8 |
| Single + flow60 >= +0.20 veto | +32.67% | 1.2024 | -20.35% | -24.33% | 430.8 |
| Single + flow60 >= +0.25 veto | +29.69% | 1.1853 | -21.34% | -25.51% | 431.8 |
| Single + flow60 + mandatory soft flow15>0 | +2.11% | 1.0401 | -16.65% | -18.45% | 88.5 |

Interpretation:
- Removing averaging-down materially reduces historical return but also improves drawdown and aligns the 8-bot architecture.
- Symmetric LONG taker-flow exhaustion is useful. +0.15 to +0.20 is the candidate region.
- +0.20 is the clean symmetric counterpart to SHORT -0.20 and gives the best mean return among tested single-position variants.
- Requiring positive 15m flow on every low-score LONG is over-restrictive and rejected.

## Runtime synchronization performed
LONG repo `.env` now uses:
- LONG_SCALE_IN_ENABLE=0
- LONG_MAX_ENTRY_LAYERS=1
- FIXED_ROI_TP_PCT=0.0400
- FIXED_ROI_TP_GIVEBACK=0.0024
- LONG_DYNAMIC_STOP_CONFIRM_SEC=30
- LONG_DYNAMIC_STOP_CATASTROPHIC_PCT=0.035

This removes same-symbol averaging and aligns TP/stop timing with the locked LONG research lifecycle. A timestamped env backup was created before changes.

SHORT non-routing lifecycle shadow now supports V49B:
- SHORT_RECOVERY_POSITION_EQUITY_PCT=0.70
- SHORT_RECOVERY_WINS_REQUIRED=2
- DD recovery threshold remains 4%.
- Service restarted successfully; routing remains OFF and production orch/supervisor remain inactive.

## Remaining asymmetries to resolve before LONG1 + SHORT1 production integration
1. LONG money-flow exhaustion is validated in research but not yet wired into the LONG runtime MARKET CONTEXT path. Implement first as shadow/telemetry, then promote only after parity checks.
2. LONG lacks a SHORT-V44-equivalent 5s/20s/30s aggressive-flow + order-book hazard shadow. Build a directional mirror for LONG rather than sharing SHORT signs blindly.
3. SHORT V44 is still telemetry-only; V47/V49 backtests used hazard logic, but routing promotion still requires forward shadow evidence.
4. OI risk sizing should become a shared Central Risk Master authority, not duplicated separately inside LONG and SHORT engines.
5. Existing `core/risk_manager.py` is a legacy daily-loss/open-count manager; it is not yet the planned portfolio Central Risk Master with NORMAL/RECOVERY/REDUCED state, gross/net exposure and cross-bot coordination.
6. The old LONG1 locked result (+87.41%) must not be used as the expected result of the new single-position architecture. The current single-position + flow20 research reference is approximately +32.67% before further LONG-side context improvements.

## Next controlled step
Build LONG1 money-flow/context shadow using already available Binance kline taker-buy quote volume (no extra REST request required for 15m/60m flow). Mirror SHORT exhaustion directionally: NEW LONG veto candidate when completed 60m taker-flow >= +0.20. Keep existing position lifecycle untouched. Collect outcome telemetry, then test entry-time OI multiplier and LONG hazard revalidation as separate A/B layers.

## LONG1 context parity V1 — implemented 2026-10-21

Status: SHADOW / TELEMETRY ONLY. No production routing authority.

### Money flow
- Existing Binance structure collector now computes completed-bar taker flow from the same existing 3m kline response.
- 15m = last 5 completed 3m bars; 60m = last 20 completed 3m bars.
- Formula: `(2 * taker_buy_quote - quote_volume) / quote_volume` aggregated over the window.
- Live formula parity self-test: zero numerical error.
- LONG exhaustion research candidate: `flow60 >= +0.20` -> shadow NEW-LONG veto candidate only; never lifecycle close.
- No additional REST request was added for flow.

### Entry-time context
- Canonical `entry_market_context.v1` contract ported from SHORT.
- Existing 1m ENTRY CONFIRMATION fetch expands payload from 2 to 20 rows, request count unchanged.
- Current/forming confirmation minute is excluded causally.
- Produces completed 15m price return + completed 15m taker flow.
- Central Binance USD-M 5m OI collector added for NEAR: one `openInterestHist(limit=5)` public request every 5 minutes (288/day).
- Latest + previous OI snapshots are stored so exact 5m boundary entries use strictly-prior fallback without an extra request.
- Entry-time regime remains telemetry-only.

### LONG model shadow
- Existing structure collector reuses the same completed 3m response for NEAR model scoring.
- Direct joblib SGD inference uses the exact production `features.fe_labels.build_features` contract.
- Direct score matched HybridModel SGD-only output to floating precision while avoiding TensorFlow/LSTM runtime overhead.
- Candidate stream: `shadow:telemetry:long1:model_candidate_v1`.
- Candidate requires model gate pass and no `flow60 >= +0.20` exhaustion.
- Mid-cycle startup cannot emit an old 3m close as a fresh candidate.
- Persistent completed-close dedupe prevents duplicate candidate emission after restart.

### LONG hazard mirror
- Reuses the existing NEAR trade/depth/bookTicker WebSocket; no new WS or REST connection.
- 20s shadow hazard candidate: LONG momentum confirmed + `flow20 >= +0.60` + `flow20-flow5 >= +0.30`.
- 30s revalidation: continued upward price -> READY_AFTER_REVALIDATION; failure/pullback -> REJECT_CANDIDATE.
- Order-book L1/depth5/depth20/microprice/spread snapshots and deltas are telemetry features only.
- Outcome stream records 1m/3m/5m return, MFE and MAE using the same live trade WS, no extra request.
- Streams:
  - `shadow:telemetry:long1:entry_hazard_v1`
  - `shadow:telemetry:long1:entry_hazard_v1_outcomes`

### Cost / resources
- NEAR Binance OI collector: ~33 MB RSS, 1 public request / 5m.
- Existing microstructure collector with hazard logic: ~37 MB RSS, no additional market-data connection.
- Structure collector with direct model inference: ~197 MB RSS.
- All five NEAR shadow collectors total ~322 MB RSS on a 3.9 GB VM; ~2.4 GB memory remained available during validation.
- No VM resize is currently required.

### Validation / safety
- Python compile: PASS.
- `git diff --check`: PASS.
- Dynamic model-gate exact parity self-test: PASS.
- 15m/60m flow formula self-test: PASS.
- causal `entry_market_context.v1` live smoke: PASS.
- LONG hazard 20s/30s state-machine self-test: PASS.
- LONG hazard 1m/3m/5m outcome-label self-test: PASS.
- Current live score at final check was below gate, so model/hazard streams correctly remained empty rather than fabricating a candidate.
- Production `binance1-orch.service` and `binance1-supervisor.service`: inactive.
- `DRY_RUN=1`, `ARMED=0`, `LIVE_KILL_SWITCH=1`.

### Promotion rule
Do not promote LONG flow/OI/hazard to routing based only on implementation correctness. Require forward model-candidate samples and fee-aware outcome separation first. In particular, 5m historical NEAR OI coverage is only ~1,439 rows (~5 days), insufficient for a full-year current-architecture OI sizing claim.

## Superseding causal correction + Central Risk V1 — 2026-10-21

### LONG replay causality correction
A research replay defect was found after the first architecture audit: a position opened mid-1m candle could have that same candle lifecycle sampled again from progress 0.0. This produced 0-1 impossible `exit < entry` trade per seed and affected some same-minute path outcomes. The first entry candle is now sampled only from the actual entry progress onward.

Corrected six-seed 1y comparison:
- 3-layer causal reference: +95.48% mean return, PF 1.4731, mean DD -26.62%, worst DD -28.39%.
- single-position causal: +30.85%, PF 1.1954, mean DD -21.64%, worst DD -25.08%.
- single + flow60 >= +0.15 exhaustion: +33.88%, PF 1.2130, mean DD -20.42%, worst DD -22.93%.
- single + flow60 >= +0.20 exhaustion: +32.69%, PF 1.2055, mean DD -20.63%, worst DD -23.96%.

Superseding decision: LONG1 uses +0.15 as the research exhaustion candidate, not +0.20. Runtime/shadow env authority is `LONG_MONEY_FLOW_EXHAUSTION_60M=0.15`. Exact causal position streams contain zero `exit < entry` rows across all six seeds.

### Central Risk Master V1
Created `orchestration/risk/central_risk_master.py` as a pure research/shadow portfolio-risk core. It is not wired into executor/order routing.

Contract:
- one position per strategy slot,
- NORMAL / RECOVERY / REDUCED shared portfolio state,
- recovery-success confirmation,
- one market-context multiplier application,
- gross/long/short/absolute-net/symbol exposure headroom,
- fail-safe `production_ready=False` until all exposure caps are explicitly configured.

Clean recursive shared-equity replay uses corrected LONG1 single-position + flow15 exhaustion candidate and SHORT1 V49B templates with 50/50 baseline strategy budgets. Individual engine DD sizing is not double-applied; central state owns replay state sizing.

Two-engine gross-cap research: gross 1.00 currently leads 0.85/0.90/0.95/0.75 on the tested return/DD balance. Do not copy this cap to eight engines.

Central state grid shows that SHORT-isolated 0.50 REDUCED / 0.70 RECOVERY is too conservative for the shared portfolio. Candidate regions include 0.60/0.75 and 0.70/0.80, but no state multiplier is locked because the current recursive replay updates central DD from realized equity only.

Required next step: Central Risk MTM Replay V2 using concurrent open-position mark-to-market equity. Production integration remains blocked until MTM V2 validates gross/net caps and state transitions.
