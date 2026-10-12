from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import roc_auc_score

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'data/offline_cache/NEARUSDT_5m_360d.csv'
OUT=ROOT/'research/results/NEAR_PRIMARY_5M_MODEL_WF.csv'
FEE=0.0010

def feats(df):
    x=df.copy()
    if 'ignore' not in x.columns: x['ignore']=0.0
    for c in ['open','high','low','close','volume','quote_asset_volume','number_of_trades','ignore','taker_buy_base_volume','taker_buy_quote_volume']:
        x[c]=pd.to_numeric(x[c],errors='coerce').fillna(0.0)
    c=x.close.astype(float)
    x['hl_range']=x.high-x.low; x['oc_change']=x.close-x.open
    x['return_1']=c.pct_change(1); x['return_3']=c.pct_change(3); x['return_5']=c.pct_change(5)
    x['ma_5']=c.rolling(5).mean(); x['ma_10']=c.rolling(10).mean(); x['ma_20']=c.rolling(20).mean()
    x['vol_10']=x.volume.astype(float).rolling(10).mean(); x['dummy_extra']=0.0
    cols=['open','high','low','close','volume','quote_asset_volume','number_of_trades','ignore','taker_buy_base_volume','taker_buy_quote_volume','hl_range','oc_change','return_1','return_3','return_5','ma_5','ma_10','ma_20','vol_10','dummy_extra']
    return x[cols].replace([np.inf,-np.inf],np.nan)

d=pd.read_csv(SRC).sort_values('open_time').reset_index(drop=True)
Xdf=feats(d); close=d.close.astype(float)
rows=[]
for H in [1,2,3]:
  fret=close.shift(-H)/close-1
  for thr in [0.0005,0.0010,0.0015]:
    y=(fret>thr).astype(int)
    valid=Xdf.notna().all(axis=1)&fret.notna()
    X=Xdf.loc[valid].to_numpy(float); yy=y.loc[valid].to_numpy(int); rr=fret.loc[valid].to_numpy(float); n=len(X)
    # Expanding train -> next-quarter test. Purge H bars at train end.
    for fold,(trf,tef) in enumerate([(0.50,0.625),(0.625,0.75),(0.75,0.875),(0.875,1.0)],1):
      tr_end=max(100,int(n*trf)-H); te_end=int(n*tef); te_start=int(n*trf)
      m=Pipeline([('scaler',StandardScaler()),('sgd',SGDClassifier(loss='log_loss',alpha=1e-4,max_iter=200,tol=1e-3,shuffle=False,random_state=42))])
      m.fit(X[:tr_end],yy[:tr_end]); p=m.predict_proba(X[te_start:te_end])[:,1]; yt=yy[te_start:te_end]; rt=rr[te_start:te_end]
      auc=roc_auc_score(yt,p) if len(np.unique(yt))>1 else np.nan
      cut=np.quantile(p,.80); sel=p>=cut
      net=(rt[sel]-FEE) if sel.any() else np.array([])
      rows.append(dict(horizon_5m=H,thr=thr,fold=fold,n_test=len(p),auc=auc,selected=int(sel.sum()),sel_rate=float(sel.mean()),selected_gross_bps=float(rt[sel].mean()*1e4) if sel.any() else np.nan,selected_net_bps=float(net.mean()*1e4) if len(net) else np.nan,selected_win_net=float((net>0).mean()) if len(net) else np.nan,base_net_bps=float((rt-FEE).mean()*1e4)))
r=pd.DataFrame(rows); r.to_csv(OUT,index=False)
print('===== AGGREGATE =====')
a=r.groupby(['horizon_5m','thr']).agg(mean_auc=('auc','mean'),min_auc=('auc','min'),sel_n=('selected','sum'),sel_net_bps=('selected_net_bps','mean'),pos_folds=('selected_net_bps',lambda x:int((x>0).sum())),worst_fold_bps=('selected_net_bps','min'),base_net_bps=('base_net_bps','mean')).reset_index()
print(a.round(4).sort_values(['sel_net_bps','mean_auc'],ascending=False).to_string(index=False))
print('OUTPUT',OUT)
