#!/usr/bin/env python3
from pathlib import Path
import pandas as pd, numpy as np
P=Path('/home/kasm920/binance1-pro'); OUT=P/'research/results/STOP_REVALIDATION_V1_20261022'; OUT.mkdir(parents=True,exist_ok=True)
FEE=.0004; HOLD=.50; CATA=.035; MAX_WAIT=120

def load1m():
 ds=[]
 for fp in [P/'data/offline_cache/NEARUSDT_1m_360d.csv',P/'research/data/NEARUSDT_1m_1month.csv']:
  d=pd.read_csv(fp); d['ts']=pd.to_datetime(d.open_time,unit='ms',utc=True)
  for c in ['open','high','low','close']: d[c]=pd.to_numeric(d[c],errors='coerce')
  ds.append(d[['ts','open','high','low','close']])
 return pd.concat(ds).sort_values('ts').drop_duplicates('ts').reset_index(drop=True)

def main():
 d=load1m(); t=pd.read_csv(P/'research/results/LONG1_SINGLE_F60_020_POSITIONS_20261021/seed1.csv'); t['open_ts']=pd.to_datetime(t.entry_ts,utc=True,format='mixed'); t['stop_ts']=pd.to_datetime(t.exit_ts,utc=True,format='mixed'); t=t[t.reason.eq('sl')]
 rows=[]
 for r in t.itertuples(index=False):
  ent=float(r.entry_price); base_exit=float(r.exit_price); base=(base_exit-ent)/ent-FEE-FEE*(base_exit/ent)
  w=d[(d.ts>r.stop_ts)&(d.ts<=r.stop_ts+pd.Timedelta(minutes=MAX_WAIT))]; out='timeout'; exit2=base_exit; wait=0
  for q in w.itertuples(index=False):
   rec=float(q.high)>=ent; cat=float(q.low)<=ent*(1-CATA); wait=(q.ts-r.stop_ts).total_seconds()/60
   if cat and rec: out='cat_same_bar'; exit2=ent*(1-CATA); break
   if cat: out='cat'; exit2=ent*(1-CATA); break
   if rec: out='recover'; exit2=ent; break
   exit2=float(q.close)
  first=(base_exit-ent)/ent-FEE*(base_exit/ent); residual=(exit2-ent)/ent-FEE*(exit2/ent)
  pol=-FEE+(1-HOLD)*first+HOLD*residual
  rows.append(dict(open_ts=r.open_ts,stop_ts=r.stop_ts,age_min=(r.stop_ts-r.open_ts).total_seconds()/60,outcome=out,wait_min=wait,base_unit=base,policy_unit=pol,delta_unit=pol-base,notional=float(r.notional)))
 x=pd.DataFrame(rows); x.to_csv(OUT/'long_policy_events.csv',index=False)
 print('N',len(x),'OUTCOMES',x.outcome.value_counts().to_dict())
 print('BASE_MEAN_PCT',100*x.base_unit.mean(),'POLICY_MEAN_PCT',100*x.policy_unit.mean(),'DELTA_PP',100*x.delta_unit.mean())
 print('IMPROVE_PCT',100*(x.delta_unit>0).mean(),'WORSE_PCT',100*(x.delta_unit<0).mean(),'WEIGHTED_DELTA_USDT',float((x.delta_unit*x.notional).sum()))
 print('QUANTILES_PCT',(100*x.delta_unit.quantile([0,.1,.25,.5,.75,.9,1])).to_dict())
 cut=x.stop_ts.quantile(.65)
 for name,g in [('EARLY',x[x.stop_ts<=cut]),('LATE',x[x.stop_ts>cut])]: print(name,'n',len(g),'delta_pp',round(100*g.delta_unit.mean(),4),'improve%',round(100*(g.delta_unit>0).mean(),2),'outcomes',g.outcome.value_counts().to_dict())
if __name__=='__main__': main()
