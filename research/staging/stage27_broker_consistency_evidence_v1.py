"""Bounded dual-pass broker GET evidence, RESEARCH-ONLY.

This DOES NOT establish atomic exchange snapshots, authenticated account identity,
maker ownership, fills, margin reservations or live order authorization.
Input callables must be audited read-only Binance GET adapters.
No logging of balances, account IDs, key material, order IDs or raw responses.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any, Callable, Mapping

SYMBOLS=("NEARUSDT","INJUSDT")
SIDES=("LONG","SHORT","BOTH")

@dataclass(frozen=True)
class Evidence:
    state: str
    reason: str
    fingerprint: str|None=None
    total_nonzero_positions: int|None=None
    pending_standard_orders: int|None=None
    pending_algo_orders: int|None=None
    capture_elapsed_ms: int|None=None
    source_authenticated: bool=False
    independently_verified_account_id: bool=False
    live_order_authorized: bool=False

def unavailable(reason:str)->Evidence:
    return Evidence("UNKNOWN",reason)

def number(value:Any)->Decimal:
    if isinstance(value,bool) or value is None:
        raise ValueError("decimal_missing_or_bool")
    try:
        d=Decimal(str(value))
    except (InvalidOperation,TypeError,ValueError) as exc:
        raise ValueError("decimal_invalid") from exc
    if not d.is_finite():
        raise ValueError("decimal_nonfinite")
    return d

def positions(rows:Any,*,account:bool)->dict[tuple[str,str],Decimal]:
    if not isinstance(rows,list):
        raise ValueError("position_response_unavailable")
    seen:dict[tuple[str,str],Decimal]={}
    for row in rows:
        if not isinstance(row,Mapping):
            raise ValueError("position_row_not_mapping")
        sym=row.get("symbol")
        side=str(row.get("positionSide","")).upper()
        if not isinstance(sym,str) or not sym or side not in SIDES:
            raise ValueError("position_leg_invalid")
        key=(sym,side)
        if key in seen:
            raise ValueError("duplicate_position_leg")
        qty=number(row["positionAmt"])
        if (side=="LONG" and qty<0) or (side=="SHORT" and qty>0):
            raise ValueError("position_side_sign_inconsistent")
        seen[key]=qty
    return seen

def account_view(raw:Any)->tuple[dict[tuple[str,str],Decimal],tuple[Decimal,...]]:
    if not isinstance(raw,Mapping) or not isinstance(raw.get("positions"),list):
        raise ValueError("account_invalid")
    metrics=(number(raw["totalMarginBalance"]),number(raw["availableBalance"]),
             number(raw["totalInitialMargin"]),
             number(raw["totalOpenOrderInitialMargin"]),
             number(raw["totalPositionInitialMargin"]))
    if metrics[0]<=0 or metrics[1]<0 or any(x<0 for x in metrics[2:]):
        raise ValueError("account_margin_invalid")
    if metrics[1]>metrics[0]+Decimal("0.000001"):
        raise ValueError("available_above_margin")
    return positions(raw["positions"],account=True),metrics

def canonical_nonzero(rows:dict[tuple[str,str],Decimal])->dict[tuple[str,str],Decimal]:
    return {k:v for k,v in rows.items() if v!=0}

def capture(*,get_account:Callable[[],Any],
    get_all_position_risk:Callable[[],Any],
    get_open_orders:Callable[[str],Any],
    get_open_algos:Callable[[str],Any],
    clock_ms:Callable[[],int], max_capture_ms:int=5000)->Evidence:
    """Two passes, 8 broker reads; same symbols, cross API and no drift.

    Even CONSISTENT_READONLY_ONLY may not authorize new orders. Two passes do
    not eliminate fill races between reads, and signed GET authenticates a
    request, NOT a durable atomic broker attestation.
    """
    try:
        start=clock_ms()
        if type(start) is not int or start<=0 or type(max_capture_ms) is not int or max_capture_ms<=0:
            return unavailable("clock_invalid")
        a1=get_account()
        p1=get_all_position_risk()
        orders={}
        algos={}
        for sym in SYMBOLS:
            orders[sym]=get_open_orders(sym)
            algos[sym]=get_open_algos(sym)
        p2=get_all_position_risk()
        a2=get_account()
        finish=clock_ms()
        if type(finish) is not int or finish<start or finish-start>max_capture_ms:
            return unavailable("capture_timed_out_or_clock_invalid")
        account_pos1,metrics1=account_view(a1)
        account_pos2,metrics2=account_view(a2)
        pos1=positions(p1,account=False)
        pos2=positions(p2,account=False)
        # Binance v3 may include zero legs in account but not positionRisk;
        # compare only NONZERO legs, retain zero validation for duplicate/sign.
        nonzero=canonical_nonzero(pos1)
        if (nonzero!=canonical_nonzero(pos2) or
            nonzero!=canonical_nonzero(account_pos1) or
            nonzero!=canonical_nonzero(account_pos2)):
            return unavailable("account_position_conflict_or_drift")
        # Comparing exact metrics is deliberately conservative.
        if metrics1!=metrics2:
            return unavailable("account_margin_changed_during_capture")
        if any(sym not in SYMBOLS for sym,side in nonzero):
            return unavailable("out_of_scope_account_position")
        # If a position appears, mark and notional must be independently
        # checked before modeling portfolio exposure; block that path for now.
        if nonzero:
            return unavailable("nonflat_requires_mark_and_stop_reconciliation")
        # Account-wide margin catches unlisted open orders on OTHER symbols
        # that a two-symbol per-order query cannot individually enumerate.
        if any(x!=0 for x in metrics1[2:]):
            return unavailable("account_wide_initial_margin_unreconciled")
        standard=algo=0
        for sym in SYMBOLS:
            for bucket,label in ((orders,"standard"),(algos,"algo")):
                rows=bucket[sym]
                if not isinstance(rows,list):
                    return unavailable(label+"_source_missing")
                for row in rows:
                    if not isinstance(row,Mapping) or row.get("symbol")!=sym:
                        return unavailable(label+"_order_symbol_invalid")
                    ident=row.get("orderId") if label=="standard" else row.get("algoId")
                    if ident is None or str(ident)=="":
                        return unavailable(label+"_order_identity_missing")
                if label=="standard":standard+=len(rows)
                else:algo+=len(rows)
        if standard or algo:
            return unavailable("open_order_requires_independent_reconciliation")
        payload={
          "schema":"stage27_broker_dualpass_no_authority.v1",
          "symbols":SYMBOLS,"nonzero_positions":0,
          "open_standard":standard,"open_algo":algo,
          "metrics":[str(x) for x in metrics1],
          "capture_start_ms":start,"capture_finish_ms":finish,
        }
        digest=sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        return Evidence("CONSISTENT_READONLY_ONLY","dualpass_flat_stable",
            fingerprint=digest,total_nonzero_positions=0,
            pending_standard_orders=0,pending_algo_orders=0,
            capture_elapsed_ms=finish-start)
    except Exception:
        return unavailable("broker_source_or_shape_unavailable")
