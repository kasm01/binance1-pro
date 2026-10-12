#!/usr/bin/env python3
import requests,pandas as pd
base='https://www.okx.com/api/v5/market/history-candles'; inst='NEAR-USDT-SWAP'
r=requests.get(base,params={'instId':inst,'bar':'1m','limit':'100'},timeout=10).json(); d=r.get('data',[])
old=min(int(x[0]) for x in d); print('page1',len(d),pd.to_datetime(old,unit='ms',utc=True))
for key in ['after','before']:
    j=requests.get(base,params={'instId':inst,'bar':'1m','limit':'5',key:str(old-1)},timeout=10).json(); dd=j.get('data',[])
    print(key,j.get('code'),len(dd),[str(pd.to_datetime(int(x[0]),unit='ms',utc=True)) for x in dd[:2]])
