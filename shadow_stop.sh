#!/usr/bin/env bash
set -euo pipefail

BASE="/home/kasm920/binance1-pro"
cd "$BASE"

echo "[SHADOW] Stopping collectors..."
pkill -f 'orchestration/collectors/okx_oi_shadow_collector.py' || true
pkill -f 'orchestration/collectors/binance_structure_shadow_collector.py' || true
pkill -f 'orchestration/collectors/binance_microstructure_shadow_collector.py' || true
pkill -f 'orchestration/collectors/market_context_shadow_collector.py' || true
sleep 1

echo
if ps -ef | grep -E 'okx_oi_shadow_collector|binance_structure_shadow_collector|binance_microstructure_shadow_collector|market_context_shadow_collector' | grep -v grep; then
  echo "[SHADOW][WARN] One or more collectors may still be running."
  exit 1
else
  echo "[SHADOW] All shadow collectors stopped."
fi
