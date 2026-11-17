#!/usr/bin/env python3
"""Persistent NEARUSDT LONG native stop reconciler.

Exchange writes only with --apply. Never opens market positions, never cancels foreign orders.
Uses one canonical close-all Binance USD-M Algo stop per detected LONG position.
"""
from __future__ import annotations
import argparse, json, logging, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import long1_native_stop_guard as g

def reconcile(*, apply: bool=False):
    pos, algos, stop, mark = g.stop_context()
    tagged=[x for x in algos if g.ours(x)]
    if not pos:
        if not tagged:return {'state':'FLAT_CLEAN','orders':0}
        if apply:
            # Only our own specifically tagged algo orders.
            for old in tagged:
                g.signed_write('DELETE','/fapi/v1/algoOrder',{'symbol':g.SYMBOL,'algoId':str(old['algoId'])})
            remaining=g.signed_get('/fapi/v1/openAlgoOrders',{'symbol':g.SYMBOL})
            if any(g.ours(x) for x in remaining):raise RuntimeError('tagged_stale_stop_still_present')
            return {'state':'FLAT_STALE_CLEANED','orders':len(tagged)}
        return {'state':'FLAT_STALE_PRESENT','orders':len(tagged)}
    posid=g.client_algo_id(pos.get('updateTime') or 0)
    exact=[x for x in algos if g.matches(x) and
           str(x.get('clientAlgoId') or '')==posid and
           str(x.get('triggerPrice') or '')!='' and
           g.Decimal(str(x['triggerPrice']))==stop and
           x.get('algoStatus') in ('NEW','PENDING','ACCEPTED')]
    foreign=[x for x in algos if g.matches(x) and not g.ours(x)]
    if foreign:return {'state':'FOREIGN_PROTECTIVE_PRESENT_MANUAL_REVIEW','foreign':len(foreign)}
    stale=[x for x in tagged if x not in exact]
    if exact and not stale:return {'state':'PROTECTED','algoId':exact[0].get('algoId'),'stop':str(stop)}
    if not apply:return {'state':'MISSING_OR_MISMATCHED','stop':str(stop),'stale':len(stale)}
    if mark<=stop:raise RuntimeError('mark_at_or_below_stop_no_new_algo_possible')
    mode=g.signed_get('/fapi/v1/positionSide/dual')
    if not mode.get('dualSidePosition'):raise RuntimeError('hedge_mode_required')
    if not exact:
        try:
            result=g.signed_write('POST','/fapi/v1/algoOrder',dict(
              algoType='CONDITIONAL',symbol=g.SYMBOL,side='SELL',positionSide='LONG',
              type='STOP_MARKET',triggerPrice=str(stop),workingType='MARK_PRICE',
              closePosition='true',priceProtect='FALSE',clientAlgoId=posid))
        except Exception:
            # POST might have reached Binance before network timeout; verify idempotency before retry.
            check=g.signed_get('/fapi/v1/openAlgoOrders',{'symbol':g.SYMBOL})
            if not any(x.get('clientAlgoId')==posid and g.matches(x) for x in check):raise
        verify=g.signed_get('/fapi/v1/openAlgoOrders',{'symbol':g.SYMBOL})
        exact=[x for x in verify if g.matches(x) and x.get('clientAlgoId')==posid
             and g.Decimal(str(x.get('triggerPrice') or 0))==stop]
        if len(exact)!=1:raise RuntimeError('exchange_stop_not_uniquely_verified')
    # New native stop is verified BEFORE removing old tagged stops.
    for old in stale:
        g.signed_write('DELETE','/fapi/v1/algoOrder',{'symbol':g.SYMBOL,'algoId':str(old['algoId'])})
    verify2=g.signed_get('/fapi/v1/openAlgoOrders',{'symbol':g.SYMBOL})
    final=[x for x in verify2 if g.matches(x) and x.get('clientAlgoId')==posid
           and g.Decimal(str(x.get('triggerPrice') or 0))==stop]
    if len(final)!=1:raise RuntimeError('native_stop_not_verified_after_reconciliation')
    return {'state':'PROTECTED_CREATED_OR_REPLACED','algoId':final[0].get('algoId'),'stop':str(stop)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--apply',action='store_true',help='Enable exchange stop creation and own stale cleanup')
    p.add_argument('--loop',action='store_true')
    p.add_argument('--interval',type=int,default=45)
    a=p.parse_args()
    if a.loop and not (30<=a.interval<=300):raise SystemExit('invalid interval')
    prior=None
    while True:
        try:
            result=reconcile(apply=a.apply)
            if result!=prior or result.get('state') not in ('PROTECTED','FLAT_CLEAN'):
                print(json.dumps({'ts':int(time.time()),**result},sort_keys=True),flush=True)
            prior=result
        except Exception as e:
            print(json.dumps({'ts':int(time.time()),'state':'ERROR','error':type(e).__name__,'details':str(e)[:180]}),flush=True)
            if not a.loop:return 2
        if not a.loop:break
        time.sleep(a.interval)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
