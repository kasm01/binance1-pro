#!/usr/bin/env python3
from pathlib import Path
import numpy as np,pandas as pd
P=Path('/home/kasm920/binance1-pro'); S=Path('/home/kasm920/binance1')
OUT=P/'research/results/STOP_REVALIDATION_V1_20261022'; OUT.mkdir(parents=True,exist_ok=True)
FEE=.0004; SOFT=.04; CATA=.06; HOLD_FRAC=.50; MAX_WAIT=120

def load1m():
 ds=[]
 for fp in sorted((S/'research/short/data/inj_1m').glob('*.csv')):
  d=pd.read_csv(fp); d['ts']=pd.to_datetime(d.open_time,unit='ms',utc=True)
  for c in ['open','high','low','close']: d[c]=pd.to_numeric(d[c],errors='coerce')
  ds.append(d[['ts','open','high','low','close']])
 return pd.concat(ds).sort_values('ts').drop_duplicates('ts').reset_index(drop=True)

def main():
 d=load1m(); ent=pd.read_csv(S/'research/short/results/SHORT1_V49B_TRADE_CONFIRM/V49B_R70_W2/entries.csv'); ent['open_ts']=pd.to_datetime(ent.ts,utc=True,format='mixed')
 c=pd.read_csv(S/'research/short/results/SHORT1_V49B_TRADE_CONFIRM/V49B_R70_W2/closed_positions.csv'); c['open_ts']=pd.to_datetime(c.open_ts,utc=True,format='mixed'); c['stop_ts']=pd.to_datetime(c.close_ts,utc=True,format='mixed')
 c=c[c.reason.eq('soft_stop_1m_confirm')].copy(); em=ent.set_index('open_ts'); rows=[]
 for r in c.itertuples(index=False):
  if r.open_ts not in em.index: continue
  e=em.loc[r.open_ts]; e=e.iloc[0] if isinstance(e,pd.DataFrame) else e
  entry=float(e.price); age=(r.stop_ts-r.open_ts).total_seconds()/60; eligible=age<=120
  base_exit=entry*(1+SOFT); base_unit=(entry-base_exit)/entry - FEE - FEE*(base_exit/entry)
  pol_unit=base_unit; outcome='baseline'; exit2=base_exit; wait=0
  if eligible:
   w=d[(d.ts>r.stop_ts)&(d.ts<=r.stop_ts+pd.Timedelta(minutes=MAX_WAIT))]
   outcome='timeout'
   for q in w.itertuples(index=False):
    rec=float(q.low)<=entry; cat=float(q.high)>=entry*(1+CATA)
    wait=(q.ts-r.stop_ts).total_seconds()/60
    if cat and rec: outcome='cat_same_bar'; exit2=entry*(1+CATA); break
    if cat: outcome='cat'; exit2=entry*(1+CATA); break
    if rec: outcome='recover'; exit2=entry; break
    exit2=float(q.close)
   residual_unit=(entry-exit2)/entry - FEE*(exit2/entry)
   # opening fee is common to whole position; half closes now, half follows residual path
   first_half=(entry-base_exit)/entry - FEE*(base_exit/entry)
   pol_unit=-FEE + (1-HOLD_FRAC)*first_half + HOLD_FRAC*residual_unit
  rows.append(dict(open_ts=r.open_ts,stop_ts=r.stop_ts,age_min=age,eligible=eligible,outcome=outcome,wait_min=wait,entry=entry,exit2=exit2,base_unit=base_unit,policy_unit=pol_unit,delta_unit=pol_unit-base_unit,notional=float(e.notional)))
 x=pd.DataFrame(rows); x.to_csv(OUT/'short_policy_events.csv',index=False)
 z=x[x.eligible]
 print('ALL_STOPS',len(x),'ELIGIBLE',len(z),'coverage',round(len(z)/len(x),4))
 print('OUTCOMES',z.outcome.value_counts().to_dict())
 print('BASE_UNIT_MEAN_PCT',100*z.base_unit.mean(),'POLICY_UNIT_MEAN_PCT',100*z.policy_unit.mean(),'DELTA_PP',100*z.delta_unit.mean())
 print('DELTA_POS_PCT',100*(z.delta_unit>0).mean(),'DELTA_NEG_PCT',100*(z.delta_unit<0).mean())
 print('NOTIONAL_WEIGHTED_DELTA_USDT',float((z.delta_unit*z.notional).sum()))
 print('DELTA_QUANTILES_PCT',(100*z.delta_unit.quantile([0,.1,.25,.5,.75,.9,1])).to_dict())
 # causal time split
 cut=z.stop_ts.quantile(.65)
 for name,g in [('EARLY',z[z.stop_ts<=cut]),('LATE',z[z.stop_ts>cut])]:
  print(name,'n',len(g),'delta_pp',round(100*g.delta_unit.mean(),4),'improve%',round(100*(g.delta_unit>0).mean(),2),'outcomes',g.outcome.value_counts().to_dict())
 # calendar aggregation of actual incremental PnL on baseline entry notional
 z=z.copy(); z['delta_usdt']=z.delta_unit*z.notional; z['month']=z.stop_ts.dt.strftime('%Y-%m')
 print('MONTHLY_DELTA_USDT'); print(z.groupby('month').agg(n=('delta_usdt','size'),delta=('delta_usdt','sum'),mean_pp=('delta_unit',lambda s:100*s.mean())).to_string())
if __name__=='__main__': main()
