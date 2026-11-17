#!/usr/bin/env bash
# Unified lifecycle for both ~/binance1 (SHORT1) and ~/binance1-pro (LONG1).
# Usage: shadow_stop.sh / shadow_start.sh; --check; --dry-run.
set -Eeuo pipefail

MODE="${1:-}"
OPT="${2:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_LONG="$ROOT"
RUN_DIR="$ROOT/run/shadow"
STATE_FILE="$RUN_DIR/enabled_before_stack_stop.txt"
PIDDIR="$ROOT/run/shadow"
PY="$ROOT/venv/bin/python"
LOGDIR="$ROOT/logs"
DRY=0
[[ "$OPT" == "--dry-run" ]] && DRY=1
[[ "$MODE" == "check" ]] && DRY=1
mkdir -p "$RUN_DIR"

# All supported current services; legacy mutually exclusive V43 alternatives
# are STOPPED by stop-all, never blindly started.
CORE_SERVICES=(
  binance1-central-risk-enforce-dry.service
  binance1-long1-native-stop.service
  binance1-long-orch.service
  binance1-long-supervisor.service
  binance1-orch.service
  binance1-supervisor.service
)
SHADOW_SERVICES=(
  binance1-oi-context.service
  binance1-long1-decision-shadow.service
  binance1-short1-model-shadow.service
  binance1-short1-model-shadow-v6.service
  binance1-short1-inj-shadow-signal-bus.service
  binance1-short1-v30-shadow.service
  binance1-short1-entry-hazard-v44.service
)
TIMERS=(
  binance1-central-risk-shadow.timer
  binance1-long-orch-health.timer
  binance1-short-orch-health.timer
  binance1-short1-model-shadow-finalizer.timer
  binance1-short1-model-shadow-v6-finalizer.timer
  binance1-short1-entry-hazard-finalizer.timer
  binance1-short1-entry-hazard-policy-analyzer.timer
  binance1-short1-v30-gate.timer
)
# Collector identities: only match processes belonging to these scripts.
COLLECTOR_PATTERNS=(
  "okx_oi_shadow_collector.py"
  "binance_structure_shadow_collector.py"
  "binance_microstructure_shadow_collector.py"
  "market_context_shadow_collector.py"
)
collector_scripts=(
  orchestration/collectors/okx_oi_shadow_collector.py
  orchestration/collectors/binance_structure_shadow_collector.py
  orchestration/collectors/binance_microstructure_shadow_collector.py
  orchestration/collectors/market_context_shadow_collector.py
)
collector_pids=(shared_near_okx.pid long1_near_structure.pid long1_near_microstructure.pid shared_near_market_context.pid)

