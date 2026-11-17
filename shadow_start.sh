#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec ./scripts/binance1_stack_control.sh start
