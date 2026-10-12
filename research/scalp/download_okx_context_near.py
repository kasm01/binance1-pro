#!/usr/bin/env python3
from pathlib import Path
import time, requests, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/results'; OUT.mkdir(parents=True,exist_ok=True)
BASE='https://www.okx.com'; INST='NEAR-USDT-SWAP'
s=requests.Session(); s.headers.update({'User-Agent':'binance1-research/1.0'})

def get(path,params):
    for n in range(5):
        try:
            r=s.get(BASE+path,params=params,timeout=15); j=r.json()
            if r.status_code==200 and str(j.get('code'))=='0': return j.get('data') or []
            print('WARN',path,'http',r.status_code,'code',j.get('code'),'msg',j.get('msg'))
        except Exception as e: print('WARN',path,type(e).__name__,str(e)[:120])
        time.sleep(0.4*(n+1))
    return []

def download_oi(max_pages=1000):
    rows=[]; end=None
    for p in range(max_pages):
        q={'instId':INST,'period':'5m','limit':'100'}
        if end is not None: q['end']=str(end)
        d=get('/api/v5/rubik/stat/contracts/open-interest-history',q)
        if not d: break
        rows.extend(d); oldest=min(int(x[0]) for x in d); end=oldest-1
        if p%25==0: print('OI page',p+1,'rows',len(rows),'oldest',pd.to_datetime(oldest,unit='ms',utc=True))
        time.sleep(0.08)
    df=pd.DataFrame(rows,columns=['ts','oi_contracts','oi_ccy','oi_usd'])
    if not df.empty:
        df['ts']=pd.to_numeric(df.ts); df=df.drop_duplicates('ts').sort_values('ts')
        for c in ['oi_contracts','oi_ccy','oi_usd']: df[c]=pd.to_numeric(df[c],errors='coerce')
    return df

def download_funding(max_pages=1000):
    rows=[]; after=None
    for p in range(max_pages):
        q={'instId':INST,'limit':'100'}
        if after is not None: q['after']=str(after)
        d=get('/api/v5/public/funding-rate-history',q)
        if not d: break
        rows.extend(d); oldest=min(int(x['fundingTime']) for x in d); after=oldest-1
        if p%10==0: print('FUND page',p+1,'rows',len(rows),'oldest',pd.to_datetime(oldest,unit='ms',utc=True))
        time.sleep(0.08)
    df=pd.DataFrame(rows)
    if not df.empty:
        df['fundingTime']=pd.to_numeric(df.fundingTime); df=df.drop_duplicates('fundingTime').sort_values('fundingTime')
        for c in ['fundingRate','realizedRate']: 
            if c in df: df[c]=pd.to_numeric(df[c],errors='coerce')
    return df

if __name__=='__main__':
    oi=download_oi(); fu=download_funding()
    op=OUT/'OKX_NEAR_OI_5M.csv.gz'; fp=OUT/'OKX_NEAR_FUNDING.csv.gz'
    oi.to_csv(op,index=False,compression='gzip'); fu.to_csv(fp,index=False,compression='gzip')
    print('OI',len(oi),'range', (pd.to_datetime(oi.ts.iloc[0],unit='ms',utc=True),pd.to_datetime(oi.ts.iloc[-1],unit='ms',utc=True)) if len(oi) else None)
    print('FUND',len(fu),'range', (pd.to_datetime(fu.fundingTime.iloc[0],unit='ms',utc=True),pd.to_datetime(fu.fundingTime.iloc[-1],unit='ms',utc=True)) if len(fu) else None)
    print('OUTPUT',op,fp)
