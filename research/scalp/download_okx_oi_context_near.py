#!/usr/bin/env python3
from pathlib import Path
import time,requests,pandas as pd
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'
URL='https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history'; INST='NEAR-USDT-SWAP'
s=requests.Session(); cutoff=int((pd.Timestamp.now(tz='UTC')-pd.Timedelta(days=370)).timestamp()*1000)
for period in ['4H','1D']:
    rows=[]; end=None
    for p in range(200):
        q={'instId':INST,'period':period,'limit':'100'}
        if end is not None:q['end']=str(end)
        try:j=s.get(URL,params=q,timeout=12).json(); d=j.get('data') or [] if str(j.get('code'))=='0' else []
        except Exception:d=[]
        if not d:break
        rows.extend(d); old=min(int(x[0]) for x in d); end=old-1
        if old<=cutoff:break
        time.sleep(.08)
    df=pd.DataFrame(rows,columns=['ts','oi_contracts','oi_ccy','oi_usd'])
    if len(df):
        df.ts=pd.to_numeric(df.ts); df=df.drop_duplicates('ts').sort_values('ts'); df=df[df.ts>=cutoff]
        for c in ['oi_contracts','oi_ccy','oi_usd']:df[c]=pd.to_numeric(df[c],errors='coerce')
    out=R/f'OKX_NEAR_OI_{period}_360d.csv.gz'; df.to_csv(out,index=False,compression='gzip')
    print(period,'N',len(df),'RANGE',(pd.to_datetime(df.ts.iloc[0],unit='ms',utc=True),pd.to_datetime(df.ts.iloc[-1],unit='ms',utc=True)) if len(df) else None,'OUT',out)
