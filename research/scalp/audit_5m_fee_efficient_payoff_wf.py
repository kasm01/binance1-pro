from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
ROOT=Path(__file__).resolve().parents[2]; D=ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz';D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv';OUT=ROOT/'research/results/NEAR_5M_FEE_EFFICIENT_PAYOFF_WF.csv'
df=pd.read_csv(D).replace([np.inf,-np.inf],np.nan).dropna().reset_index(drop=True);d1=pd.read_csv(D1);feat=[c for c in df if c.startswith('m5_')];X=df[feat].to_numpy('float32')
ot=d1.open_time.to_numpy(np.int64);hh=d1.high.to_numpy(float);ll=d1.low.to_numpy(float);cc=d1.close.to_numpy(float);idx=np.searchsorted(ot,df.entry_open_time.to_numpy(np.int64));ep=df.entry_price.to_numpy(float);FEE=.001
edges=np.linspace(0,len(df),5,dtype=int);rows=[]
for TP in [.002,.003,.004]:
 for SL in [.010,.015]:
  for H in [15,30]:
   y=np.full(len(df),np.nan);win=np.zeros(len(df),int)
   for j,(ii,e) in enumerate(zip(idx,ep)):
    if ii+H>len(d1):continue
    out=None
    for k in range(ii,ii+H):
     if ll[k]<=e*(1-SL):out=-SL;break
     if hh[k]>=e*(1+TP):out=TP;win[j]=1;break
    if out is None:out=cc[ii+H-1]/e-1
    y[j]=out-FEE
   ok=np.isfinite(y)
   for fold in range(1,4):
    tr=np.arange(0,edges[fold]);te=np.arange(edges[fold],edges[fold+1]);tr=tr[ok[tr]];te=te[ok[te]]
    kw=dict(max_iter=90,max_leaf_nodes=15,l2_regularization=2.,learning_rate=.06,random_state=700+fold)
    rg=HistGradientBoostingRegressor(**kw).fit(X[tr],y[tr]);cl=HistGradientBoostingClassifier(**kw).fit(X[tr],(y[tr]>0).astype(int))
    prt=rg.predict(X[tr]);ppt=cl.predict_proba(X[tr])[:,1];pr=rg.predict(X[te]);pp=cl.predict_proba(X[te])[:,1]
    def z(v,ref):
      sd=np.std(ref);return (v-np.mean(ref))/(sd if sd>1e-9 else 1)
    best=None
    for a in [0,.25,.5,.75,1.]:
     st=a*z(prt,prt)+(1-a)*z(ppt,ppt)
     for f in [.005,.01,.02,.05]:
      n=max(150,int(len(tr)*f));sel=np.argsort(st)[-n:];val=y[tr][sel].mean()
      if best is None or val>best[0]:best=(val,a,f)
    _,a,f=best;score=a*z(pr,prt)+(1-a)*z(pp,ppt);n=max(1,int(len(te)*f));sel=np.argsort(score)[-n:];v=y[te][sel]
    rows.append(dict(tp_pct=TP*100,sl_pct=SL*100,horizon=H,fold=fold+1,blend=a,top_frac=f,n=n,net_bps=v.mean()*1e4,win_rate=(v>0).mean(),tp_rate=win[te][sel].mean(),base_bps=y[te].mean()*1e4))
out=pd.DataFrame(rows);out.to_csv(OUT,index=False)
agg=[]
for key,g in out.groupby(['tp_pct','sl_pct','horizon']):
 w=g.n;agg.append((*key,int(w.sum()),np.average(g.net_bps,weights=w),int((g.net_bps>0).sum()),g.net_bps.min(),np.average(g.win_rate,weights=w),np.average(g.tp_rate,weights=w),g.top_frac.tolist()))
a=pd.DataFrame(agg,columns=['tp_pct','sl_pct','horizon','n','net_bps','pos_folds','worst','win','tp_rate','fracs']).sort_values('net_bps',ascending=False);print(a.to_string(index=False,float_format=lambda x:f'{x:.4f}'));print('OUT',OUT)
