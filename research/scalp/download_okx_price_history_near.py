#!/usr/bin/env python3
from pathlib import Path
import time, requests, pandas as pd
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'research/results'; OUT.mkdir(parents=True,exist_ok=True)
URL='https://www.okx.com/api/v5/market/history-candles'; INST='NEAR-USDT-SWAP'
s=requests.Session(); s.headers.update({'User-Agent':'binance1-research/1.0'})

def fetch(bar,max_days=370):
    rows=[]; after=None; cutoff=int((pd.Timestamp.now(tz='UTC')-pd.Timedelta(days=max_days)).timestamp()*1000)
    for p in range(2000):
        q={'instId':INST,'bar':bar,'limit':'300'}
        if after is not None: q['after']=str(after)
        ok=False
        for k in range(4):
            try:
                j=s.get(URL,params=q,timeout=15).json()
                if str(j.get('code'))=='0': d=j.get('data') or []; ok=True; break
            except Exception: pass
            time.sleep(.25*(k+1))
        if not ok or not d: break
        rows.extend(d); oldest=min(int(x[0]) for x in d); after=oldest-1
        if p%50==0: print(bar,'page',p+1,'rows',len(rows),'oldest',pd.to_datetime(oldest,unit='ms',utc=True),flush=True)
        if oldest<=cutoff: break
        time.sleep(.06)
    cols=['ts','open','high','low','close','vol','volCcy','volCcyQuote','confirm']
    df=pd.DataFrame(rows,columns=cols)
    if len(df):
        df['ts']=pd.to_numeric(df.ts); df=df.drop_duplicates('ts').sort_values('ts'); df=df[df.ts>=cutoff]
        for c in ['open','high','low','close','vol','volCcy','volCcyQuote']: df[c]=pd.to_numeric(df[c],errors='coerce')
    return df

for bar in ['3m','5m']:
    df=fetch(bar)
    path=OUT/f'OKX_NEAR_{bar}_360d.csv.gz'; df.to_csv(path,index=False,compression='gzip')
    rng=(pd.to_datetime(df.ts.iloc[0],unit='ms',utc=True),pd.to_datetime(df.ts.iloc[-1],unit='ms',utc=True)) if len(df) else None
    print(bar,'N',len(df),'RANGE',rng,'OUTPUT',path,flush=True)
