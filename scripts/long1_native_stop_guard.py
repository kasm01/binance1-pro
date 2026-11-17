#!/usr/bin/env python3
"""Binance USD-M exchange-native protective SL manager; explicit --apply required.
Research/operations only. Never opens a position, cancels unrelated orders or widens stop.
"""
import argparse, hashlib, hmac, json, os, sys, time
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from core.binance_futures_v3 import signed_get,position_risk,_base_url
SYMBOL='NEARUSDT';TAG='b1guard_NEAR_L_'
def client_algo_id(entry_ms:int):
    return TAG+str(int(entry_ms))
def signed_write(method,path,params):
    api=os.getenv('BINANCE_API_KEY','').strip();secret=os.getenv('BINANCE_API_SECRET','').strip()
    if not api or not secret:raise RuntimeError('missing_api_credentials')
    p=dict(params,timestamp=int(time.time()*1000),recvWindow=5000)
    query=urlencode(p);sign=hmac.new(secret.encode(),query.encode(),hashlib.sha256).hexdigest()
    url=f'{_base_url()}{path}?{query}&signature={sign}'
    response=requests.request(method,url,headers={'X-MBX-APIKEY':api},timeout=10,allow_redirects=False)
    if response.status_code!=200:raise RuntimeError('exchange_api_rejected:'+str(response.status_code)+':'+response.text[:180])
    return response.json()
def stop_context():
    current=position_risk(SYMBOL)
    active=[v for v in current if v.get('positionSide')=='LONG' and Decimal(str(v.get('positionAmt') or 0))>0]
    if len(active)>1:raise RuntimeError('ambiguous_multiple_long_positions')
    pos=active[0] if active else None
    open_algo=signed_get('/fapi/v1/openAlgoOrders',{'symbol':SYMBOL})
    if not isinstance(open_algo,list):raise RuntimeError('open_algo_list_invalid')
    if not pos:return None,open_algo,None,None
    info=requests.get(_base_url()+'/fapi/v1/exchangeInfo',timeout=10).json()
    sym=next(v for v in info['symbols'] if v['symbol']==SYMBOL)
    tick=next(Decimal(v['tickSize']) for v in sym['filters'] if v['filterType']=='PRICE_FILTER')
    entry=Decimal(pos['entryPrice']);amount=Decimal(pos['positionAmt'])
    if entry<=0 or amount<=0 or tick<=0:raise RuntimeError('invalid_current_position_or_tick')
    from_env=Decimal(os.environ.get('SL_PCT','0.0299'))
    if from_env<=0 or from_env>.10:raise RuntimeError('invalid_SL_PCT')
    # nearest tick; not a widened underlying price stop
    stop=((entry*(Decimal(1)-from_env)/tick).quantize(0,rounding=ROUND_HALF_UP)*tick)
    mark=Decimal(pos.get('markPrice','0'))
    return pos,open_algo,stop,mark
def ours(o):
    return str(o.get('clientAlgoId') or '').startswith(TAG)
def matches(o):
    return o.get('symbol')==SYMBOL and o.get('side')=='SELL' and o.get('positionSide')=='LONG' and str(o.get('orderType') or o.get('type'))=='STOP_MARKET' and str(o.get('closePosition')).lower()=='true'
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true',help='Allow exchange POST/DELETE only after guard checks')
    parser.add_argument('--cleanup-flat',action='store_true',help='Remove ONLY tagged stale guards when Binance LONG position is flat')
    a=parser.parse_args()
    pos,orders,stop,mark=stop_context()
    print('MODE', 'APPLY' if a.apply else 'CHECK_ONLY','OPEN_LONG',bool(pos),
          'OPEN_ALGO',len(orders),'TAGGED',sum(ours(o) for o in orders))
    if pos is None:
        stale=[o for o in orders if ours(o)]
        print('NO_LONG','STALE_GUARDS',[(o.get('algoId'),o.get('triggerPrice')) for o in stale])
        if a.apply and a.cleanup_flat:
            for o in stale:
                result=signed_write('DELETE','/fapi/v1/algoOrder',{'symbol':SYMBOL,'algoId':str(o['algoId'])})
                print('CANCELED_STALE',o['algoId'],result.get('code'))
        return
    print('POSITION','qty',pos['positionAmt'],'entry',pos['entryPrice'],'mark',mark,
          'native_stop',str(stop),'app_SL_PCT',os.environ.get('SL_PCT','0.0299'))
    candidates=[o for o in orders if matches(o)]
    if candidates:
        print('PREEXISTING_NATIVE_STOPS',[(o.get('algoId'),o.get('triggerPrice'),o.get('clientAlgoId')) for o in candidates])
        # Existing protection is independent; do not accidentally duplicate.
        return
    if any(ours(o) for o in orders):raise RuntimeError('unknown_tagged_order_requires_manual_review')
    if mark<=stop:raise RuntimeError('MARK_AT_OR_BELOW_TARGET_STOP--NO_POST')
    if not a.apply:
        print('CHECK_ONLY_WOULD_CREATE',str(stop))
        return
    from_mode=signed_get('/fapi/v1/positionSide/dual')
    if not bool(from_mode.get('dualSidePosition')):raise RuntimeError('account_mode_not_HEDGE--manual_review')
    cid=client_algo_id(pos.get('updateTime') or int(time.time()*1000))
    result=signed_write('POST','/fapi/v1/algoOrder',dict(
      algoType='CONDITIONAL',symbol=SYMBOL,side='SELL',
      positionSide='LONG',type='STOP_MARKET',triggerPrice=str(stop),
      workingType='MARK_PRICE',closePosition='true',priceProtect='FALSE',
      clientAlgoId=cid))
    print('CREATED','algoId',result.get('algoId'),'clientAlgoId',cid)
    verify=signed_get('/fapi/v1/openAlgoOrders',{'symbol':SYMBOL})
    valid=[x for x in verify if matches(x) and x.get('clientAlgoId')==cid and Decimal(str(x['triggerPrice']))==stop]
    if not valid:raise RuntimeError('GUARD_POSTED_BUT_NOT_VERIFIED_CHECK_BINANCE_IMMEDIATELY')
    print('VERIFIED',[(x.get('algoId'),x.get('algoStatus'),x.get('triggerPrice'),x.get('workingType'),x.get('closePosition')) for x in valid])
if __name__=='__main__':main()
