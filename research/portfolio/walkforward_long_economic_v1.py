from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT=Path('/home/kasm920/binance1-pro'); sys.path.insert(0,str(ROOT))
import research.portfolio.validate_long2_doge_v1 as life

SYMBOLS=['SOLUSDT','AVAXUSDT']
FEATURES=['rv60','rv20','ret_6','ema100_slope3','ema100_rel','body_pct','ema10_slope3','ret_60','ema10_rel','ret_mean60','atr14_pct','down_frac20','rv10','ema50_slope3','imb_mean6','ret_3']
FAV=.006; ADV=.0075; H=20
COMMON_START=pd.Timestamp('2025-09-19 20:24:00',tz='UTC'); COMMON_END=pd.Timestamp('2026-09-14 19:20:00',tz='UTC')
FOLDS=[(180,30,30),(210,30,30),(240,30,30),(270,30,None)]; FRACS=[.02,.05,.10,.15,.20]
OUT=ROOT/'research/results/LONG2_ECONOMIC_WALKFORWARD_V1_20261022'; OUT.mkdir(parents=True,exist_ok=True)

def feat(raw):
    d=raw.copy()
    for c in ['open','high','low','close','volume','taker_buy_base_volume']: d[c]=pd.to_numeric(d[c],errors='coerce').astype(float)
    o,h,l,c,v,tb=(d[x] for x in ['open','high','low','close','volume','taker_buy_base_volume']); r=c.pct_change(); f=pd.DataFrame(index=d.index)
    for n in [1,2,3,6,12,20,60,240]: f[f'ret_{n}']=c.pct_change(n)
    f['body_pct']=(c-o)/o; f['range_pct']=(h-l)/c; rng=(h-l).replace(0,np.nan); f['close_loc']=(c-l)/rng
    for span in [5,10,20,50,100]:
        e=c.ewm(span=span,adjust=False).mean(); f[f'ema{span}_rel']=c/e-1.; f[f'ema{span}_slope3']=e/e.shift(3)-1.
    pc=c.shift(1); tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1); f['atr14_pct']=tr.rolling(14).mean()/c
    for w in [10,20,60,240]:
        f[f'rv{w}']=r.rolling(w).std(); mu=v.rolling(w).mean(); sd=v.rolling(w).std().replace(0,np.nan); f[f'vol_z{w}']=(v-mu)/sd
    for w in [10,20,60]: f[f'down_frac{w}']=(r<0).astype(float).rolling(w).mean(); f[f'ret_mean{w}']=r.rolling(w).mean()
    buy=tb/v.replace(0,np.nan); f['imbalance']=2*buy-1.
    for w in [3,6,12,30]: f[f'imb_mean{w}']=f['imbalance'].rolling(w).mean()
    return f[FEATURES].replace([np.inf,-np.inf],np.nan)

def load(sym):
    d3=pd.read_csv(ROOT/f'data/offline_cache/{sym}_3m_360d.csv'); d1=pd.read_csv(ROOT/f'data/offline_cache/{sym}_1m_360d.csv')
    for c in ['open','high','low','close','volume','open_time','close_time','taker_buy_base_volume']: d3[c]=pd.to_numeric(d3[c],errors='coerce')
    for c in ['open','high','low','close','volume','quote_asset_volume','taker_buy_quote_volume']: d1[c]=pd.to_numeric(d1[c],errors='coerce')
    q=d1.quote_asset_volume; b=d1.taker_buy_quote_volume; d1['flow60_prev']=((2*b-q).rolling(60,min_periods=60).sum()/q.rolling(60,min_periods=60).sum()).shift(1)
    f=feat(d3); o=d3.open.to_numpy(float); hi=d3.high.to_numpy(float); lo=d3.low.to_numpy(float); ct=d3.close_time.to_numpy(np.int64)
    rows=np.arange(0,len(d3)-H-1,dtype=int); ei=rows+1; idx=ei[:,None]+np.arange(H)[None,:]; ent=o[ei]
    mfe=np.max(hi[idx]/ent[:,None]-1.,axis=1); mae=np.max(1.-lo[idx]/ent[:,None],axis=1); y=((mfe>=FAV)&(mae<=ADV)).astype(int)
    X=f.iloc[rows].copy(); good=np.isfinite(X.to_numpy(float)).all(axis=1); rows=rows[good]; X=X.loc[good].reset_index(drop=True).to_numpy(float); y=y[good]; score_ts=ct[rows]; label_end=ct[np.minimum(rows+H+1,len(ct)-1)]
    return d1,{'X':X,'y':y,'ct':score_ts,'label_end':label_end}

