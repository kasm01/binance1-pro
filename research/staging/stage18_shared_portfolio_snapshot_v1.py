"""Stage18 PURE snapshot candidate, no Binance calls or Redis I/O.

For MULTI-BOT use: each independent signed GET must be performed via the same
authenticated account, with server-time and venue proof in a future adapter.
The output never confers order authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal,InvalidOperation
from typing import Any,Mapping
import math

SYMBOLS=("NEARUSDT","INJUSDT")
LEGS=("LONG","SHORT","BOTH")

@dataclass(frozen=True)
class SnapshotResult:
    state: str
    reason: str
    captured_at_ms: int|None
    positions: tuple[tuple[str,str,str], ...]
    open_standard_orders: int|None
    open_algo_orders: int|None
    can_authorize_live: bool=False

def unknown(reason:str)->SnapshotResult:
    return SnapshotResult("UNKNOWN",reason,None,(),None,None,False)

def _dec(x: Any)->Decimal:
    if isinstance(x,bool):raise ValueError("bool is not amount")
    try:
        val=Decimal(str(x))
        if not val.is_finite():raise ValueError("non-finite amount")
        return val
    except (InvalidOperation,TypeError) as err:
        raise ValueError("invalid decimal") from err

def inspect_snapshot(*, positions_by_symbol:Any, orders_by_symbol:Any,
                     algo_by_symbol:Any, account:Any, fetched_at_ms:Any,
                     observed_at_ms:Any, source_complete:bool,
                     max_age_ms:int=5000)->SnapshotResult:
    """Strict closed-world inspection for two symbols; no inferred empty lists."""
    if source_complete is not True:
        return unknown("source_not_complete")
    if not isinstance(fetched_at_ms,int) or isinstance(fetched_at_ms,bool) or not isinstance(observed_at_ms,int):
        return unknown("invalid_clock")
    if fetched_at_ms<=0 or observed_at_ms<=0 or fetched_at_ms>observed_at_ms+1000:
        return unknown("future_or_invalid_clock")
    if observed_at_ms-fetched_at_ms>max_age_ms:
        return unknown("stale_snapshot")
    if not isinstance(account,Mapping):
        return unknown("account_unavailable")
    try:
        equity=_dec(account["totalMarginBalance"])
        available=_dec(account["availableBalance"])
        if equity<=0 or available<0:
            return unknown("invalid_margin")
    except (KeyError,ValueError):
        return unknown("account_metrics_unknown")
    for label,pack in (("positions",positions_by_symbol),("orders",orders_by_symbol),("algos",algo_by_symbol)):
        if not isinstance(pack,Mapping) or set(pack)!=set(SYMBOLS):
            return unknown(f"{label}_symbols_incomplete")
        if any(not isinstance(pack.get(s),list) for s in SYMBOLS):
            return unknown(f"{label}_unavailable")
    legs=[]
    seen=set()
    order_count=algo_count=0
    try:
        for symbol in SYMBOLS:
            for row in positions_by_symbol[symbol]:
                if not isinstance(row,Mapping) or row.get("symbol")!=symbol:
                    return unknown("position_symbol_mismatch")
                side=str(row.get("positionSide","")).upper()
                if side not in LEGS:
                    return unknown("position_side_unknown")
                key=(symbol,side)
                if key in seen:
                    return unknown("duplicate_position_leg")
                seen.add(key)
                quantity=_dec(row["positionAmt"])
                if (side=="LONG" and quantity<0) or (side=="SHORT" and quantity>0):
                    return unknown("position_sign_inconsistent")
                if quantity!=0:
                    if side=="BOTH":
                        # Distinguish net positive/negative; do not invent a hedge position
                        side="LONG" if quantity>0 else "SHORT"
                    legs.append((symbol,side,str(abs(quantity))))
            for row in orders_by_symbol[symbol]:
                if not isinstance(row,Mapping) or row.get("symbol")!=symbol or not row.get("orderId"):
                    return unknown("open_order_invalid")
                order_count+=1
            for row in algo_by_symbol[symbol]:
                if not isinstance(row,Mapping) or row.get("symbol")!=symbol or not row.get("algoId"):
                    return unknown("algo_order_invalid")
                algo_count+=1
    except (KeyError,ValueError):
        return unknown("position_data_invalid")
    return SnapshotResult(
        "CONSISTENT_INPUTS_NOT_AUTHORIZED","snapshot_readonly_only",fetched_at_ms,
        tuple(sorted(legs)),order_count,algo_count,False)
