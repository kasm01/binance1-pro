#!/usr/bin/env bash
set -euo pipefail

BASE="/home/kasm920/binance1-pro"
PIDDIR="$BASE/run/shadow"
cd "$BASE"

SHARED_SERVICES=(
  binance1-oi-context.service
)

SHORT_SERVICES=(
  binance1-short1-model-shadow.service
  binance1-short1-v30-shadow.service
  binance1-short1-entry-hazard-v44.service
  binance1-short1-entry-hazard-v43.service
  binance1-short1-entry-hazard-shadow.service
  binance1-short1-entry-hazard-outcome-ws.service
)

SHORT_TIMERS=(
  binance1-short1-model-shadow-finalizer.timer
  binance1-short1-entry-hazard-finalizer.timer
  binance1-short1-entry-hazard-policy-analyzer.timer
  binance1-short1-v30-gate.timer
)

SHORT_ONESHOTS=(
  binance1-short1-model-shadow-finalizer.service
  binance1-short1-entry-hazard-finalizer.service
  binance1-short1-entry-hazard-policy-analyzer.service
  binance1-short1-v30-gate.service
)

stop_pidfile() {
  local file="$1"
  if [[ -f "$file" ]]; then
    local pid
    pid="$(cat "$file" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$file"
  fi
}

echo "[SHADOW] Stopping SHORT1 timers first..."
for u in "${SHORT_TIMERS[@]}"; do
  systemctl --user stop "$u" >/dev/null 2>&1 || true
done

# If a timer-triggered oneshot is currently running, stop it too.
for u in "${SHORT_ONESHOTS[@]}"; do
  systemctl --user stop "$u" >/dev/null 2>&1 || true
done

echo "[SHADOW] Stopping SHORT1 shadow services..."
for u in "${SHORT_SERVICES[@]}"; do
  systemctl --user stop "$u" >/dev/null 2>&1 || true
done

echo "[SHADOW] Stopping NEAR collectors..."
for pf in \
  "$PIDDIR/shared_near_okx.pid" \
  "$PIDDIR/long1_near_structure.pid" \
  "$PIDDIR/long1_near_microstructure.pid" \
  "$PIDDIR/shared_near_market_context.pid"
do
  stop_pidfile "$pf"
done
pkill -f '[o]kx_oi_shadow_collector.py.*--symbols NEARUSDT' || true
pkill -f '[b]inance_structure_shadow_collector.py.*--symbols NEARUSDT.*--strategy-id LONG1' || true
pkill -f '[b]inance_microstructure_shadow_collector.py.*--symbol NEARUSDT.*--strategy-id LONG1' || true
pkill -f '[m]arket_context_shadow_collector.py.*--symbols NEARUSDT' || true
sleep 2

echo
echo "[SHADOW] Verification:"
FAIL=0

if ps -eo cmd | grep -E 'okx_oi_shadow_collector.*NEARUSDT|binance_structure_shadow_collector.*NEARUSDT.*LONG1|binance_microstructure_shadow_collector.*NEARUSDT.*LONG1|market_context_shadow_collector.*NEARUSDT' | grep -v grep >/dev/null; then
  echo "[SHADOW][WARN] One or more NEAR collectors are still running."
  ps -eo pid,etime,%cpu,%mem,cmd | grep -E 'okx_oi_shadow_collector.*NEARUSDT|binance_structure_shadow_collector.*NEARUSDT.*LONG1|binance_microstructure_shadow_collector.*NEARUSDT.*LONG1|market_context_shadow_collector.*NEARUSDT' | grep -v grep || true
  FAIL=1
else
  echo "[SHADOW][OK] NEAR collectors stopped."
fi

echo "[SHADOW] Stopping shared services last..."
for u in "${SHARED_SERVICES[@]}"; do
  systemctl --user stop "$u" >/dev/null 2>&1 || true
done

for u in "${SHORT_SERVICES[@]}" "${SHORT_TIMERS[@]}" "${SHORT_ONESHOTS[@]}" "${SHARED_SERVICES[@]}"; do
  state="$(systemctl --user is-active "$u" 2>/dev/null || true)"
  if [[ "$state" == "active" || "$state" == "activating" ]]; then
    echo "[SHADOW][WARN] $u is still $state"
    FAIL=1
  fi
done

if pgrep -af '/home/kasm920/binance1/.+(short_economic_shadow|oi_context_collector|short1_v30_lifecycle_shadow|short1_entry_hazard)' >/dev/null 2>&1; then
  echo "[SHADOW][WARN] A binance1 SHORT1 shadow process may still be running:"
  pgrep -af '/home/kasm920/binance1/.+(short_economic_shadow|oi_context_collector|short1_v30_lifecycle_shadow|short1_entry_hazard)' || true
  FAIL=1
else
  echo "[SHADOW][OK] SHORT1 shadow processes stopped."
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "[SHADOW][ERROR] Shutdown verification failed. Do NOT stop the VM until reviewed."
  exit 1
fi

echo "[SHADOW] ALL SHADOW SERVICES/COLLECTORS STOPPED. Safe to stop the VM."