def model(): return Pipeline([('scale',StandardScaler()),('clf',LogisticRegression(C=.35,penalty='l2',solver='liblinear',max_iter=2000,class_weight='balanced',random_state=42))])

def window_df(d,start,end):
    ts=pd.to_datetime(d.open_time,unit='ms',utc=True); return d[(ts>=start-pd.Timedelta(minutes=65))&(ts<end)].copy().reset_index(drop=True)

def events(scores,ct,d,start,end):
    opens=d.open_time.to_numpy(np.int64); a=int(start.timestamp()*1000); b=int(end.timestamp()*1000); out=[]
    for t,s in zip(ct,scores):
        if t<a or t>=b: continue
        j=int(np.searchsorted(opens,int(t)+1,'left'))
        if j<len(d) and a<=int(d.iloc[j].open_time)<b: out.append((j,float(s),int(d.iloc[j].open_time)))
    return out

def runset(d,ev,thr,seeds=range(1,7)):
    rows=[]
    for seed in seeds:
        s,_=life.run(d,ev,seed,thr,.20); rows.append({'seed':seed,**s})
    return pd.DataFrame(rows)

def main():
    rows=[]
    for sym in SYMBOLS:
        print('\nSYMBOL',sym,flush=True); d1,d=load(sym)
        for fold,(td,vd,xd) in enumerate(FOLDS,1):
            te=COMMON_START+pd.Timedelta(days=td); ve=te+pd.Timedelta(days=vd); xe=COMMON_END if xd is None else min(ve+pd.Timedelta(days=xd),COMMON_END)
            tr=(d['ct']>=int(COMMON_START.timestamp()*1000))&(d['label_end']<int(te.timestamp()*1000)); m=model().fit(d['X'][tr],d['y'][tr]); pall=m.predict_proba(d['X'])[:,1]; ptr=pall[tr]
            dv=window_df(d1,te,ve); evv=events(pall,d['ct'],dv,te,ve); choices=[]
            for frac in FRACS:
                th=float(np.quantile(ptr,1-frac)); z=runset(dv,evv,th,seeds=range(1,4)); tm=z.trades.mean()
                if tm<3: continue
                obj=float(z.return_pct.mean()+.25*z.return_pct.min()+.10*z.dd_pct.mean()); choices.append((obj,z.return_pct.mean(),z.return_pct.min(),z.dd_pct.min(),tm,frac,th))
            if not choices: print('FOLD',fold,'NO_VALID',flush=True); continue
            choices.sort(reverse=True); obj,vm,vmin,vdd,vt,frac,th=choices[0]
            dt=window_df(d1,ve,xe); evt=events(pall,d['ct'],dt,ve,xe); z=runset(dt,evt,th,seeds=range(1,7))
            row={'symbol':sym,'fold':fold,'train_days':td,'top_fraction':frac,'threshold':th,'val_obj':obj,'val_return_mean':vm,'val_return_min':vmin,'val_dd_worst':vdd,'val_trades_mean':vt,'test_return_mean':z.return_pct.mean(),'test_return_min':z.return_pct.min(),'test_return_max':z.return_pct.max(),'test_return_std':z.return_pct.std(),'test_pf_mean':z.pf.replace([np.inf],np.nan).mean(),'test_dd_mean':z.dd_pct.mean(),'test_dd_worst':z.dd_pct.min(),'test_trades_mean':z.trades.mean(),'test_win_mean':z.win_pct.mean(),'positive_test_seeds':int((z.return_pct>0).sum())}
            rows.append(row); print('FOLD_RESULT',row,flush=True)
    R=pd.DataFrame(rows); R.to_csv(OUT/'folds.csv',index=False)
    if len(R):
        A=R.groupby('symbol').agg(folds=('fold','count'),positive_fold_means=('test_return_mean',lambda x:int((x>0).sum())),return_mean=('test_return_mean','mean'),worst_fold_mean=('test_return_mean','min'),worst_seed=('test_return_min','min'),dd_worst=('test_dd_worst','min'),trades_mean=('test_trades_mean','mean'),all_positive_seed_folds=('positive_test_seeds',lambda x:int((x==6).sum()))).reset_index(); A.to_csv(OUT/'summary.csv',index=False); print('\nSUMMARY\n'+A.to_string(index=False),flush=True)
if __name__=='__main__':main()
