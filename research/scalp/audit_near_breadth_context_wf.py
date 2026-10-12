from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
ROOT=Path(__file__).resolve().parents[2];df=pd.read_csv(ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz').replace([np.inf,-np.inf],np.nan).dropna().reset_index(drop=True);d1=pd.read_csv(ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv')
ALTS=['SOLUSDT','DOGEUSDT','LINKUSDT','AVAXUSDT']
# historical free market breadth on exact 5m close timeline
ctx=pd.DataFrame({'feature_close_time':df.feature_close_time.astype('int64')})
rets=[];rets3=[]
for s in ALTS:
 d=pd.read_csv(ROOT/f'data/offline_cache/{s}_1m_360d.csv');x=d.copy();x['_g']=x.open_time.astype('int64')//300000;a=x.groupby('_g',sort=True).agg(close=('close','last'),close_time=('close_time','last')).reset_index(drop=True);c=a.close.astype(float);z=pd.DataFrame({'feature_close_time':a.close_time.astype('int64'),f'{s}_r1':c.pct_change(),f'{s}_r3':c.pct_change(3)});ctx=ctx.merge(z,on='feature_close_time',how='left');rets.append(f'{s}_r1');rets3.append(f'{s}_r3')
ctx['mkt_ret1_mean']=ctx[rets].mean(axis=1);ctx['mkt_ret1_median']=ctx[rets].median(axis=1);ctx['mkt_ret3_mean']=ctx[rets3].mean(axis=1);ctx['breadth_up1']=(ctx[rets]>0).mean(axis=1);ctx['breadth_up3']=(ctx[rets3]>0).mean(axis=1);ctx['dispersion1']=ctx[rets].std(axis=1);ctx['mkt_abs1']=ctx[rets].abs().mean(axis=1);ctx['near_rel1']=df.m5_ret1.to_numpy()-ctx.mkt_ret1_mean.to_numpy();ctx['near_rel3']=df.m5_ret3.to_numpy()-ctx.mkt_ret3_mean.to_numpy();bread=['mkt_ret1_mean','mkt_ret1_median','mkt_ret3_mean','breadth_up1','breadth_up3','dispersion1','mkt_abs1','near_rel1','near_rel3']
df=pd.concat([df,ctx[bread]],axis=1).replace([np.inf,-np.inf],np.nan).dropna().reset_index(drop=True)
ot=d1.open_time.to_numpy(np.int64);hh=d1.high.to_numpy(float);ll=d1.low.to_numpy(float);cc=d1.close.to_numpy(float);idx=np.searchsorted(ot,df.entry_open_time.to_numpy(np.int64));ep=df.entry_price.to_numpy(float);FEE=.001;edges=np.linspace(0,len(df),5,dtype=int)
configs=[('LONG',.002,.010,30),('SHORT',.004,.015,15)];rows=[]
for side,TP,SL,H in configs:
 y=np.full(len(df),np.nan)
 for j,(ii,e) in enumerate(zip(idx,ep)):
  if ii+H>len(d1):continue
  out=None
  for k in range(ii,ii+H):
   if side=='LONG':
    if ll[k]<=e*(1-SL):out=-SL;break
    if hh[k]>=e*(1+TP):out=TP;break
   else:
    if hh[k]>=e*(1+SL):out=-SL;break
    if ll[k]<=e*(1-TP):out=TP;break
  if out is None:out=(cc[ii+H-1]/e-1)*(1 if side=='LONG' else -1)
  y[j]=out-FEE
 ok=np.isfinite(y)
 for model in ['M5','M5_BREADTH']:
  feat=[c for c in df if c.startswith('m5_')]+(bread if model=='M5_BREADTH' else []);X=df[feat].to_numpy('float32')
  for fold in range(1,4):
   tr=np.arange(0,edges[fold]);te=np.arange(edges[fold],edges[fold+1]);tr=tr[ok[tr]];te=te[ok[te]];kw=dict(max_iter=90,max_leaf_nodes=15,l2_regularization=2.,learning_rate=.06,random_state=1500+fold)
   rg=HistGradientBoostingRegressor(**kw).fit(X[tr],y[tr]);cl=HistGradientBoostingClassifier(**kw).fit(X[tr],(y[tr]>0).astype(int));prt=rg.predict(X[tr]);ppt=cl.predict_proba(X[tr])[:,1];pr=rg.predict(X[te]);pp=cl.predict_proba(X[te])[:,1]
   def z(v,r):
    sd=np.std(r);return (v-np.mean(r))/(sd if sd>1e-9 else 1)
   best=None
   for a in [0,.25,.5,.75,1.]:
    st=a*z(prt,prt)+(1-a)*z(ppt,ppt)
    for f in [.005,.01,.02,.05]:
     n=max(150,int(len(tr)*f));sel=np.argsort(st)[-n:];val=y[tr][sel].mean()
     if best is None or val>best[0]:best=(val,a,f)
   _,a,f=best;sc=a*z(pr,prt)+(1-a)*z(pp,ppt);n=max(1,int(len(te)*f));sel=np.argsort(sc)[-n:];v=y[te][sel];rows.append(dict(side=side,model=model,fold=fold+1,n=n,blend=a,frac=f,net_bps=v.mean()*1e4,win=(v>0).mean(),base_bps=y[te].mean()*1e4))
out=pd.DataFrame(rows);out.to_csv(ROOT/'research/results/NEAR_BREADTH_CONTEXT_WF.csv',index=False);print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'));print('\nAGG')
for k,g in out.groupby(['side','model']):print(k,'n',g.n.sum(),'net',np.average(g.net_bps,weights=g.n),'pos',int((g.net_bps>0).sum()),'worst',g.net_bps.min())
