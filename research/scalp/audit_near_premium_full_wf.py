from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'
df=pd.read_csv(R/'NEAR_STRONG_SIGNAL_DATASET.csv.gz'); d1=pd.read_csv(ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'); pre=pd.read_csv(R/'BINANCE_NEAR_PREMIUM_5M_360d.csv.gz'); fund=pd.read_csv(R/'BINANCE_NEAR_FUNDING_360d.csv.gz')
pre=pre.sort_values('close_time'); pc=pre.close.astype(float); pre['premium_close']=pc; pre['premium_d1']=pc.diff(); pre['premium_d3']=pc-pc.shift(3); pre['premium_mean3']=pc.rolling(3).mean(); pre['premium_mean12']=pc.rolling(12).mean(); pre['premium_z48']=(pc-pc.rolling(48).mean())/pc.rolling(48).std().replace(0,np.nan); pre['premium_range']=pre.high.astype(float)-pre.low.astype(float)
prem=['premium_close','premium_d1','premium_d3','premium_mean3','premium_mean12','premium_z48','premium_range']; df=pd.merge_asof(df.sort_values('feature_close_time'),pre[['close_time']+prem],left_on='feature_close_time',right_on='close_time',direction='backward').drop(columns='close_time')
fund=fund.sort_values('fundingTime'); fund['fundingRate']=fund.fundingRate.astype(float); fund['funding_d1']=fund.fundingRate.diff(); fund['funding_mean3']=fund.fundingRate.rolling(3).mean(); fund['funding_abs']=fund.fundingRate.abs(); fc=['fundingRate','funding_d1','funding_mean3','funding_abs']; df=pd.merge_asof(df.sort_values('feature_close_time'),fund[['fundingTime']+fc],left_on='feature_close_time',right_on='fundingTime',direction='backward').drop(columns='fundingTime')
base=[c for c in df.columns if c.startswith('m5_')]; df=df.replace([np.inf,-np.inf],np.nan).dropna(subset=base+prem+fc).reset_index(drop=True); print('rows',len(df),flush=True)
# utility TP .2 SL1 H30 fee10
ot=d1.open_time.to_numpy(np.int64); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float); idx=np.searchsorted(ot,df.entry_open_time.to_numpy(np.int64)); ent=df.entry_price.to_numpy(float); y=np.full(len(df),np.nan); stop=np.zeros(len(df),int)
for j,(ii,e) in enumerate(zip(idx,ent)):
 if ii+30>len(d1):continue
 out=None
 for k in range(ii,ii+30):
  if l[k]<=e*.99:out=-.01;stop[j]=1;break
  if h[k]>=e*1.002:out=.002;break
 if out is None:out=c[ii+29]/e-1
 y[j]=out-.001
ok=np.isfinite(y);df=df.loc[ok].reset_index(drop=True);y=y[ok];stop=stop[ok]
groups={'M5':base,'M5_PREM':base+prem,'M5_PREM_FUND':base+prem+fc}; edges=np.linspace(0,len(df),5,dtype=int); rows=[]
for name,cols in groups.items():
 X=df[cols].astype('float32').to_numpy()
 for fold in range(1,4):
  tr=np.arange(edges[0],edges[fold]);te=np.arange(edges[fold],edges[fold+1]);cfg=dict(max_iter=60,max_leaf_nodes=15,l2_regularization=2,learning_rate=.06,random_state=900+fold)
  rg=HistGradientBoostingRegressor(**cfg).fit(X[tr],y[tr]);cl=HistGradientBoostingClassifier(**cfg).fit(X[tr],y[tr]>0);dg=HistGradientBoostingClassifier(**cfg).fit(X[tr],stop[tr])
  prt=rg.predict(X[tr]);ppt=cl.predict_proba(X[tr])[:,1];pr=rg.predict(X[te]);pp=cl.predict_proba(X[te])[:,1];pdg=dg.predict_proba(X[te])[:,1]
  sr=(pr-prt.mean())/(prt.std()+1e-9);sp=(pp-ppt.mean())/(ppt.std()+1e-9);score=.5*sr+.5*sp
  for frac in [.0025,.005,.01,.02]:
   k=max(1,int(len(te)*frac));sel=np.argsort(score)[-k:]
   rows.append(dict(model=name,fold=fold+1,frac=frac,n=k,net_bps=np.mean(y[te][sel])*1e4,win=np.mean(y[te][sel]>0),stop_rate=np.mean(stop[te][sel]),util_auc=roc_auc_score(y[te]>0,pp),danger_auc=roc_auc_score(stop[te],pdg)))
out=pd.DataFrame(rows);out.to_csv(R/'NEAR_PREMIUM_FULL_WF.csv',index=False);print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'),flush=True);print('\nAGG',flush=True)
for (m,f),g in out.groupby(['model','frac']):print(m,f,'n',g.n.sum(),'net',np.average(g.net_bps,weights=g.n),'pos',int((g.net_bps>0).sum()),'worst',g.net_bps.min(),'stop',np.average(g.stop_rate,weights=g.n),flush=True)
