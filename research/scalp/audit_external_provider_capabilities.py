#!/usr/bin/env python3
import os,time,base64,hmac,hashlib,json
from pathlib import Path
from urllib.parse import urlencode
import requests
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[2]
for f in [ROOT/'.env',ROOT/'.runtime_secrets.env']:
    if f.exists(): load_dotenv(f, override=False)

KEYS=['COINGLASS_API_KEY','OKX_API_KEY','OKX_API_SECRET','OKX_PASSPHRASE','CRYPTOQUANT_API_KEY','COINMARKETCAP_API_KEY','SANTIMENT_API_KEY','ETHERSCAN_API_KEY','INFURA_API_KEY','THE_GRAPH_API_KEY','GRAPH_API_KEY','POLYGON_API_KEY','BSCSCAN_API_KEY','PG_DSN']
print('===== SECRET PRESENCE ONLY =====')
for k in KEYS:
    v=os.getenv(k,'')
    print(f'{k}:', 'PRESENT' if bool(v and v.strip()) else 'MISSING')

S=requests.Session(); S.headers.update({'User-Agent':'binance1-research-capability-audit/1.0'})

def safe_get(name,url,headers=None,params=None,timeout=12):
    try:
        r=S.get(url,headers=headers or {},params=params or {},timeout=timeout)
        out={'name':name,'http':r.status_code,'ok':False,'code':None,'msg':None,'data_type':None,'data_len':None}
        try:
            j=r.json(); out['code']=str(j.get('code')) if isinstance(j,dict) and 'code' in j else None; out['msg']=str(j.get('msg',''))[:120] if isinstance(j,dict) else None
            d=j.get('data') if isinstance(j,dict) else None
            out['data_type']=type(d).__name__ if d is not None else type(j).__name__
            if hasattr(d,'__len__'): out['data_len']=len(d)
            out['ok']=r.ok and (out['code'] in (None,'0','200','200000'))
        except Exception:
            out['msg']=r.text[:120].replace('\n',' ')
            out['ok']=r.ok
        print(json.dumps(out,ensure_ascii=False))
        return out
    except Exception as e:
        out={'name':name,'http':None,'ok':False,'code':None,'msg':type(e).__name__+': '+str(e)[:100]}
        print(json.dumps(out,ensure_ascii=False)); return out

print('\n===== COINGLASS V4 READ-ONLY =====')
cg=os.getenv('COINGLASS_API_KEY','').strip()
if cg:
    h={'accept':'application/json','CG-API-KEY':cg}
    base='https://open-api-v4.coinglass.com'
    safe_get('cg_supported_coins',base+'/api/futures/supported-coins',h)
    safe_get('cg_oi_exchange_list_NEAR',base+'/api/futures/open-interest/exchange-list',h,{'symbol':'NEAR'})
    safe_get('cg_liq_exchange_list_NEAR_1h',base+'/api/futures/liquidation/exchange-list',h,{'symbol':'NEAR','range':'1h'})
    for iv in ['1m','5m','30m','4h']:
        safe_get('cg_oi_hist_'+iv,base+'/api/futures/open-interest/history',h,{'exchange':'Binance','symbol':'NEARUSDT','interval':iv,'limit':5})
    for iv in ['1m','30m','4h']:
        safe_get('cg_funding_hist_'+iv,base+'/api/futures/funding-rate/history',h,{'exchange':'Binance','symbol':'NEARUSDT','interval':iv,'limit':5})
else: print('COINGLASS_API_KEY missing')

print('\n===== OKX PUBLIC READ-ONLY =====')
okbase='https://www.okx.com'
safe_get('okx_oi_NEAR',okbase+'/api/v5/public/open-interest',params={'instType':'SWAP','instId':'NEAR-USDT-SWAP'})
safe_get('okx_funding_hist_NEAR',okbase+'/api/v5/public/funding-rate-history',params={'instId':'NEAR-USDT-SWAP','limit':'5'})
safe_get('okx_candles_NEAR',okbase+'/api/v5/market/candles',params={'instId':'NEAR-USDT-SWAP','bar':'1m','limit':'5'})

print('\n===== OKX PRIVATE AUTH VALIDITY (NO ACCOUNT VALUES PRINTED) =====')
api=os.getenv('OKX_API_KEY','').strip(); sec=os.getenv('OKX_API_SECRET','').strip(); pas=os.getenv('OKX_PASSPHRASE','').strip()
if api and sec and pas:
    path='/api/v5/account/config'; method='GET'; body=''
    ts=time.strftime('%Y-%m-%dT%H:%M:%S.',time.gmtime())+f'{int(time.time()*1000)%1000:03d}Z'
    pre=ts+method+path+body
    sign=base64.b64encode(hmac.new(sec.encode(),pre.encode(),hashlib.sha256).digest()).decode()
    hdr={'OK-ACCESS-KEY':api,'OK-ACCESS-SIGN':sign,'OK-ACCESS-TIMESTAMP':ts,'OK-ACCESS-PASSPHRASE':pas,'Content-Type':'application/json'}
    try:
        r=S.get(okbase+path,headers=hdr,timeout=12); j=r.json(); code=str(j.get('code','')); msg=str(j.get('msg',''))[:120]
        perms=[]
        if code=='0' and isinstance(j.get('data'),list) and j['data']:
            perm=j['data'][0].get('perm','')
            perms=[x.strip() for x in str(perm).split(',') if x.strip()]
        print(json.dumps({'name':'okx_private_auth','http':r.status_code,'ok':r.ok and code=='0','code':code,'msg':msg,'permissions':perms},ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'name':'okx_private_auth','ok':False,'msg':type(e).__name__+': '+str(e)[:100]},ensure_ascii=False))
else: print('OKX credentials incomplete')
