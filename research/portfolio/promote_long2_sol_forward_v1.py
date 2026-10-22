from __future__ import annotations
from pathlib import Path
import json, sys
import numpy as np
import pandas as pd

ROOT=Path('/home/kasm920/binance1-pro'); sys.path.insert(0,str(ROOT))
from features.pipeline import make_matrix
import research.portfolio.walkforward_long2_lifecycle_v1 as wf

SYM='SOLUSDT'
DATA_START=pd.Timestamp('2025-09-19 20:24:00',tz='UTC')
TRAIN_END=pd.Timestamp('2026-08-15 19:20:00',tz='UTC')
VAL_END=pd.Timestamp('2026-09-14 19:20:00',tz='UTC')
TEST_END=pd.Timestamp('2026-10-11 21:36:00',tz='UTC')
THRESHOLDS=[.500,.525,.550,.575,.600,.625,.650]
OUT=ROOT/'research/results/LONG2_SOL_PROMOTION_FORWARD_V1_20261022'; OUT.mkdir(parents=True,exist_ok=True)

def union(interval):
    parts=[pd.read_csv(ROOT/f'data/offline_cache/{SYM}_{interval}_360d.csv'),pd.read_csv(ROOT/f'research/data/{SYM}_{interval}_1month.csv')]
    d=pd.concat(parts,ignore_index=True).drop_duplicates('open_time').sort_values('open_time').reset_index(drop=True)
    return d

def prep1():
    d=union('1m')
    for c in ('open','high','low','close','volume','quote_asset_volume','taker_buy_quote_volume'):
        d[c]=pd.to_numeric(d[c],errors='coerce')
    q=d.quote_asset_volume; b=d.taker_buy_quote_volume; net=2*b-q
    d['flow60_prev']=(net.rolling(60,min_periods=60).sum()/q.rolling(60,min_periods=60).sum()).shift(1)
    return d

def prep3():
    d=union('3m'); meta=json.loads((ROOT/'models/model_meta_SOLUSDT_3m.json').read_text()); schema=list(meta['feature_schema']); h=int(meta['label_horizon']); thr=float(meta['label_thr'])
    X=make_matrix(d,schema=schema); close=pd.to_numeric(d.close,errors='coerce').to_numpy(float); ct=pd.to_numeric(d.close_time,errors='coerce').to_numpy(np.int64)
    future=np.roll(close,-h); ret=future/np.maximum(close,1e-12)-1.; y=(ret>thr).astype(int); usable=len(d)-h
    X=X[:usable]; y=y[:usable]; ct=ct[:usable]; label_end=ct+h*180000; finite=np.isfinite(X).all(axis=1)
    return {'X':X[finite],'y':y[finite],'ct':ct[finite],'label_end':label_end[finite],'meta':meta}

def summarize(z):
    return {'return_mean':float(z.return_pct.mean()),'return_min':float(z.return_pct.min()),'return_max':float(z.return_pct.max()),'return_std':float(z.return_pct.std()),'pf_mean':float(z.pf.replace([np.inf],np.nan).mean()),'dd_mean':float(z.dd_pct.mean()),'dd_worst':float(z.dd_pct.min()),'trades_mean':float(z.trades.mean()),'win_mean':float(z.win_pct.mean()),'positive_seeds':int((z.return_pct>0).sum())}

def main():
    d1=prep1(); d3=prep3(); tr=(d3['ct']>=int(DATA_START.timestamp()*1000))&(d3['label_end']<int(TRAIN_END.timestamp()*1000)); model=wf.fit_model(d3['X'][tr],d3['y'][tr],d3['meta']); score=model.predict_proba(d3['X'])[:,1]; scored=list(zip(d3['ct'],score))
    dv=wf.window_df(d1,TRAIN_END,VAL_END); evv=wf.scored_to_events(scored,dv,TRAIN_END,VAL_END)
    val_rows=[]
    for th in THRESHOLDS:
        z=wf.run_set(dv,evv,th,seeds=range(1,7)); s=summarize(z); obj=s['return_mean']+.25*s['return_min']+.10*s['dd_mean']; val_rows.append({'threshold':th,'objective':obj,**s})
    V=pd.DataFrame(val_rows); V.to_csv(OUT/'validation_grid.csv',index=False); print('VALIDATION\n'+V.to_string(index=False),flush=True)
    eligible=V[(V.trades_mean>=3)&(V.return_mean>0)&(V.return_min>-2)&(V.dd_worst>-10)&(V.pf_mean>1)].copy()
    if eligible.empty:
        print('PROMOTION NO_DEPLOY reason=no_validation_profile_passed',flush=True); (OUT/'decision.txt').write_text('NO_DEPLOY\n'); return
    best=eligible.sort_values(['objective','return_min','pf_mean'],ascending=False).iloc[0]; th=float(best.threshold); print('PROMOTION PASS threshold',th,'validation',best.to_dict(),flush=True)
    dt=wf.window_df(d1,VAL_END,TEST_END); evt=wf.scored_to_events(scored,dt,VAL_END,TEST_END); test=wf.run_set(dt,evt,th,seeds=range(1,7)); test.to_csv(OUT/'forward_by_seed.csv',index=False); ts=summarize(test); print('FORWARD',ts,flush=True)
    # Forward is audit only; it never changes the preselected threshold.
    decision='SHADOW_CANDIDATE' if (ts['return_mean']>0 and ts['positive_seeds']>=4 and ts['dd_worst']>-10) else 'NO_DEPLOY_FORWARD_FAIL'
    (OUT/'decision.txt').write_text(f'{decision}\nthreshold={th}\nvalidation={best.to_dict()}\nforward={ts}\n')
    print('FINAL_DECISION',decision,flush=True)
if __name__=='__main__': main()
