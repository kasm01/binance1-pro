from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz'; D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'; OUT=ROOT/'research/results/NEAR_DANGER_FIRST_NESTED_WF.csv'
df=pd.read_csv(D).replace([np.inf,-np.inf],np.nan).dropna().reset_index(drop=True); d1=pd.read_csv(D1)
feat=[c for c in df if c.startswith('m5_')]; X=df[feat].to_numpy('float32'); ot=d1.open_time.to_numpy(np.int64); hh=d1.high.to_numpy(float); ll=d1.low.to_numpy(float); cc=d1.close.to_numpy(float)
idx=np.searchsorted(ot,df.entry_open_time.to_numpy(np.int64)); e=df.entry_price.to_numpy(float); TP=.002;SL=.01;H=15;FEE=.001
u=np.full(len(df),np.nan);follow=np.zeros(len(df),int);danger=np.zeros(len(df),int);fast=np.zeros(len(df),int)
for j,(ii,ep) in enumerate(zip(idx,e)):
    if ii+H>len(d1):continue
    out=None
    for s,k in enumerate(range(ii,ii+H),start=1):
        if ll[k]<=ep*(1-SL): out=-SL; danger[j]=1; break
        if hh[k]>=ep*(1+TP): out=TP; follow[j]=1; fast[j]=int(s<=3); break
    if out is None: out=cc[ii+H-1]/ep-1
    u[j]=out-FEE
ok=np.isfinite(u); edges=np.linspace(0,len(df),5,dtype=int)

def fit_pred(tr,te,seed):
    kw=dict(max_iter=100,max_leaf_nodes=15,l2_regularization=2.,learning_rate=.06,random_state=seed)
    rg=HistGradientBoostingRegressor(**kw).fit(X[tr],u[tr]); fc=HistGradientBoostingClassifier(**kw).fit(X[tr],follow[tr]); dc=HistGradientBoostingClassifier(**kw).fit(X[tr],danger[tr]); xc=HistGradientBoostingClassifier(**kw).fit(X[tr],fast[tr])
    return rg.predict(X[te]),fc.predict_proba(X[te])[:,1],dc.predict_proba(X[te])[:,1],xc.predict_proba(X[te])[:,1]

def ranks(ref,v):
    s=np.sort(ref); return np.searchsorted(s,v,side='right')/len(s)
rows=[]
for fold in range(1,4):
    outer=np.arange(0,edges[fold]); te=np.arange(edges[fold],edges[fold+1]); outer=outer[ok[outer]]; te=te[ok[te]]
    cut=max(500,int(len(outer)*.75)); sub=outer[:cut]; cal=outer[cut:]
    # calibration model trained only on earlier 75%
    ur,fr,dr,xr=fit_pred(sub,sub,100+fold); uc,fc,dc,xc=fit_pred(sub,cal,100+fold)
    Uc=ranks(ur,uc); Fc=ranks(fr,fc); Dc=ranks(dr,dc); Xc=ranks(xr,xc)
    best=None
    for dq in [.1,.2,.3,.4,.5,.6,.7]:
      for fq in [.5,.6,.7,.8,.9,.95]:
       for uq in [.5,.6,.7,.8,.9,.95]:
        for xq in [0,.5,.7,.8,.9]:
          m=(Dc<=dq)&(Fc>=fq)&(Uc>=uq)&(Xc>=xq); n=int(m.sum())
          if n<75:continue
          val=float(u[cal][m].mean()); score=val-2e-5/np.sqrt(n)
          if best is None or score>best[0]:best=(score,dq,fq,uq,xq,n,val)
    # outer full refit; rank against full-train predictions
    utr,ftr,dtr,xtr=fit_pred(outer,outer,500+fold); ute,fte,dte,xte=fit_pred(outer,te,500+fold)
    if best is None: continue
    _,dq,fq,uq,xq,ncal,vcal=best
    Ut=ranks(utr,ute); Ft=ranks(ftr,fte); Dt=ranks(dtr,dte); Xt=ranks(xtr,xte)
    m=(Dt<=dq)&(Ft>=fq)&(Ut>=uq)&(Xt>=xq); vals=u[te][m]
    rows.append(dict(fold=fold+1,danger_q=dq,follow_q=fq,utility_q=uq,fast_q=xq,cal_n=ncal,cal_net_bps=vcal*1e4,test_n=len(vals),test_net_bps=vals.mean()*1e4 if len(vals) else np.nan,test_win=(vals>0).mean() if len(vals) else np.nan,test_tp=follow[te][m].mean() if len(vals) else np.nan,test_danger=danger[te][m].mean() if len(vals) else np.nan,test_fast=fast[te][m].mean() if len(vals) else np.nan,base_bps=u[te].mean()*1e4))
out=pd.DataFrame(rows);out.to_csv(OUT,index=False);print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
if len(out):
 w=out.test_n;print('WEIGHTED net',np.average(out.test_net_bps,weights=w),'n',w.sum(),'pos_folds',int((out.test_net_bps>0).sum()),'worst',out.test_net_bps.min(),'danger',np.average(out.test_danger,weights=w),'fast',np.average(out.test_fast,weights=w))
print('OUT',OUT)
