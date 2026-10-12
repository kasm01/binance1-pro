from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path(__file__).resolve().parents[2]
D=pd.read_csv(ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz')
OI=pd.read_csv(ROOT/'research/results/OKX_NEAR_OI_4H_360d.csv.gz').sort_values('ts')
OI['oi_ret1']=OI.oi_contracts.pct_change(); OI['oi_ret2']=OI.oi_contracts.pct_change(2); OI['oi_ret3']=OI.oi_contracts.pct_change(3)
OI['oi_abs1']=OI.oi_ret1.abs(); OI['oi_usd_ret1']=OI.oi_usd.pct_change()
D=pd.merge_asof(D.sort_values('feature_close_time'),OI[['ts','oi_ret1','oi_ret2','oi_ret3','oi_abs1','oi_usd_ret1']],left_on='feature_close_time',right_on='ts',direction='backward')
D=D.dropna(subset=['oi_ret1']).reset_index(drop=True)
strong=(D.mfe_5m_pct>=0.20)&(D.mae_5m_pct>=-0.15)&(D.time_to_mfe_5m<=3)
danger=(D.mae_10m_pct<=-0.50)|(D.net_10m_pct<=-0.30)
mask=strong ^ danger; D=D.loc[mask].reset_index(drop=True); yS=strong[mask].astype(int).to_numpy(); yD=danger[mask].astype(int).to_numpy()
m5=[c for c in D if c.startswith('m5_')]; m3=[c for c in D if c.startswith('m3_')]; oi=['oi_ret1','oi_ret2','oi_ret3','oi_abs1','oi_usd_ret1']
X5=D[m5].replace([np.inf,-np.inf],np.nan).fillna(0).to_numpy(); X3=D[m3].replace([np.inf,-np.inf],np.nan).fillna(0).to_numpy(); X3O=D[m3+oi].replace([np.inf,-np.inf],np.nan).fillna(0).to_numpy()
n=len(D); cuts=[0.40,0.55,0.70,0.85,1.0]; rows=[]
def auc(y,p): return roc_auc_score(y,p) if len(np.unique(y))>1 else np.nan
for fi in range(1,4):
 tr_end=int(n*cuts[fi]); te0=tr_end; te1=int(n*cuts[fi+1]); tr=np.arange(0,max(300,tr_end-3)); te=np.arange(te0,te1)
 s1=HistGradientBoostingClassifier(max_iter=70,max_leaf_nodes=15,learning_rate=.06,l2_regularization=.5,random_state=42).fit(X5[tr],yS[tr])
 ps_tr=s1.predict_proba(X5[tr])[:,1]; ps_te=s1.predict_proba(X5[te])[:,1]; t5=np.quantile(ps_tr,.80); tr_sel=tr[ps_tr>=t5]; te_sel=te[ps_te>=t5]
 if len(tr_sel)<150 or len(te_sel)<20: continue
 rec={'fold':fi+1,'n5':len(te_sel),'base_strong':yS[te_sel].mean(),'base_danger':yD[te_sel].mean(),'m5_auc':auc(yS[te],ps_te)}
 for tag,X in [('M3',X3),('M3OI',X3O)]:
  f=HistGradientBoostingClassifier(max_iter=70,max_leaf_nodes=15,learning_rate=.06,l2_regularization=.7,random_state=43).fit(X[tr_sel],yS[tr_sel])
  g=HistGradientBoostingClassifier(max_iter=70,max_leaf_nodes=15,learning_rate=.06,l2_regularization=.7,random_state=44).fit(X[tr_sel],yD[tr_sel])
  pftr=f.predict_proba(X[tr_sel])[:,1]; pdtr=g.predict_proba(X[tr_sel])[:,1]; pft=f.predict_proba(X[te_sel])[:,1]; pdt=g.predict_proba(X[te_sel])[:,1]
  scoretr=pftr-pdtr; score=pft-pdt; t3=np.quantile(scoretr,.80); ch=te_sel[score>=t3]
  rec.update({f'{tag}_follow_auc':auc(yS[te_sel],pft),f'{tag}_danger_auc':auc(yD[te_sel],pdt),f'{tag}_n':len(ch),f'{tag}_strong':yS[ch].mean() if len(ch) else np.nan,f'{tag}_danger':yD[ch].mean() if len(ch) else np.nan})
 rows.append(rec)
out=pd.DataFrame(rows); out.to_csv(ROOT/'research/results/NEAR_5M_SETUP_3M_OI_CONFIRM_WF.csv',index=False)
print('overlap_rows',n); print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
for tag in ['M3','M3OI']:
 print(tag,'n',out[f'{tag}_n'].sum(),'strong',np.average(out[f'{tag}_strong'],weights=out[f'{tag}_n']),'danger',np.average(out[f'{tag}_danger'],weights=out[f'{tag}_n']),'follow_auc',out[f'{tag}_follow_auc'].mean(),'danger_auc',out[f'{tag}_danger_auc'].mean())
