#!/usr/bin/env bash
set -euo pipefail

BASE="/home/kasm920/binance1-pro"
PY="/home/kasm920/venv/bin/python"
LOGDIR="$BASE/logs"

cd "$BASE"
mkdir -p "$LOGDIR"

echo "[SHADOW] Checking Redis..."
if ! redis-cli ping >/dev/null 2>&1; then
  echo "[SHADOW][ERROR] Redis is not responding."
  exit 1
fi

echo "[SHADOW] Stopping stale duplicate collectors..."
pkill -f 'orchestration/collectors/okx_oi_shadow_collector.py' || true
pkill -f 'orchestration/collectors/binance_structure_shadow_collector.py' || true
pkill -f 'orchestration/collectors/binance_microstructure_shadow_collector.py' || true
pkill -f 'orchestration/collectors/market_context_shadow_collector.py' || true
sleep 1

echo "[SHADOW] Starting OKX OI..."
nohup "$PY" -u orchestration/collectors/okx_oi_shadow_collector.py \
  --symbols NEARUSDT \
  --period 4H \
  --poll-sec 60 \
  --ttl-sec 300 \
  > "$LOGDIR/okx_oi_shadow.log" 2>&1 </dev/null &

echo "[SHADOW] Starting Binance structure..."
nohup "$PY" -u orchestration/collectors/binance_structure_shadow_collector.py \
  --symbols NEARUSDT \
  --ttl-sec 180 \
  --grace-sec 1.5 \
  > "$LOGDIR/binance_structure_shadow.log" 2>&1 </dev/null &

echo "[SHADOW] Starting Binance microstructure..."
nohup "$PY" -u orchestration/collectors/binance_microstructure_shadow_collector.py \
  --symbol NEARUSDT \
  --ttl-sec 10 \
  --snapshot-sec 1 \
  --telemetry-sec 10 \
  > "$LOGDIR/binance_microstructure_shadow.log" 2>&1 </dev/null &

echo "[SHADOW] Starting combined market context..."
nohup "$PY" -u orchestration/collectors/market_context_shadow_collector.py \
  --symbols NEARUSDT \
  --poll-sec 1 \
  --ttl-sec 180 \
  > "$LOGDIR/market_context_shadow.log" 2>&1 </dev/null &

sleep 4

echo
echo "[SHADOW] Running collectors:"
ps -eo pid,etime,%cpu,%mem,cmd \
| grep -E 'okx_oi_shadow_collector|binance_structure_shadow_collector|binance_microstructure_shadow_collector|market_context_shadow_collector' \
| grep -v grep || true

echo
echo "[SHADOW] Recent status:"
for f in \
  "$LOGDIR/okx_oi_shadow.log" \
  "$LOGDIR/binance_structure_shadow.log" \
  "$LOGDIR/binance_microstructure_shadow.log" \
  "$LOGDIR/market_context_shadow.log"
do
  echo "--- $(basename "$f") ---"
  tail -2 "$f" 2>/dev/null || true
done
