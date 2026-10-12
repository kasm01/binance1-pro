from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path('/home/kasm920/binance1-pro'); D=ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz'; OUT=ROOT/'research/results/NEAR_5M15_TWO_HEAD_ECON_WF.csv'
df=pd.read_csv(D)
sets={'M5':[c for c in df if c.startswith('m5_')], 'M5_15':[c for c in df if c.startswith('m5_') or c.startswith('m15_')]}
follow=((df.mfe_10m_pct>=0.20)&(df.mae_10m_pct>=-0.50)&(df.time_to_mfe_10m<=5)).astype(int).to_numpy()
danger=((df.mae_10m_pct<=-0.75)|(df.net_10m_pct<=-0.30)).astype(int).to_numpy()
net=df.net_10m_pct.to_numpy()*100-10; n=len(df); bounds=[.50,.625,.75,.875,1.0]; rows=[]
for name,feat in sets.items():
 X=df[feat].replace([np.inf,-np.inf],np.nan).fillna(0).to_numpy()
 for fi in range(1,4):
  tr_end=int(n*bounds[fi]); te=np.arange(tr_end,int(n*bounds[fi+1])); tr=np.arange(0,tr_end-3)
  mf=HistGradientBoostingClassifier(max_iter=120,max_leaf_nodes=15,learning_rate=.06,l2_regularization=1.0,random_state=10+fi).fit(X[tr],follow[tr])
  md=HistGradientBoostingClassifier(max_iter=120,max_leaf_nodes=15,learning_rate=.06,l2_regularization=1.0,random_state=20+fi).fit(X[tr],danger[tr])
  pf=mf.predict_proba(X[te])[:,1]; pdg=md.predict_proba(X[te])[:,1]; score=pf-pdg
  af=roc_auc_score(follow[te],pf); ad=roc_auc_score(danger[te],pdg)
  for frac in (.02,.05,.10):
   k=max(1,int(len(te)*frac)); loc=np.argsort(score)[-k:]; sel=te[loc]
   rows.append(dict(features=name,fold=fi,frac=frac,n=k,follow_auc=af,danger_auc=ad,follow_rate=follow[sel].mean(),danger_rate=danger[sel].mean(),net_bps=net[sel].mean(),base_bps=net[te].mean()))
r=pd.DataFrame(rows);r.to_csv(OUT,index=False)
for name in sets:
 print('\n',name)
 q=r[r.features==name]
 for frac in (.02,.05,.10):
  z=q[q.frac==frac]; print(frac,'n',z.n.sum(),'follow_auc',z.follow_auc.mean(),'danger_auc',z.danger_auc.mean(),'follow',np.average(z.follow_rate,weights=z.n),'danger',np.average(z.danger_rate,weights=z.n),'net',np.average(z.net_bps,weights=z.n),'pos_folds',int((z.net_bps>0).sum()),'worst',z.net_bps.min())
print('OUT',OUT)
