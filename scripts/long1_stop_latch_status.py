#!/usr/bin/env python3
"""Read-only LONG1 emergency lock status. No exchange order or lock clearing."""
from pathlib import Path
import sys,os,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
load_dotenv(ROOT/'.runtime_secrets.env',override=False)
from core.long1_native_stop_fail_safe import KEY,DISK_LATCH,long_qty
from core.binance_futures_v3 import signed_get
import redis

def main():
    r=redis.Redis(decode_responses=True,socket_timeout=2)
    data=dict(disk_latch=DISK_LATCH.exists(),redis_latch=None,exchange_qty=None,
              native_stop_count=None,safety_latch_clear_and_flat=None)
    try:
        data['redis_latch']=r.get(KEY)
    except Exception as e:
        data['redis_error']=type(e).__name__
    try:
        data['exchange_qty']=long_qty()
        algo=signed_get('/fapi/v1/openAlgoOrders',{'symbol':'NEARUSDT'})
        data['native_stop_count']=sum(
            a.get('side')=='SELL' and a.get('positionSide')=='LONG'
            and str(a.get('orderType') or a.get('type'))=='STOP_MARKET'
            for a in algo)
    except Exception as e:
        data['exchange_error']=type(e).__name__
    data['safety_latch_clear_and_flat']=(
        not data['disk_latch'] and data['redis_latch'] in ('',None,'0')
        and not data.get('redis_error') and not data.get('exchange_error')
        and data['exchange_qty']==0
    )
    print(json.dumps(data,sort_keys=True))
    return 0 if not data.get('redis_error') and not data.get('exchange_error') else 2

if __name__=='__main__':
    raise SystemExit(main())
