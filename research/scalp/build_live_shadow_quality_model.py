from pathlib import Path
import json, joblib
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_LIVE_SHADOW_QUALITY_MODEL.joblib'
META=ROOT/'research/results/NEAR_LIVE_SHADOW_QUALITY_MODEL_META.json'
TP,SL,H=.0025,.0050,10

def mdl(seed):
 return HistGradientBoostingClassifier(learning_rate=.05,max_iter=200,max_leaf_nodes=15,min_samples_leaf=150,l2_regularization=5.,early_stopping=False,random_state=seed)

ds=pd.read_csv(DATA).sort_values('feature_close_time').reset_index(drop=True)
feat=[c for c in ds.columns if c.startswith(('m3_','m5_','m15_'))]
d1=pd.read_csv(D1); ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float)
yf=np.zeros(len(ds),int); yd=np.zeros(len(ds),int)
for i,r in ds.iterrows():
 j=int(np.searchsorted(ot,int(r.entry_open_time),side='left')); e=o[j]
 for k in range(H):
  jj=j+k
  if l[jj]/e-1<=-SL: yd[i]=1; break
  if h[jj]/e-1>=TP: yf[i]=1; break
X=ds[feat].to_numpy(float); n=len(ds)
a=int(n*.85); b=int(n*.925)
mf,md=mdl(42),mdl(43); mf.fit(X[:a],yf[:a]); md.fit(X[:a],yd[:a])
qcal=mf.predict_proba(X[a:b])[:,1]-md.predict_proba(X[a:b])[:,1]
q80,q90=np.quantile(qcal,[.80,.90])
qv=mf.predict_proba(X[b:])[:,1]-md.predict_proba(X[b:])[:,1]
# diagnostic: follow vs danger only, ignore HOLD for AUC
mask=(yf[b:]+yd[b:])>0
y=(yf[b:][mask]==1).astype(int); qd=qv[mask]
auc=roc_auc_score(y,qd) if len(np.unique(y))>1 else None
sel=(qv>=q80)&(qv<=q90)
meta={'schema_version':1,'symbol':'NEARUSDT','feature_count':len(feat),'features':feat,'train_end_idx':a,'cal_end_idx':b,'n_total':n,'q80':float(q80),'q90':float(q90),'validation_n':int(len(qv)),'validation_band_n':int(sel.sum()),'validation_follow_rate':float(yf[b:][sel].mean()) if sel.any() else None,'validation_danger_rate':float(yd[b:][sel].mean()) if sel.any() else None,'validation_auc_follow_vs_danger':None if auc is None else float(auc),'train_last_feature_close_time':int(ds.feature_close_time.iloc[a-1]),'cal_last_feature_close_time':int(ds.feature_close_time.iloc[b-1]),'data_last_feature_close_time':int(ds.feature_close_time.iloc[-1]),'shadow_only':True}
joblib.dump({'follow_model':mf,'danger_model':md,'features':feat,'q80':float(q80),'q90':float(q90),'meta':meta},OUT)
META.write_text(json.dumps(meta,indent=2))
print(json.dumps({k:v for k,v in meta.items() if k!='features'},indent=2)); print('OUT',OUT)
