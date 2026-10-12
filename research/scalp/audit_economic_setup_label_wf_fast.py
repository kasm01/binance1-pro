from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path('/home/kasm920/binance1-pro')
D=pd.read_csv(ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz')
K=pd.read_csv(ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv')
for c in ['open_time','close_time']: K[c]=pd.to_numeric(K[c],errors='coerce')
for c in ['open','high','low','close']: K[c]=pd.to_numeric(K[c],errors='coerce')
et=pd.to_numeric(D.entry_open_time,errors='coerce').astype('int64').to_numpy(); ot=K.open_time.astype('int64').to_numpy()
if np.nanmedian(et)<1e12: et*=1000
if np.nanmedian(ot)<1e12: ot*=1000
idx=np.searchsorted(ot,et)
valid=(idx<len(K))&(ot[np.minimum(idx,len(K)-1)]==et)
print('rows',len(D),'aligned',int(valid.sum()),flush=True)
# Vectorized future matrices up to 15m
H=15; n=len(D); offs=np.arange(H)
mat_idx=idx[:,None]+offs[None,:]
valid_path=mat_idx<len(K); safe=np.minimum(mat_idx,len(K)-1)
entry=D.entry_price.astype(float).to_numpy()[:,None]
hi=K.high.astype(float).to_numpy()[safe]/entry-1.0
lo=K.low.astype(float).to_numpy()[safe]/entry-1.0
cl=K.close.astype(float).to_numpy()[safe]/entry-1.0
hi[~valid_path]=np.nan; lo[~valid_path]=np.nan; cl[~valid_path]=np.nan
fcols=[c for c in D.columns if c.startswith(('m5_','m3_','m15_'))]
X=D[fcols].replace([np.inf,-np.inf],np.nan).fillna(0).to_numpy(float)
cuts=[int(n*x) for x in (.50,.625,.75,.875,1.0)]
fee=.10 # percentage points = 10 bps
rows=[]
for horizon in (10,15):
  hhi=hi[:,:horizon]; hlo=lo[:,:horizon]; hcl=cl[:,:horizon]
  for sl in (.50,.75,1.00,1.50):
    tp=.20
    tph=hhi>=tp/100.0; slh=hlo<=-sl/100.0
    anytp=np.any(tph,axis=1); anysl=np.any(slh,axis=1)
    itp=np.where(anytp,np.argmax(tph,axis=1),10**6)
    isl=np.where(anysl,np.argmax(slh,axis=1),10**6)
    realized=np.full(n,np.nan)
    # conservative same candle: stop first
    stop=(isl<=itp)&anysl; take=(itp<isl)&anytp
    timeout=~stop&~take
    realized[stop]=-sl-fee; realized[take]=tp-fee
    last=np.sum(np.isfinite(hcl),axis=1)-1; last=np.maximum(last,0)
    tclose=hcl[np.arange(n),last]*100.0-fee
    realized[timeout]=tclose[timeout]
    mask=valid&np.isfinite(realized); y=(realized>0).astype(int)
    foldstats=[]; aucs=[]
    for fold in range(1,5):
      tr_end=cuts[fold-1]; te_start=tr_end; te_end=cuts[fold]
      tr=np.arange(0,max(0,tr_end-3)); te=np.arange(te_start,te_end)
      tr=tr[mask[tr]]; te=te[mask[te]]
      m=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=15,learning_rate=.05,l2_regularization=1.0,random_state=42)
      m.fit(X[tr],y[tr]); p=m.predict_proba(X[te])[:,1]
      auc=roc_auc_score(y[te],p) if len(np.unique(y[te]))>1 else .5; aucs.append(auc)
      q=np.quantile(p,.80); sel=te[p>=q]
      foldstats.append((fold,len(sel),float(np.mean(realized[sel])),float(np.mean(realized[te])),float(np.mean(y[sel]))))
    sn=sum(z[1] for z in foldstats); wp=sum(z[1]*z[2] for z in foldstats)/sn; wb=sum(z[1]*z[3] for z in foldstats)/sn
    rows.append(dict(horizon_min=horizon,tp_pct=tp,sl_pct=sl,base_positive_rate=float(y[mask].mean()),mean_auc=float(np.mean(aucs)),min_auc=float(np.min(aucs)),sel_n=sn,sel_net_bps=wp*100,base_net_bps=wb*100,delta_bps=(wp-wb)*100,pos_folds=sum(z[2]>0 for z in foldstats),worst_fold_bps=min(z[2] for z in foldstats)*100))
out=pd.DataFrame(rows).sort_values(['sel_net_bps','mean_auc'],ascending=False)
out.to_csv(ROOT/'research/results/NEAR_ECON_SETUP_LABEL_WF.csv',index=False)
print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'),flush=True)
