from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz'; D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_5M_LIFECYCLE_UTILITY_WF.csv'
df=pd.read_csv(D).replace([np.inf,-np.inf],np.nan).dropna().reset_index(drop=True)
d1=pd.read_csv(D1)
feat=[c for c in df.columns if c.startswith('m5_')]
X=df[feat].astype('float32').to_numpy(); ot=d1.open_time.to_numpy(np.int64); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
entry_t=df.entry_open_time.to_numpy(np.int64); entry=df.entry_price.to_numpy(float)
idx=np.searchsorted(ot,entry_t)
TP=0.002; H=15; FEE=0.001 # 10 bps round trip
stops=[0.005,0.0075,0.010,0.015]
# realized net return decimal after fee, conservative same-candle SL first
util={}; win={}
for sl in stops:
    y=np.full(len(df),np.nan); w=np.zeros(len(df),int)
    for j,(ii,e) in enumerate(zip(idx,entry)):
        if ii<0 or ii+H>len(d1) or e<=0: continue
        out=None
        for k in range(ii,ii+H):
            slhit=l[k]<=e*(1-sl); tphit=h[k]>=e*(1+TP)
            if slhit: out=-sl; break
            if tphit: out=TP; w[j]=1; break
        if out is None: out=c[ii+H-1]/e-1.0
        y[j]=out-FEE
    util[sl]=y; win[sl]=w
edges=np.linspace(0,len(df),5,dtype=int); rows=[]
for sl in stops:
  y=util[sl]; w=win[sl]; ok=np.isfinite(y)
  for fold in range(1,4):
    tr=np.arange(0,edges[fold]); te=np.arange(edges[fold],edges[fold+1]); tr=tr[ok[tr]]; te=te[ok[te]]
    common=dict(max_iter=120,max_leaf_nodes=15,l2_regularization=2.0,learning_rate=0.06,random_state=400+fold)
    rg=HistGradientBoostingRegressor(**common).fit(X[tr],y[tr])
    cl=HistGradientBoostingClassifier(**common).fit(X[tr],(y[tr]>0).astype(int))
    pr=rg.predict(X[te]); pp=cl.predict_proba(X[te])[:,1]
    prt=rg.predict(X[tr]); ppt=cl.predict_proba(X[tr])[:,1]
    # choose score blend and fraction on train only
    def z(v):
      s=np.std(v); return (v-np.mean(v))/(s if s>1e-9 else 1)
    zrt=z(prt); zpt=z(ppt)
    blends=[0,0.25,0.5,0.75,1.0]; fracs=[.01,.02,.05,.10,.20]
    best=None
    for a in blends:
      st=a*zrt+(1-a)*zpt
      for f in fracs:
        k=max(250,int(len(tr)*f)); sel=np.argsort(st)[-k:]; val=float(np.mean(y[tr][sel]))
        if best is None or val>best[0]: best=(val,a,f)
    _,a,f=best
    sr=(pr-np.mean(prt))/(np.std(prt) if np.std(prt)>1e-9 else 1)
    sp=(pp-np.mean(ppt))/(np.std(ppt) if np.std(ppt)>1e-9 else 1)
    score=a*sr+(1-a)*sp; k=max(1,int(len(te)*f)); sel=np.argsort(score)[-k:]
    auc=roc_auc_score((y[te]>0).astype(int),pp)
    rows.append(dict(sl_pct=sl*100,fold=fold+1,blend_reg=a,top_frac=f,n=len(sel),auc=auc,win_rate=float((y[te][sel]>0).mean()),tp_rate=float(w[te][sel].mean()),net_bps=float(np.mean(y[te][sel])*10000),base_bps=float(np.mean(y[te])*10000)))
out=pd.DataFrame(rows); out.to_csv(OUT,index=False)
print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
print('\nAGG')
for sl,g in out.groupby('sl_pct'):
 print('SL',sl,'n',g.n.sum(),'net',np.average(g.net_bps,weights=g.n),'base',np.average(g.base_bps,weights=g.n),'pos_folds',int((g.net_bps>0).sum()),'worst',g.net_bps.min(),'auc',g.auc.mean(),'blend',g.blend_reg.tolist(),'frac',g.top_frac.tolist())
print('OUT',OUT)
