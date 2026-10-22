from __future__ import annotations
from pathlib import Path
import json, sys
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier

ROOT=Path('/home/kasm920/binance1-pro'); sys.path.insert(0,str(ROOT))
from features.pipeline import make_matrix
import research.portfolio.validate_long2_doge_v1 as life

SYMBOLS=['LINKUSDT','SOLUSDT']
COMMON_START=pd.Timestamp('2025-09-19 20:24:00',tz='UTC')
COMMON_END=pd.Timestamp('2026-09-14 19:20:00',tz='UTC')
FOLDS=[(180,30,30),(210,30,30),(240,30,30),(270,30,None)]
THRESHOLDS=[.500,.525,.550,.575,.600]
OUT=ROOT/'research/results/LONG2_CAUSAL_WALKFORWARD_LINK_SOL_V1_20261022'; OUT.mkdir(parents=True,exist_ok=True)

def load_1m(sym):
    d=pd.read_csv(ROOT/f'data/offline_cache/{sym}_1m_360d.csv')
    for c in ('open','high','low','close','volume','quote_asset_volume','taker_buy_quote_volume'):
        d[c]=pd.to_numeric(d[c],errors='coerce')
    q=d.quote_asset_volume; b=d.taker_buy_quote_volume; net=2*b-q
    d['flow60_prev']=(net.rolling(60,min_periods=60).sum()/q.rolling(60,min_periods=60).sum()).shift(1)
    return d

def load_3m(sym):
    d=pd.read_csv(ROOT/f'data/offline_cache/{sym}_3m_360d.csv')
    meta=json.loads((ROOT/f'models/model_meta_{sym}_3m.json').read_text())
    schema=list(meta['feature_schema']); h=int(meta['label_horizon']); label_thr=float(meta['label_thr'])
    X=make_matrix(d,schema=schema)
    close=pd.to_numeric(d.close,errors='coerce').to_numpy(float); ct=pd.to_numeric(d.close_time,errors='coerce').to_numpy(np.int64)
    future=np.roll(close,-h); ret=future/np.maximum(close,1e-12)-1.; y=(ret>label_thr).astype(int); usable=len(d)-h
    X=X[:usable]; y=y[:usable]; ct=ct[:usable]; label_end=ct+h*180000
    finite=np.isfinite(X).all(axis=1)
    return {'X':X[finite],'y':y[finite],'ct':ct[finite],'label_end':label_end[finite],'meta':meta}

def fit_model(X,y,meta):
    n0=max(int((y==0).sum()),1); n1=max(int((y==1).sum()),1); sw=np.where(y==1,.5/n1,.5/n0)
    model=Pipeline([('scaler',StandardScaler()),('sgd',SGDClassifier(loss='log_loss',penalty='l2',alpha=float(meta.get('sgd_alpha',1e-4)),max_iter=int(meta.get('sgd_max_iter',50)),tol=float(meta.get('sgd_tol',.001)),shuffle=bool(meta.get('sgd_shuffle',False)),random_state=42,n_jobs=-1))])
    model.fit(X,y,sgd__sample_weight=sw); return model

def window_df(d,start,end):
    ts=pd.to_datetime(d.open_time,unit='ms',utc=True)
    pre=start-pd.Timedelta(minutes=65)
    return d[(ts>=pre)&(ts<end)].copy().reset_index(drop=True)

def scored_to_events(scored, d, start, end):
    opens=d.open_time.to_numpy(np.int64); a=int(start.timestamp()*1000); b=int(end.timestamp()*1000); out=[]
    for ct,score in scored:
        if ct<a or ct>=b: continue
        j=int(np.searchsorted(opens,int(ct)+1,'left'))
        if j<len(d):
            oms=int(d.iloc[j].open_time)
            if a<=oms<b: out.append((j,float(score),oms))
    return out

def run_set(d,events,threshold,seeds=range(1,7)):
    rows=[]
    for seed in seeds:
        s,_=life.run(d,events,seed,threshold,.20); rows.append({'seed':seed,**s})
    return pd.DataFrame(rows)

def main():
    rows=[]
    for sym in SYMBOLS:
        print('\nSYMBOL',sym,flush=True); d1=load_1m(sym); d3=load_3m(sym)
        for fold,(train_days,val_days,test_days) in enumerate(FOLDS,1):
            train_end=COMMON_START+pd.Timedelta(days=train_days); val_end=train_end+pd.Timedelta(days=val_days); test_end=COMMON_END if test_days is None else min(val_end+pd.Timedelta(days=test_days),COMMON_END)
            tr=(d3['ct']>=int(COMMON_START.timestamp()*1000))&(d3['label_end']<int(train_end.timestamp()*1000))
            model=fit_model(d3['X'][tr],d3['y'][tr],d3['meta']); scores=model.predict_proba(d3['X'])[:,1]
            scored=list(zip(d3['ct'],scores))
            dv=window_df(d1,train_end,val_end); evv=scored_to_events(scored,dv,train_end,val_end)
            choices=[]
            for th in THRESHOLDS:
                z=run_set(dv,evv,th,seeds=range(1,4)); tm=z.trades.mean()
                if tm<3: continue
                # Conservative validation objective; rewards return but penalizes path instability and DD.
                obj=float(z.return_pct.mean()+0.25*z.return_pct.min()+0.10*z.dd_pct.mean())
                choices.append((obj,float(z.return_pct.mean()),float(z.return_pct.min()),float(z.dd_pct.mean()),float(tm),th))
            if not choices:
                print('FOLD',fold,'NO_VALID_THRESHOLD',flush=True); continue
            choices.sort(reverse=True); obj,vmean,vmin,vdd,vt,th=choices[0]
            dt=window_df(d1,val_end,test_end); evt=scored_to_events(scored,dt,val_end,test_end); test=run_set(dt,evt,th,seeds=range(1,7))
            row={'symbol':sym,'fold':fold,'train_days':train_days,'train_end':train_end,'val_end':val_end,'test_end':test_end,'threshold':th,'val_obj':obj,'val_return_mean':vmean,'val_return_min':vmin,'val_dd_mean':vdd,'val_trades_mean':vt,'test_return_mean':test.return_pct.mean(),'test_return_min':test.return_pct.min(),'test_return_max':test.return_pct.max(),'test_return_std':test.return_pct.std(),'test_pf_mean':test.pf.replace([np.inf],np.nan).mean(),'test_dd_mean':test.dd_pct.mean(),'test_dd_worst':test.dd_pct.min(),'test_trades_mean':test.trades.mean(),'test_win_mean':test.win_pct.mean(),'positive_test_seeds':int((test.return_pct>0).sum())}
            rows.append(row); print('FOLD_RESULT',row,flush=True)
    R=pd.DataFrame(rows); R.to_csv(OUT/'folds.csv',index=False)
    if len(R):
        A=R.groupby('symbol').agg(folds=('fold','count'),positive_fold_means=('test_return_mean',lambda x:int((x>0).sum())),return_mean=('test_return_mean','mean'),return_median=('test_return_mean','median'),worst_fold_mean=('test_return_mean','min'),worst_seed=('test_return_min','min'),pf_mean=('test_pf_mean','mean'),dd_mean=('test_dd_mean','mean'),dd_worst=('test_dd_worst','min'),trades_mean=('test_trades_mean','mean'),all_positive_seed_folds=('positive_test_seeds',lambda x:int((x==6).sum()))).reset_index()
        A.to_csv(OUT/'summary.csv',index=False); print('\nSUMMARY\n'+A.to_string(index=False),flush=True)
if __name__=='__main__': main()
