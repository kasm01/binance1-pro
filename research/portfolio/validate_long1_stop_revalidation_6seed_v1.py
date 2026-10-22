#!/usr/bin/env python3
from pathlib import Path
import pandas as pd,numpy as np
P=Path('/home/kasm920/binance1-pro'); OUT=P/'research/results/STOP_REVALIDATION_V1_20261022'; FEE=.0004; CATA=.035; HOLD=.5; MAX_WAIT=120

def load1m():
 ds=[]
 for fp in [P/'data/offline_cache/NEARUSDT_1m_360d.csv',P/'research/data/NEARUSDT_1m_1month.csv']:
  d=pd.read_csv(fp); d['ts']=pd.to_datetime(d.open_time,unit='ms',utc=True)
  for c in ['open','high','low','close']: d[c]=pd.to_numeric(d[c],errors='coerce')
  ds.append(d[['ts','open','high','low','close']])
 return pd.concat(ds).sort_values('ts').drop_duplicates('ts').reset_index(drop=True)

def run(seed,d):
 t=pd.read_csv(P/f'research/results/LONG1_SINGLE_F60_020_POSITIONS_20261021/seed{seed}.csv'); t['open_ts']=pd.to_datetime(t.entry_ts,utc=True,format='mixed'); t['stop_ts']=pd.to_datetime(t.exit_ts,utc=True,format='mixed'); t=t[t.reason.eq('sl')]; rows=[]
 for r in t.itertuples(index=False):
  ent=float(r.entry_price); bx=float(r.exit_price); base=(bx-ent)/ent-FEE-FEE*(bx/ent); w=d[(d.ts>r.stop_ts)&(d.ts<=r.stop_ts+pd.Timedelta(minutes=MAX_WAIT))]; out='timeout'; x2=bx
  for q in w.itertuples(index=False):
   rec=float(q.high)>=ent; cat=float(q.low)<=ent*(1-CATA)
   if cat and rec: out='cat_same_bar'; x2=ent*(1-CATA); break
   if cat: out='cat'; x2=ent*(1-CATA); break
   if rec: out='recover'; x2=ent; break
   x2=float(q.close)
  first=(bx-ent)/ent-FEE*(bx/ent); residual=(x2-ent)/ent-FEE*(x2/ent); pol=-FEE+(1-HOLD)*first+HOLD*residual
  rows.append(dict(seed=seed,stop_ts=r.stop_ts,outcome=out,delta_unit=pol-base,notional=float(r.notional),delta_usdt=(pol-base)*float(r.notional)))
 return pd.DataFrame(rows)

def main():
 d=load1m(); X=pd.concat([run(s,d) for s in range(1,7)],ignore_index=True); X.to_csv(OUT/'long_policy_6seed_events.csv',index=False)
 A=X.groupby('seed').agg(n=('delta_unit','size'),delta_pp=('delta_unit',lambda s:100*s.mean()),delta_usdt=('delta_usdt','sum'),improve_pct=('delta_unit',lambda s:100*(s>0).mean())).reset_index(); print('BY_SEED'); print(A.to_string(index=False)); print('MEAN_DELTA_PP',A.delta_pp.mean(),'MIN',A.delta_pp.min(),'MEAN_USDT',A.delta_usdt.mean())
 X['day']=X.stop_ts.dt.strftime('%Y-%m-%d'); D=X.groupby(['seed','day']).delta_usdt.sum().reset_index(); DA=D.groupby('day').agg(delta_mean=('delta_usdt','mean'),delta_min=('delta_usdt','min'),delta_max=('delta_usdt','max')).reset_index(); print('DAYS_POS_DELTA',int((DA.delta_mean>0).sum()),'NEG_DELTA',int((DA.delta_mean<0).sum()),'WORST_DAY_DELTA_USDT',DA.delta_mean.min(),'BEST',DA.delta_mean.max()); DA.to_csv(OUT/'long_policy_daily_delta.csv',index=False)
 print('OUTCOMES',X.outcome.value_counts().to_dict())
if __name__=='__main__': main()
