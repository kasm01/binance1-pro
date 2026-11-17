"""Manual one-shot bounded USD-M signed GET audit, NEVER used as live permit.

Only emits counts, reason, elapsed and independent auth booleans; NO secrets,
account balances, position sizes, exact order IDs or raw responses.
"""
from __future__ import annotations
import json,sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from core.binance_futures_v3 import account,position_risk,signed_get
from research.staging.stage27_broker_consistency_evidence_v1 import capture

def positions():
    return position_risk()
def orders(symbol):
    return signed_get('/fapi/v1/openOrders',{'symbol':symbol},timeout=5)
def algos(symbol):
    return signed_get('/fapi/v1/openAlgoOrders',{'symbol':symbol},timeout=5)
started=time.monotonic()
ev=capture(get_account=account,get_all_position_risk=positions,
           get_open_orders=orders,get_open_algos=algos,
           clock_ms=lambda:int(time.monotonic()*1000),max_capture_ms=8000)
print(json.dumps({"checked_at_utc":datetime.now(timezone.utc).isoformat(),
    "state":ev.state,"reason":ev.reason,
    "total_nonzero_positions":ev.total_nonzero_positions,
    "open_standard":ev.pending_standard_orders,
    "open_algo":ev.pending_algo_orders,
    "capture_elapsed_ms":ev.capture_elapsed_ms,
    "total_elapsed_s":round(time.monotonic()-started,2),
    "source_authenticated":ev.source_authenticated,
    "account_id_independently_verified":ev.independently_verified_account_id,
    "live_order_authorized":ev.live_order_authorized,
    "exchange_writes":0,"production_redis_writes":0},sort_keys=True))
