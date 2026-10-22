#!/usr/bin/env bash
set -euo pipefail

BASE="/home/kasm920/binance1-pro"
PY="/home/kasm920/venv/bin/python"
LOGDIR="$BASE/logs"
PIDDIR="$BASE/run/shadow"

SHARED_SERVICES=(
  binance1-oi-context.service
)

SHORT_SERVICES=(
  binance1-short1-model-shadow.service
  binance1-short1-v30-shadow.service
  binance1-short1-entry-hazard-v44.service
)

SHORT_TIMERS=(
  binance1-short1-model-shadow-finalizer.timer
  binance1-short1-entry-hazard-finalizer.timer
  binance1-short1-entry-hazard-policy-analyzer.timer
  binance1-short1-v30-gate.timer
)

LEGACY_HAZARD_SERVICES=(
  binance1-short1-entry-hazard-v43.service
  binance1-short1-entry-hazard-shadow.service
  binance1-short1-entry-hazard-outcome-ws.service
)

cd "$BASE"
mkdir -p "$LOGDIR" "$PIDDIR"

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

# Strategy/shared collector identity is PID-file first; anchored regex below is
# only a migration fallback for pre-isolation processes.
for pf in \
  "$PIDDIR/shared_near_okx.pid" \
  "$PIDDIR/long1_near_structure.pid" \
  "$PIDDIR/long1_near_microstructure.pid" \
  "$PIDDIR/shared_near_market_context.pid"
do
  stop_pidfile "$pf"
done

echo "[SHADOW] Checking Redis..."
if ! redis-cli ping >/dev/null 2>&1; then
  echo "[SHADOW][ERROR] Redis is not responding."
  exit 1
fi
echo "[SHADOW] Redis PONG"

echo "[SHADOW] Stopping stale/duplicate NEAR collectors..."
pkill -f '[o]kx_oi_shadow_collector.py.*--symbols NEARUSDT' || true
pkill -f '[b]inance_structure_shadow_collector.py.*--symbols NEARUSDT.*--strategy-id LONG1' || true
pkill -f '[b]inance_microstructure_shadow_collector.py.*--symbol NEARUSDT.*--strategy-id LONG1' || true
pkill -f '[m]arket_context_shadow_collector.py.*--symbols NEARUSDT' || true

# Legacy hazard services must never run together with V44.
for u in "${LEGACY_HAZARD_SERVICES[@]}"; do
  systemctl --user stop "$u" >/dev/null 2>&1 || true
done
sleep 1

echo "[SHADOW] Starting shared market-context services..."
for u in "${SHARED_SERVICES[@]}"; do
  systemctl --user start "$u"
done

echo "[SHADOW] Starting NEAR collectors..."
nohup "$PY" -u orchestration/collectors/okx_oi_shadow_collector.py \
  --symbols NEARUSDT --period 4H --poll-sec 60 --ttl-sec 300 \
  > "$LOGDIR/shared_near_okx_oi.log" 2>&1 </dev/null &
echo $! > "$PIDDIR/shared_near_okx.pid"

nohup "$PY" -u orchestration/collectors/binance_structure_shadow_collector.py \
  --symbols NEARUSDT --strategy-id LONG1 --ttl-sec 180 --grace-sec 1.5 \
  > "$LOGDIR/long1_near_structure.log" 2>&1 </dev/null &
echo $! > "$PIDDIR/long1_near_structure.pid"

nohup "$PY" -u orchestration/collectors/binance_microstructure_shadow_collector.py \
  --symbol NEARUSDT --strategy-id LONG1 --ttl-sec 10 --snapshot-sec 1 --telemetry-sec 10 \
  > "$LOGDIR/long1_near_microstructure.log" 2>&1 </dev/null &
echo $! > "$PIDDIR/long1_near_microstructure.pid"

nohup "$PY" -u orchestration/collectors/market_context_shadow_collector.py \
  --symbols NEARUSDT --poll-sec 1 --ttl-sec 180 \
  > "$LOGDIR/shared_near_market_context.log" 2>&1 </dev/null &
echo $! > "$PIDDIR/shared_near_market_context.pid"

echo "[SHADOW] Starting SHORT1 systemd shadow services..."
for u in "${SHORT_SERVICES[@]}"; do
  systemctl --user start "$u"
done

echo "[SHADOW] Starting SHORT1 timers..."
for u in "${SHORT_TIMERS[@]}"; do
  systemctl --user start "$u"
done

sleep 4

echo
echo "[SHADOW] NEAR collectors:"
ps -eo pid,etime,%cpu,%mem,cmd \
| grep -E 'okx_oi_shadow_collector.*NEARUSDT|binance_structure_shadow_collector.*NEARUSDT.*LONG1|binance_microstructure_shadow_collector.*NEARUSDT.*LONG1|market_context_shadow_collector.*NEARUSDT' \
| grep -v grep || true

echo
echo "[SHADOW] Shared services:"
for u in "${SHARED_SERVICES[@]}"; do
  printf '  %-55s %s\n' "$u" "$(systemctl --user is-active "$u" 2>/dev/null || true)"
done
echo "[SHADOW] SHORT1 services:"
for u in "${SHORT_SERVICES[@]}"; do
  printf '  %-55s %s\n' "$u" "$(systemctl --user is-active "$u" 2>/dev/null || true)"
done

echo "[SHADOW] SHORT1 timers:"
for u in "${SHORT_TIMERS[@]}"; do
  printf '  %-55s %s\n' "$u" "$(systemctl --user is-active "$u" 2>/dev/null || true)"
done

echo
echo "[SHADOW] Legacy hazard services (must be inactive):"
for u in "${LEGACY_HAZARD_SERVICES[@]}"; do
  printf '  %-55s %s\n' "$u" "$(systemctl --user is-active "$u" 2>/dev/null || true)"
done

echo
echo "[SHADOW] Recent NEAR status:"
for f in \
  "$LOGDIR/shared_near_okx_oi.log" \
  "$LOGDIR/long1_near_structure.log" \
  "$LOGDIR/long1_near_microstructure.log" \
  "$LOGDIR/shared_near_market_context.log"
do
  echo "--- $(basename "$f") ---"
  tail -2 "$f" 2>/dev/null || true
done

echo
echo "[SHADOW] START COMPLETE"
