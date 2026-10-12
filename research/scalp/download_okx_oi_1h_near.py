#!/usr/bin/env python3
from pathlib import Path
import time,requests,pandas as pd
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'research/results/OKX_NEAR_OI_1H_360d.csv.gz'
URL='https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history'; INST='NEAR-USDT-SWAP'
s=requests.Session(); rows=[]; end=None; cutoff=int((pd.Timestamp.now(tz='UTC')-pd.Timedelta(days=370)).timestamp()*1000)
for p in range(200):
    q={'instId':INST,'period':'1H','limit':'100'}
    if end is not None:q['end']=str(end)
    d=[]
    for k in range(4):
        try:
            j=s.get(URL,params=q,timeout=12).json()
            if str(j.get('code'))=='0': d=j.get('data') or []; break
        except Exception: pass
        time.sleep(.25*(k+1))
    if not d: break
    rows.extend(d); oldest=min(int(x[0]) for x in d); end=oldest-1
    if p%20==0: print('page',p+1,'rows',len(rows),'oldest',pd.to_datetime(oldest,unit='ms',utc=True),flush=True)
    if oldest<=cutoff: break
    time.sleep(.08)
df=pd.DataFrame(rows,columns=['ts','oi_contracts','oi_ccy','oi_usd'])
if len(df):
    df.ts=pd.to_numeric(df.ts); df=df.drop_duplicates('ts').sort_values('ts'); df=df[df.ts>=cutoff]
    for c in ['oi_contracts','oi_ccy','oi_usd']:df[c]=pd.to_numeric(df[c],errors='coerce')
df.to_csv(OUT,index=False,compression='gzip')
print('N',len(df),'RANGE', (pd.to_datetime(df.ts.iloc[0],unit='ms',utc=True),pd.to_datetime(df.ts.iloc[-1],unit='ms',utc=True)) if len(df) else None,'OUTPUT',OUT)
