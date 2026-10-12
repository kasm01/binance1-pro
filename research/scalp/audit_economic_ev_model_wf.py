from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path('/home/kasm920/binance1-pro')
D=pd.read_csv(ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz')
K=pd.read_csv(ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv')
for c in ['open_time','close_time']: K[c]=pd.to_numeric(K[c],errors='coerce')
for c in ['open','high','low','close']: K[c]=pd.to_numeric(K[c],errors='coerce')
et=pd.to_numeric(D.entry_open_time,errors='coerce').astype('int64').to_numpy(); ot=K.open_time.astype('int64').to_numpy()
if np.nanmedian(et)<1e12: et*=1000
if np.nanmedian(ot)<1e12: ot*=1000
idx=np.searchsorted(ot,et); valid=(idx<len(K))&(ot[np.minimum(idx,len(K)-1)]==et)
H=15; n=len(D); raw_idx=idx[:,None]+np.arange(H)[None,:]; safe=np.minimum(raw_idx,len(K)-1); vpath=raw_idx<len(K)
entry=D.entry_price.astype(float).to_numpy()[:,None]
hi=K.high.astype(float).to_numpy()[safe]/entry-1; lo=K.low.astype(float).to_numpy()[safe]/entry-1; cl=K.close.astype(float).to_numpy()[safe]/entry-1
hi[~vpath]=np.nan; lo[~vpath]=np.nan; cl[~vpath]=np.nan
fcols=[c for c in D.columns if c.startswith(('m5_','m3_','m15_'))]
X=D[fcols].replace([np.inf,-np.inf],np.nan).fillna(0).to_numpy(float)
cuts=[int(n*x) for x in (.50,.625,.75,.875,1.0)]; fee=.10
rows=[]
for horizon in (10,15):
 hhi,hlo,hcl=hi[:,:horizon],lo[:,:horizon],cl[:,:horizon]
 for sl in (.50,.75,1.0,1.5):
  tp=.20; tph=hhi>=tp/100; slh=hlo<=-sl/100
  anytp=tph.any(1); anysl=slh.any(1); itp=np.where(anytp,tph.argmax(1),10**6); isl=np.where(anysl,slh.argmax(1),10**6)
  stop=(isl<=itp)&anysl; take=(itp<isl)&anytp; timeout=~stop&~take
  yret=np.full(n,np.nan); yret[stop]=-sl-fee; yret[take]=tp-fee
  last=np.maximum(np.isfinite(hcl).sum(1)-1,0); tclose=hcl[np.arange(n),last]*100-fee; yret[timeout]=tclose[timeout]
  mask=valid&np.isfinite(yret); target=np.clip(yret,-sl-fee,tp-fee)
  fold_cache=[]
  for fold in range(1,5):
    tr_end=cuts[fold-1]; te=np.arange(tr_end,cuts[fold]); tr=np.arange(0,max(0,tr_end-3)); tr=tr[mask[tr]]; te=te[mask[te]]
    r=HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=15,learning_rate=.05,l2_regularization=2.0,random_state=42)
    r.fit(X[tr],target[tr]); pred=r.predict(X[te])
    c=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,learning_rate=.05,l2_regularization=2.0,random_state=43)
    c.fit(X[tr],stop[tr].astype(int)); ps=c.predict_proba(X[te])[:,1]
    auc=roc_auc_score(stop[te].astype(int),ps) if len(np.unique(stop[te]))>1 else .5
    fold_cache.append((te,pred,auc))
  for topfrac in (.05,.10,.20):
    fs=[]; aucs=[]
    for te,pred,auc in fold_cache:
      aucs.append(auc); q=np.quantile(pred,1-topfrac); keep=pred>=q; sel=te[keep]
      fs.append((len(sel),float(np.mean(yret[sel])),float(np.mean(yret[te])),float(stop[sel].mean()),float(take[sel].mean())))
    sn=sum(z[0] for z in fs); net=sum(z[0]*z[1] for z in fs)/sn; base=sum(z[0]*z[2] for z in fs)/sn
    rows.append(dict(horizon_min=horizon,tp_pct=tp,sl_pct=sl,top_frac=topfrac,sel_n=sn,sel_net_bps=net*100,base_net_bps=base*100,delta_bps=(net-base)*100,pos_folds=sum(z[1]>0 for z in fs),worst_fold_bps=min(z[1] for z in fs)*100,stop_rate=sum(z[0]*z[3] for z in fs)/sn,tp_rate=sum(z[0]*z[4] for z in fs)/sn,mean_stop_auc=float(np.mean(aucs)),min_stop_auc=float(np.min(aucs))))
out=pd.DataFrame(rows).sort_values(['sel_net_bps','delta_bps'],ascending=False)
out.to_csv(ROOT/'research/results/NEAR_ECON_EV_MODEL_WF.csv',index=False)
print(out.head(24).to_string(index=False,float_format=lambda x:f'{x:.4f}'),flush=True)
