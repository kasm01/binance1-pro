#!/usr/bin/env bash
# Manual-only, public-data watcher. Never invokes shadow_start.sh / trade orders.
set -Eeuo pipefail
UNIT=binance1-manual-watch.service
MODE="${1:-status}"
case "$MODE" in
  status)
    printf '[MANUAL WATCH] unit=%s\n' "$UNIT"
    systemctl --user show "$UNIT" -p ActiveState -p SubState -p MainPID -p NRestarts -p MemoryCurrent
    printf '[MANUAL WATCH] bot trade services remain independent; this command does not start them\n'
    ;;
  start)
    for unsafe in binance1-supervisor.service binance1-long-supervisor.service binance1-orch.service binance1-long-orch.service; do
      if [[ "$(systemctl --user is-active "$unsafe" 2>/dev/null || true)" == active ]]; then
        printf '[BLOCK] Old trade service active: %s. Manual watcher start aborted.\n' "$unsafe" >&2
        exit 2
      fi
    done
    systemctl --user start "$UNIT"
    systemctl --user is-active "$UNIT"
    ;;
  stop)
    systemctl --user stop "$UNIT"
    printf '[MANUAL WATCH] stopped; no Binance orders\n'
    ;;
  restart)
    "$0" stop
    "$0" start
    ;;
  *)
    printf 'Usage: ./scripts/manual_watch_control.sh {status|start|stop|restart}\n' >&2
    exit 2
    ;;
esac