log() { printf '[STACK] %s\n' "$*"; }
warn() { printf '[STACK][WARN] %s\n' "$*" >&2; }
err() { printf '[STACK][ERROR] %s\n' "$*" >&2; }
unit_present() { systemctl --user cat "$1" >/dev/null 2>&1; }
unit_state() { systemctl --user is-active "$1" 2>/dev/null || true; }
unit_enabled() { systemctl --user is-enabled "$1" 2>/dev/null || true; }
unit_list() {
  systemctl --user list-unit-files 'binance1-*.service' 'binance1-*.timer' --no-legend --no-pager 2>/dev/null |
    awk '$1 ~ /^binance1-.*\.(service|timer)$/ { print $1 }' | sort -u
}
running_list() {
  systemctl --user list-units --type=service --type=timer --all --no-legend --no-pager 2>/dev/null |
    awk '$1 ~ /^binance1-.*\.(service|timer)$/ && ($3=="active" || $3=="activating" || $3=="deactivating") { print $1 }' | sort -u
}
inspect_collectors() {
  ps -eo pid=,args= | awk '
  /[p]ython/ && /[o]kx_oi_shadow_collector.py|[b]inance_structure_shadow_collector.py|[b]inance_microstructure_shadow_collector.py|[m]arket_context_shadow_collector.py/ {
     if ($0 !~ /awk /) print
  }'
}
stop_collectors() {
  local i pid command
  for i in "${!collector_pids[@]}"; do
    local file="$PIDDIR/${collector_pids[$i]}"
    [[ -f "$file" ]] || continue
    pid="$(cat "$file" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && [[ -r "/proc/$pid/cmdline" ]]; then
      command="$(tr '\0' ' ' <"/proc/$pid/cmdline")"
      if [[ "$command" == *"${collector_scripts[$i]}"* ]]; then
        if (( DRY )); then log "would stop collector PID $pid"; else kill "$pid" 2>/dev/null || true; fi
      else
        warn "PID file $file belongs to another process; not killing"
      fi
    fi
    (( DRY )) || rm -f "$file"
  done
  # Catch orphaned matching collector processes without killing unrelated users.
  local name
  for name in "${COLLECTOR_PATTERNS[@]}"; do
    if (( DRY )); then
      pgrep -af "[${name:0:1}]${name:1}" || true
    else
      pkill -f "[${name:0:1}]${name:1}" 2>/dev/null || true
    fi
  done
}
# Native stop daemon protects exchange-side positions. Never shut it down
# unless signed GET verifies that LONG1 is flat and there are no algo stops.
native_flat_preflight() {
  [[ "${STACK_SKIP_NATIVE_CHECK_FOR_TESTS:-0}" != "1" ]] || { err "test-only override must not bypass production stop preflight"; return 1; }
  [[ -x "$PY" ]] || { err "missing python venv"; return 1; }
  timeout 15 "$PY" - <<'PY'
from scripts.long1_native_stop_guard import stop_context
try:
    pos, orders, _, _ = stop_context()
except Exception as exc:
    print(f"[STACK][ERROR] Binance position/stop read unavailable: {type(exc).__name__}", flush=True)
    raise SystemExit(2)
if pos:
    print("[STACK][ERROR] LONG position detected: keep native stop running; manual position review needed", flush=True)
    raise SystemExit(3)
if orders:
    print("[STACK][ERROR] algo stop orders exist: keep native stop running; review before stopping", flush=True)
    raise SystemExit(4)
print("[STACK] Binance NEARUSDT LONG position flat; no open algo orders", flush=True)
PY
}
stop_unit() {
  local u="$1"
  unit_present "$u" || return 0
  if (( DRY )); then log "would stop $u";return 0; fi
  if ! systemctl --user stop "$u"; then warn "stop failed for $u"; return 1; fi
}
start_unit() {
  local u="$1"
  if ! unit_present "$u"; then warn "unit not installed: $u";return 0; fi
  if (( DRY )); then log "would start $u";return 0; fi
  if ! systemctl --user start "$u"; then warn "start failed for $u";return 1; fi
}

