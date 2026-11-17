"""Offline prototype orchestrator for strictly read-only Binance account view.

Inject adapters; no default network functions; never derives authority from
snapshot freshness or incomplete open order views.
"""
from __future__ import annotations
from typing import Any,Callable
from research.staging.stage18_shared_portfolio_snapshot_v1 import inspect_snapshot,unknown,SYMBOLS

def capture(*, read_account:Callable[[],Any],
            read_positions:Callable[[str],Any],
            read_open_orders:Callable[[str],Any],
            read_open_algos:Callable[[str],Any],
            clock_ms:Callable[[],int], max_capture_ms:int=5000):
    try:
        start=clock_ms()
        if type(start) is not int or start<=0:
            return unknown("capture_clock_invalid")
        account=read_account()
        pos,orders,algos={},{},{}
        for symbol in SYMBOLS:
            pos[symbol]=read_positions(symbol)
            orders[symbol]=read_open_orders(symbol)
            algos[symbol]=read_open_algos(symbol)
        finished=clock_ms()
        if type(finished) is not int or finished<start:
            return unknown("capture_clock_invalid")
        if finished-start>max_capture_ms:
            return unknown("capture_duration_exceeded")
        return inspect_snapshot(positions_by_symbol=pos,orders_by_symbol=orders,
             algo_by_symbol=algos,account=account,fetched_at_ms=start,
             observed_at_ms=finished,source_complete=True,max_age_ms=max_capture_ms)
    except Exception:
        return unknown("broker_read_failed")
