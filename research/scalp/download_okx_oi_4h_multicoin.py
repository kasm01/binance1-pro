#!/usr/bin/env python3
from pathlib import Path
import time, requests, pandas as pd
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'research/results'
COINS=['SOL','LINK','AVAX','DOGE']; URL='https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history'
cutoff=int((pd.Timestamp.now(tz='UTC')-pd.Timedelta(days=370)).timestamp()*1000)
s=requests.Session()
for coin in COINS:
    inst=f'{coin}-USDT-SWAP'; rows=[]; end=None
    for page in range(40):
        q={'instId':inst,'period':'4H','limit':'100'}
        if end is not None:q['end']=str(end)
        try:
            j=s.get(URL,params=q,timeout=12).json(); data=j.get('data') or [] if str(j.get('code'))=='0' else []
        except Exception:data=[]
        if not data:break
        rows.extend(data); oldest=min(int(x[0]) for x in data); end=oldest-1
        if page==0 or (page+1)%5==0: print(coin,'page',page+1,'rows',len(rows),'oldest',pd.to_datetime(oldest,unit='ms',utc=True),flush=True)
        if oldest<=cutoff:break
        time.sleep(.08)
    df=pd.DataFrame(rows,columns=['ts','oi_contracts','oi_ccy','oi_usd'])
    if len(df):
        df.ts=pd.to_numeric(df.ts); df=df.drop_duplicates('ts').sort_values('ts'); df=df[df.ts>=cutoff]
        for c in ['oi_contracts','oi_ccy','oi_usd']:df[c]=pd.to_numeric(df[c],errors='coerce')
    path=OUT/f'OKX_{coin}_OI_4H_360d.csv.gz'; df.to_csv(path,index=False,compression='gzip')
    rng=(pd.to_datetime(df.ts.iloc[0],unit='ms',utc=True),pd.to_datetime(df.ts.iloc[-1],unit='ms',utc=True)) if len(df) else None
    print(coin,'N',len(df),'RANGE',rng,'OUT',path,flush=True)
