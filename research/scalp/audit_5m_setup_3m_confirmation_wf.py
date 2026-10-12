from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path(__file__).resolve().parents[2]
D=pd.read_csv(ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz')
# mutually exclusive diagnostic labels from prior audit
strong=(D.mfe_5m_pct>=0.20)&(D.mae_5m_pct>=-0.15)&(D.time_to_mfe_5m<=3)
danger=(D.mae_10m_pct<=-0.50)|(D.net_10m_pct<=-0.30)
mask=strong ^ danger
D=D.loc[mask].reset_index(drop=True); yS=strong[mask].astype(int).to_numpy(); yD=danger[mask].astype(int).to_numpy()
m5=[c for c in D if c.startswith('m5_')]
m3=[c for c in D if c.startswith('m3_')]
X5=D[m5].replace([np.inf,-np.inf],np.nan).fillna(0).to_numpy()
X3=D[m3].replace([np.inf,-np.inf],np.nan).fillna(0).to_numpy()
n=len(D); cuts=[0.50,0.625,0.75,0.875,1.0]
rows=[]
for fi in range(1,4):
    tr_end=int(n*cuts[fi]); te0=tr_end; te1=int(n*cuts[fi+1])
    tr=np.arange(0,max(200,tr_end-3)); te=np.arange(te0,te1)
    # stage1: 5m setup strong probability
    s1=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,learning_rate=.06,l2_regularization=.5,random_state=42)
    s1.fit(X5[tr],yS[tr]); pS_tr=s1.predict_proba(X5[tr])[:,1]; pS_te=s1.predict_proba(X5[te])[:,1]
    thr5=np.quantile(pS_tr,.80)
    tr_sel=tr[pS_tr>=thr5]; te_sel=te[pS_te>=thr5]
    if len(tr_sel)<200 or len(te_sel)<20: continue
    # second stage only among 5m candidates: separate follow/danger using 3m continuous features
    f=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,learning_rate=.06,l2_regularization=.7,random_state=43)
    g=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,learning_rate=.06,l2_regularization=.7,random_state=44)
    f.fit(X3[tr_sel],yS[tr_sel]); g.fit(X3[tr_sel],yD[tr_sel])
    pf_tr=f.predict_proba(X3[tr_sel])[:,1]; pd_tr=g.predict_proba(X3[tr_sel])[:,1]
    pf=f.predict_proba(X3[te_sel])[:,1]; pdg=g.predict_proba(X3[te_sel])[:,1]
    score=pf-pdg; score_tr=pf_tr-pd_tr; thr3=np.quantile(score_tr,.80)
    chosen=te_sel[score>=thr3]
    def auc(y,p):
        return roc_auc_score(y,p) if len(np.unique(y))>1 else np.nan
    rows.append(dict(fold=fi+1,n5=len(te_sel),base_strong=yS[te_sel].mean(),base_danger=yD[te_sel].mean(),
                     follow_auc=auc(yS[te_sel],pf),danger_auc=auc(yD[te_sel],pdg),n3=len(chosen),
                     chosen_strong=yS[chosen].mean() if len(chosen) else np.nan,chosen_danger=yD[chosen].mean() if len(chosen) else np.nan,
                     m5_auc=auc(yS[te],pS_te),thr5=thr5,thr3=thr3))
out=pd.DataFrame(rows)
out.to_csv(ROOT/'research/results/NEAR_5M_SETUP_3M_CONFIRM_WF.csv',index=False)
print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
if len(out):
 print('\nWEIGHTED')
 print('5m candidates',out.n5.sum(),'strong',np.average(out.base_strong,weights=out.n5),'danger',np.average(out.base_danger,weights=out.n5))
 print('3m chosen',out.n3.sum(),'strong',np.average(out.chosen_strong,weights=out.n3),'danger',np.average(out.chosen_danger,weights=out.n3))
 print('mean follow auc',out.follow_auc.mean(),'mean danger auc',out.danger_auc.mean(),'mean m5 auc',out.m5_auc.mean())
