from pathlib import Path
import time, requests, pandas as pd
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'research/results'; OUT.mkdir(parents=True,exist_ok=True)
S='NEARUSDT'; BASE='https://fapi.binance.com'; now=int(time.time()*1000); start=now-360*86400000

def get_json(path,params):
    for k in range(5):
        r=requests.get(BASE+path,params=params,timeout=15)
        if r.status_code==200:return r.json()
        time.sleep(1.5*(k+1))
    raise RuntimeError(f'{path} http={r.status_code} {r.text[:200]}')

# premium index klines 5m
rows=[]; t=start
while t<now:
    js=get_json('/fapi/v1/premiumIndexKlines',{'symbol':S,'interval':'5m','startTime':t,'endTime':now,'limit':1500})
    if not js:break
    rows.extend(js); nt=int(js[-1][6])+1
    if nt<=t:break
    t=nt; time.sleep(.05)
pre=pd.DataFrame(rows,columns=['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_base','taker_quote','ignore'])
pre=pre.drop_duplicates('open_time').sort_values('open_time')
for c in ['open','high','low','close']:pre[c]=pd.to_numeric(pre[c],errors='coerce')
pre[['open_time','close_time','open','high','low','close']].to_csv(OUT/'BINANCE_NEAR_PREMIUM_5M_360d.csv.gz',index=False,compression='gzip')
print('premium_rows',len(pre),'from',pre.open_time.min(),'to',pre.open_time.max())

# funding history; paginate by startTime. limit 1000
fr=[]; t=start
while t<now:
    js=get_json('/fapi/v1/fundingRate',{'symbol':S,'startTime':t,'endTime':now,'limit':1000})
    if not js:break
    fr.extend(js); nt=int(js[-1]['fundingTime'])+1
    if nt<=t:break
    t=nt
    if len(js)<1000:break
    time.sleep(.05)
fd=pd.DataFrame(fr)
if len(fd):
    fd=fd.drop_duplicates('fundingTime').sort_values('fundingTime')
    fd['fundingRate']=pd.to_numeric(fd['fundingRate'],errors='coerce')
    fd[['fundingTime','fundingRate']].to_csv(OUT/'BINANCE_NEAR_FUNDING_360d.csv.gz',index=False,compression='gzip')
print('funding_rows',len(fd),'from',fd.fundingTime.min() if len(fd) else None,'to',fd.fundingTime.max() if len(fd) else None)
