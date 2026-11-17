"""Strict Binance USD-M full-account position count for live LONG risk checks.

A failed or malformed positionRisk must raise; it can NEVER become 0.
This is a source-validation layer, not proof of atomic portfolio snapshot.
"""
from __future__ import annotations
from decimal import Decimal,InvalidOperation

def count_side(rows,side:str)->int:
    target=str(side or "").strip().lower()
    if target not in {"long","short"}:
        raise ValueError("position_side_invalid")
    if not isinstance(rows,list):
        raise ValueError("broker_position_response_invalid")
    unique=set()
    count=0
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("broker_position_row_invalid")
        symbol=row.get("symbol")
        position_side=str(row.get("positionSide") or "").upper()
        if not isinstance(symbol,str) or not symbol.strip() or position_side not in {"BOTH","LONG","SHORT"}:
            raise ValueError("broker_position_identity_invalid")
        ident=(symbol,position_side)
        if ident in unique:
            raise ValueError("duplicate_exchange_position_leg")
        unique.add(ident)
        if "positionAmt" not in row:
            raise ValueError("missing_exchange_position_amount")
        try:
            quantity=Decimal(str(row["positionAmt"]))
        except (InvalidOperation,TypeError,ValueError) as exc:
            raise ValueError("invalid_exchange_position_amount") from exc
        if not quantity.is_finite():
            raise ValueError("nonfinite_exchange_position_amount")
        if position_side=="LONG" and quantity<0:
            raise ValueError("long_position_sign_invalid")
        if position_side=="SHORT" and quantity>0:
            raise ValueError("short_position_sign_invalid")
        if quantity==0:
            continue
        normalized=("long" if quantity>0 else "short") if position_side=="BOTH" else position_side.lower()
        if normalized==target:
            count+=1
    return count