case "$MODE" in
  stop)
    # Prevent enabled restart-on-boot for these units; restore original enabled
    # states after next successful start. Repeated stops keep original snapshot.
    if [[ ! -s "$STATE_FILE" ]]; then
      : > "$STATE_FILE"
      while IFS= read -r u; do
        [[ "$(unit_enabled "$u")" == "enabled" ]] && printf '%s\n' "$u" >> "$STATE_FILE" || true
      done < <(unit_list)
    fi
    log "Stopping timers first, then all installed binance1 services."
    errors=0
    # Do not DISABLE native stop's reboot protection until Binance confirms flat.
    # Other services can still shut down if this check fails.
    native_safe=1
    if [[ "$(unit_state binance1-long1-native-stop.service)" == "active" ]] ||
       [[ "$(unit_enabled binance1-long1-native-stop.service)" == "enabled" ]]; then
      if ! native_flat_preflight; then native_safe=0; errors=1;fi
    fi
    # Disable restart-on-boot for enabled binance1 units; no mask or touching Redis.
    while IFS= read -r u; do
      if [[ "$u" == "binance1-long1-native-stop.service" && "$native_safe" != "1" ]]; then
        continue
      fi
      [[ "$(unit_enabled "$u")" == "enabled" ]] && systemctl --user disable "$u" >/dev/null 2>&1 || true
    done < <(unit_list)
    # Native-stop stays active through stop of all engines.
    while IFS= read -r u; do
      [[ "$u" == "binance1-long1-native-stop.service" ]] && continue
      stop_unit "$u" || errors=1
    done < <( (unit_list; running_list) | sort -u | awk '/\.timer$/ { print }')
    # Supervisors first; stop orchestration and all shadow/other workers.
    for u in binance1-long-supervisor.service binance1-supervisor.service; do
      stop_unit "$u" || errors=1
    done
    for u in binance1-long-orch.service binance1-orch.service; do
      stop_unit "$u" || errors=1
    done
    while IFS= read -r u; do
      case "$u" in
        binance1-long1-native-stop.service|binance1-long-supervisor.service|binance1-supervisor.service|binance1-long-orch.service|binance1-orch.service|*.timer) continue ;;
      esac
      stop_unit "$u" || errors=1
    done < <( (unit_list; running_list) | sort -u)
    stop_collectors
    # The stop daemon is last. If Binance is not provably flat, leave safety
    # running and return non-zero; do not claim "all stopped".
    if [[ "$(unit_state binance1-long1-native-stop.service)" == "active" ]]; then
      if [[ "$native_safe" == "1" ]] && native_flat_preflight; then
        stop_unit binance1-long1-native-stop.service || errors=1
      else
        errors=1
        warn "Native stop deliberately left active and enabled to preserve position protection."
      fi
    fi
    sleep 1
    if [[ -n "$(running_list)" ]]; then
      warn "Still active: $(running_list | tr '\n' ' ')"
      errors=1
    fi
    if [[ -n "$(inspect_collectors)" ]]; then
      warn "Collector processes remain; inspect manually."
      errors=1
    fi
    if (( errors )); then err "STOP INCOMPLETE (protective guard or failures).";exit 1;fi
    log "ALL discovered binance1 user services/timers STOPPED (Redis service is intentionally separate)."
    ;;
  start)
    if (( DRY )); then
      log "DRY-RUN: no processes started, no Redis writes, no systemd changes."
      for u in "${CORE_SERVICES[@]}" "${SHADOW_SERVICES[@]}" "${TIMERS[@]}"; do
        if unit_present "$u"; then
          log "would start $u"
        else
          warn "missing unit: $u"
        fi
      done
      log "would start the 4 original NEAR collectors if not already running."
      exit 0
    fi
    log "Starting both stacks: SHORT1 ~/binance1 (dry-run as configured) and LONG1 ~/binance1-pro (may be LIVE)."
    log "No strategy/risk parameter changed. Launching risk and exchange stop first."
    if ! redis-cli ping >/dev/null 2>&1; then err "Redis unavailable; aborting start.";exit 1;fi
    errors=0
    for u in binance1-central-risk-enforce-dry.service binance1-long1-native-stop.service; do
      start_unit "$u" || errors=1
    done
    if (( errors )); then err "Central risk or native stop failed, NOT starting trading engines";exit 1;fi
    for u in "${SHADOW_SERVICES[@]}"; do start_unit "$u" || errors=1; done
    mkdir -p "$LOGDIR" "$PIDDIR"
    # Only start missing collector processes, avoid duplicate external WS/API.
    if ! pgrep -f '[o]kx_oi_shadow_collector.py.*NEARUSDT' >/dev/null; then
      nohup "$PY" -u orchestration/collectors/okx_oi_shadow_collector.py --symbols NEARUSDT --period 4H --poll-sec 60 --ttl-sec 300 >"$LOGDIR/shared_near_okx_oi.log" 2>&1 </dev/null &
      echo $! >"$PIDDIR/shared_near_okx.pid"
    fi
    if ! pgrep -f '[b]inance_structure_shadow_collector.py.*NEARUSDT' >/dev/null; then
      nohup "$PY" -u orchestration/collectors/binance_structure_shadow_collector.py --symbols NEARUSDT --strategy-id LONG1 --ttl-sec 180 --grace-sec 1.5 >"$LOGDIR/long1_near_structure.log" 2>&1 </dev/null &
      echo $! >"$PIDDIR/long1_near_structure.pid"
    fi
    if ! pgrep -f '[b]inance_microstructure_shadow_collector.py.*NEARUSDT' >/dev/null; then
      nohup "$PY" -u orchestration/collectors/binance_microstructure_shadow_collector.py --symbol NEARUSDT --strategy-id LONG1 --ttl-sec 10 --snapshot-sec 1 --telemetry-sec 10 >"$LOGDIR/long1_near_microstructure.log" 2>&1 </dev/null &
      echo $! >"$PIDDIR/long1_near_microstructure.pid"
    fi
    if ! pgrep -f '[m]arket_context_shadow_collector.py.*NEARUSDT' >/dev/null; then
      nohup "$PY" -u orchestration/collectors/market_context_shadow_collector.py --symbols NEARUSDT --poll-sec 1 --ttl-sec 180 >"$LOGDIR/shared_near_market_context.log" 2>&1 </dev/null &
      echo $! >"$PIDDIR/shared_near_market_context.pid"
    fi
    # Start orchestration before supervisors. Legacy is SHORT1, long is LONG1.
    if (( errors )); then err "One or more supporting services failed; trading engines NOT started.";exit 1;fi
    for u in binance1-orch.service binance1-long-orch.service; do start_unit "$u" || errors=1;done
    if (( errors )); then err "Orchestration failure; supervisors NOT started.";exit 1;fi
    for u in binance1-supervisor.service binance1-long-supervisor.service; do start_unit "$u" || errors=1;done
    if (( errors )); then err "Supervisor failed; timers NOT enabled";exit 1;fi
    for u in "${TIMERS[@]}"; do start_unit "$u" || errors=1; done
    if [[ -f "$STATE_FILE" ]]; then
      while IFS= read -r u; do
        [[ -n "$u" ]] && systemctl --user enable "$u" >/dev/null 2>&1 || warn "Could not re-enable $u"
      done < "$STATE_FILE"
      (( errors )) || rm -f "$STATE_FILE"
    fi
    sleep 2
    for u in "${CORE_SERVICES[@]}" "${SHADOW_SERVICES[@]}"; do
      printf '[STACK] %-58s %s\n' "$u" "$(unit_state "$u")"
    done
    # Confirm managed persistent services and timers, not just return codes.
    for u in "${CORE_SERVICES[@]}" "${SHADOW_SERVICES[@]}" "${TIMERS[@]}"; do
      state="$(unit_state "$u")"
      if [[ "$state" != "active" ]]; then
        warn "started unit not ACTIVE: $u (state=$state)"
        errors=1
      fi
    done
    if (( errors )); then err "START INCOMPLETE, inspect services";exit 1;fi
    log "START sequence completed. Use ./shadow_stop.sh to stop both stacks."
    ;;
  check)
    log "Running binance1 services and timers:"
    running_list | sed 's/^/  /'
    log "Active collectors:"
    inspect_collectors || true
    log "Enabled binance1 service/timer units:"
    while IFS= read -r u; do
      [[ "$(unit_enabled "$u")" == "enabled" ]] && printf '  %s\n' "$u"
    done < <(unit_list)
    true  # Empty or fully disabled stack is a SUCCESSFUL status inspection.
    ;;
  *)
    echo "Usage: $(basename "$0") {start|stop|check}" >&2
    exit 2
    ;;
esac
