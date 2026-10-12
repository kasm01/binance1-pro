from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
R=Path('/home/kasm920/binance1-pro'); D=pd.read_csv(R/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz'); K=pd.read_csv(R/'data/offline_cache/NEARUSDT_1m_360d.csv')
for c in ['open_time','close_time']: K[c]=pd.to_numeric(K[c],errors='coerce')
for c in ['open','high','low','close']: K[c]=pd.to_numeric(K[c],errors='coerce')
et=pd.to_numeric(D.entry_open_time,errors='coerce').astype('int64').to_numpy(); ot=K.open_time.astype('int64').to_numpy();
if np.median(et)<1e12: et*=1000
if np.median(ot)<1e12: ot*=1000
idx=np.searchsorted(ot,et); n=len(D); H=15; raw=idx[:,None]+np.arange(H); safe=np.minimum(raw,len(K)-1); entry=D.entry_price.astype(float).to_numpy()[:,None]
hi=K.high.astype(float).to_numpy()[safe]/entry-1; lo=K.low.astype(float).to_numpy()[safe]/entry-1; cl=K.close.astype(float).to_numpy()[safe]/entry-1
f=[c for c in D if c.startswith(('m5_','m3_','m15_'))]; X=D[f].replace([np.inf,-np.inf],np.nan).fillna(0).to_numpy(float)
cuts=[int(n*x) for x in (.50,.625,.75,.875,1)]; fee=.10; rows=[]
for sl in (1.0,1.5):
 tp=.20; tph=hi>=tp/100; slh=lo<=-sl/100; at=tph.any(1); ass=slh.any(1); it=np.where(at,tph.argmax(1),10**6); is_=np.where(ass,slh.argmax(1),10**6)
 stop=(is_<=it)&ass; take=(it<is_)&at; timeout=~stop&~take; yret=np.where(stop,-sl-fee,np.where(take,tp-fee,cl[:,-1]*100-fee))
 cache=[]
 for fold in range(1,5):
  tr_end=cuts[fold-1]; tr=np.arange(0,tr_end-3); te=np.arange(tr_end,cuts[fold]); m=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=15,learning_rate=.05,l2_regularization=2,random_state=7); m.fit(X[tr],stop[tr].astype(int)); p=m.predict_proba(X[te])[:,1]; cache.append((te,p,roc_auc_score(stop[te],p)))
 for keepfrac in (.05,.10,.20,.30,.50):
  fs=[]
  for te,p,auc in cache:
   q=np.quantile(p,keepfrac); sel=te[p<=q]; fs.append((len(sel),yret[sel].mean(),stop[sel].mean(),take[sel].mean(),auc))
  sn=sum(z[0] for z in fs); rows.append(dict(sl_pct=sl,keep_lowrisk_frac=keepfrac,n=sn,net_bps=sum(z[0]*z[1] for z in fs)/sn*100,pos_folds=sum(z[1]>0 for z in fs),worst_fold_bps=min(z[1] for z in fs)*100,stop_rate=sum(z[0]*z[2] for z in fs)/sn,tp_rate=sum(z[0]*z[3] for z in fs)/sn,mean_auc=np.mean([z[4] for z in fs]),min_auc=np.min([z[4] for z in fs])))
out=pd.DataFrame(rows).sort_values('net_bps',ascending=False); out.to_csv(R/'research/results/NEAR_DANGER_HEAD_WF.csv',index=False); print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
