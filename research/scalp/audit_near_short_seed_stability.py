from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
ROOT=Path(__file__).resolve().parents[2];df=pd.read_csv(ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz').replace([np.inf,-np.inf],np.nan).dropna().reset_index(drop=True);d1=pd.read_csv(ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv')
feat=[c for c in df if c.startswith('m5_')];X=df[feat].to_numpy('float32');ot=d1.open_time.to_numpy(np.int64);hh=d1.high.to_numpy(float);ll=d1.low.to_numpy(float);cc=d1.close.to_numpy(float);idx=np.searchsorted(ot,df.entry_open_time.to_numpy(np.int64));ep=df.entry_price.to_numpy(float);TP=.004;SL=.015;H=15;FEE=.001
y=np.full(len(df),np.nan);w=np.zeros(len(df),int)
for j,(ii,e) in enumerate(zip(idx,ep)):
 if ii+H>len(d1):continue
 out=None
 for k in range(ii,ii+H):
  if hh[k]>=e*(1+SL):out=-SL;break
  if ll[k]<=e*(1-TP):out=TP;w[j]=1;break
 if out is None:out=-(cc[ii+H-1]/e-1)
 y[j]=out-FEE
ok=np.isfinite(y);edges=np.linspace(0,len(df),5,dtype=int);rows=[]
for seed0 in [100,300,500,700,900,1100,1300]:
 for fold in range(1,4):
  tr=np.arange(0,edges[fold]);te=np.arange(edges[fold],edges[fold+1]);tr=tr[ok[tr]];te=te[ok[te]];kw=dict(max_iter=80,max_leaf_nodes=15,l2_regularization=2.,learning_rate=.06,random_state=seed0+fold)
  rg=HistGradientBoostingRegressor(**kw).fit(X[tr],y[tr]);cl=HistGradientBoostingClassifier(**kw).fit(X[tr],(y[tr]>0).astype(int));prt=rg.predict(X[tr]);ppt=cl.predict_proba(X[tr])[:,1];pr=rg.predict(X[te]);pp=cl.predict_proba(X[te])[:,1]
  def z(v,r):
   sd=np.std(r);return (v-np.mean(r))/(sd if sd>1e-9 else 1)
  best=None
  for a in [0,.25,.5,.75,1.]:
   st=a*z(prt,prt)+(1-a)*z(ppt,ppt)
   for f in [.005,.01,.02,.05]:
    n=max(150,int(len(tr)*f));sel=np.argsort(st)[-n:];val=y[tr][sel].mean()
    if best is None or val>best[0]:best=(val,a,f)
  _,a,f=best;sc=a*z(pr,prt)+(1-a)*z(pp,ppt);n=max(1,int(len(te)*f));sel=np.argsort(sc)[-n:];v=y[te][sel];rows.append(dict(seed=seed0,fold=fold+1,n=n,blend=a,frac=f,net_bps=v.mean()*1e4,tp=w[te][sel].mean()))
out=pd.DataFrame(rows);print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'));print('\nSEEDS')
for s,g in out.groupby('seed'):print(s,'net',np.average(g.net_bps,weights=g.n),'pos',int((g.net_bps>0).sum()),'worst',g.net_bps.min(),'n',g.n.sum())
out.to_csv(ROOT/'research/results/NEAR_SHORT_SEED_STABILITY.csv',index=False)
