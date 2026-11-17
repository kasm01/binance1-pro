"""Stage20 bounded, signed GET-only account audit. Never opens/closes orders.
Only prints structural proof / error types; NEVER prints credentials, balances,
position sizes, raw orders, client IDs, or full broker responses.
"""
from __future__ import annotations
import json,os,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from core.binance_futures_v3 import account,position_risk,signed_get
SYMBOLS=('NEARUSDT','INJUSDT')
start=time.monotonic()
out={"time_utc":datetime.now(timezone.utc).isoformat(),"source":"SIGNED_GET_ONLY",
     "scope":"FULL_ACCOUNT_POSITIONS_AND_TWO_SYMBOL_ORDER_SOURCES",
     "state":"UNKNOWN","authorized_live":False,"new_orders":0}
try:
    a=account()
    p=position_risk()
    if not isinstance(p,list) or not all(isinstance(row,dict) for row in p):
        raise ValueError("invalid_account_position_payload")
    incomplete=[i for i,row in enumerate(p) if not all(k in row for k in ('symbol','positionSide','positionAmt'))]
    if incomplete:raise ValueError("missing_position_fields")
    nonzero=[]
    for row in p:
        qty=float(row['positionAmt'])
        if not __import__('math').isfinite(qty):raise ValueError("invalid_position_quantity")
        if qty!=0:nonzero.append(str(row['symbol']))
    order_counts={}
    for symbol in SYMBOLS:
        orders=signed_get('/fapi/v1/openOrders',{'symbol':symbol})
        algos=signed_get('/fapi/v1/openAlgoOrders',{'symbol':symbol})
        if not isinstance(orders,list) or not isinstance(algos,list):
            raise ValueError("invalid_order_source")
        if any(not isinstance(row,dict) or row.get('symbol')!=symbol for row in orders+algos):
            raise ValueError("order_symbol_mismatch")
        order_counts[symbol]={"standard":len(orders),"algo":len(algos)}
    out.update(state="READONLY_COVERAGE_COMPLETE_NOT_AUTHORIZED",
        account_fields_valid=all(k in a for k in ('totalMarginBalance','availableBalance','totalInitialMargin')),
        all_account_position_rows=len(p),
        all_account_nonzero_positions=len(nonzero),
        nonzero_symbols_in_scope=sum(s in SYMBOLS for s in nonzero),
        nonzero_symbols_outside_scope=sum(s not in SYMBOLS for s in nonzero),
        scoped_order_counts=order_counts,
        snapshot_captured_in_sec=round(time.monotonic()-start,2))
except Exception as ex:
    out.update(state="UNKNOWN",reason="signed_get_failed:"+type(ex).__name__)
out["elapsed_sec"]=round(time.monotonic()-start,2)
print(json.dumps(out,sort_keys=True))
