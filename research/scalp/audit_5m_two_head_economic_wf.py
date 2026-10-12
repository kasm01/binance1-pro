from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path('/home/kasm920/binance1-pro')
D=ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz'
OUT=ROOT/'research/results/NEAR_5M_TWO_HEAD_ECON_WF.csv'
df=pd.read_csv(D)
feat=[c for c in df.columns if c.startswith('m5_')]
X=df[feat].replace([np.inf,-np.inf],np.nan).fillna(0.0).to_numpy()
# economic labels based on 10m path, percent-point columns
# FOLLOW: fast +0.20% excursion with controlled MAE and <=5m time-to-MFE
follow=((df.mfe_10m_pct>=0.20)&(df.mae_10m_pct>=-0.50)&(df.time_to_mfe_10m<=5)).astype(int).to_numpy()
# DANGER: large adverse excursion or bad 10m close
danger=((df.mae_10m_pct<=-0.75)|(df.net_10m_pct<=-0.30)).astype(int).to_numpy()
# fee-adjusted proxy return from 10m close at 10bps RT (decimal pct points -> bps x100)
net_bps=df.net_10m_pct.to_numpy()*100.0 - 10.0
n=len(df)
# anchored walk-forward folds
bounds=[0.50,0.625,0.75,0.875,1.0]
rows=[]
for fi in range(1,4):
    tr_end=int(n*bounds[fi]); te0=tr_end; te1=int(n*bounds[fi+1])
    tr=np.arange(0,max(100,tr_end-3)); te=np.arange(te0,te1)
    mf=HistGradientBoostingClassifier(max_iter=120,max_leaf_nodes=15,learning_rate=.06,l2_regularization=1.0,random_state=100+fi)
    md=HistGradientBoostingClassifier(max_iter=120,max_leaf_nodes=15,learning_rate=.06,l2_regularization=1.0,random_state=200+fi)
    mf.fit(X[tr],follow[tr]); md.fit(X[tr],danger[tr])
    pf=mf.predict_proba(X[te])[:,1]; pdg=md.predict_proba(X[te])[:,1]
    af=roc_auc_score(follow[te],pf) if len(np.unique(follow[te]))>1 else np.nan
    ad=roc_auc_score(danger[te],pdg) if len(np.unique(danger[te]))>1 else np.nan
    # economic score: reward follow, penalize danger. Evaluate fixed top fractions.
    score=pf-pdg
    for frac in (.02,.05,.10,.20):
        k=max(1,int(len(te)*frac)); loc=np.argsort(score)[-k:]; sel=te[loc]
        rows.append(dict(fold=fi,top_frac=frac,n=k,follow_auc=af,danger_auc=ad,
            follow_rate=float(follow[sel].mean()),danger_rate=float(danger[sel].mean()),
            net_bps=float(net_bps[sel].mean()),base_net_bps=float(net_bps[te].mean()),
            score_mean=float(score[loc].mean())))
res=pd.DataFrame(rows); res.to_csv(OUT,index=False)
print('FEATURES',len(feat),feat)
print('\nAGG')
a=res.groupby('top_frac').agg(n=('n','sum'),follow_auc=('follow_auc','mean'),danger_auc=('danger_auc','mean'),follow_rate=('follow_rate','mean'),danger_rate=('danger_rate','mean'),net_bps=('net_bps',lambda s: np.average(s,weights=res.loc[s.index,'n'])),base_net_bps=('base_net_bps',lambda s: np.average(s,weights=res.loc[s.index,'n'])),pos_folds=('net_bps',lambda s:int((s>0).sum())),worst_fold_bps=('net_bps','min')).reset_index()
print(a.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
print('\nFOLDS TOP5')
print(res[res.top_frac==.05].to_string(index=False,float_format=lambda x:f'{x:.4f}'))
print('OUT',OUT)
