#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path(__file__).resolve().parents[2]
IN=ROOT/'research/results/NEAR_DUAL_GATE_CANDIDATES.csv.gz'
OUT1=ROOT/'research/results/NEAR_STRONG_SIGNAL_FEATURE_SEPARATION.csv'
OUT2=ROOT/'research/results/NEAR_STRONG_SIGNAL_WF.csv'
df=pd.read_csv(IN)
feat=[c for c in df.columns if c.startswith(('m5_','m3_','m15_'))]
# Clean strong vs danger: exclude ambiguous middle states
# *_pct columns are percentage points: 0.20 == +0.20%, -0.50 == -0.50%.
strong=(df.mfe_5m_pct>=0.20)&(df.mae_5m_pct>=-0.15)&(df.time_to_mfe_5m<=3)
danger=(df.mae_10m_pct<=-0.50)|(df.net_10m_pct<=-0.30)
use=strong|danger
d=df.loc[use].copy(); d['y']=strong[use].astype(int).to_numpy()
print('LABELED_N=',len(d),'STRONG=',int(d.y.sum()),'DANGER=',int((1-d.y).sum()),'STRONG_RATE=',round(d.y.mean(),4))
# robust univariate separation, orientation-free AUC
rows=[]
for c in feat+['gate_quality']:
    x=d[c].astype(float)
    med1=x[d.y.eq(1)].median(); med0=x[d.y.eq(0)].median()
    mad=np.nanmedian(np.abs(x-np.nanmedian(x)))+1e-12
    eff=(med1-med0)/(1.4826*mad)
    try: auc=roc_auc_score(d.y,x); auc=max(auc,1-auc)
    except: auc=np.nan
    signs=[]
    for f in sorted(d.gate_fold.unique()):
        z=d[d.gate_fold.eq(f)]
        if z.y.nunique()<2: continue
        delta=z.loc[z.y.eq(1),c].median()-z.loc[z.y.eq(0),c].median()
        signs.append(np.sign(delta))
    consistency=max(sum(s>0 for s in signs),sum(s<0 for s in signs))/max(1,len(signs))
    rows.append((c,med1,med0,eff,auc,consistency,len(signs)))
r=pd.DataFrame(rows,columns=['feature','strong_median','danger_median','robust_effect','auc_abs','fold_sign_consistency','folds'])
r['score']=(r.auc_abs-.5)*2*np.abs(r.robust_effect)*r.fold_sign_consistency
r=r.sort_values('score',ascending=False); r.to_csv(OUT1,index=False)
print('\n===== TOP SEPARATORS =====')
print(r.head(18).round(4).to_string(index=False))
# walk-forward classifier; train prior folds, test next. compare all vs top-score selections.
wf=[]
Xall=d[feat].replace([np.inf,-np.inf],np.nan).fillna(0.0)
for tf in [2,3,4]:
    tr=d.gate_fold<tf; te=d.gate_fold.eq(tf)
    if tr.sum()<50 or te.sum()<10 or d.loc[tr,'y'].nunique()<2 or d.loc[te,'y'].nunique()<2: continue
    model=HistGradientBoostingClassifier(max_depth=3,learning_rate=.05,max_iter=180,l2_regularization=2.0,random_state=42)
    model.fit(Xall.loc[tr],d.loc[tr,'y'])
    ps_tr=model.predict_proba(Xall.loc[tr])[:,1]; ps_te=model.predict_proba(Xall.loc[te])[:,1]
    auc=roc_auc_score(d.loc[te,'y'],ps_te)
    base=d.loc[te,'y'].mean()
    for keep in [.20,.30,.40,.50]:
        cut=np.quantile(ps_tr,1-keep)
        sel=ps_te>=cut
        z=d.loc[te].iloc[np.flatnonzero(sel)]
        if len(z)==0: continue
        wf.append(dict(test_fold=tf,keep_target=keep,n_test=int(te.sum()),n_keep=len(z),coverage=len(z)/te.sum(),auc=auc,base_strong_rate=base,kept_strong_rate=z.y.mean(),danger_rate=1-z.y.mean(),mfe5_bps=z.mfe_5m_pct.mean()*100,mae5_bps=z.mae_5m_pct.mean()*100,net10_bps=z.net_10m_pct.mean()*100,gate_q=z.gate_quality.mean()))
w=pd.DataFrame(wf); w.to_csv(OUT2,index=False)
print('\n===== WALK-FORWARD STRONG-SIGNAL FILTER =====')
print(w.round(4).to_string(index=False))
if not w.empty:
    print('\n===== AGG BY KEEP =====')
    print(w.groupby('keep_target').apply(lambda g: pd.Series({'n_keep':g.n_keep.sum(),'mean_auc':g.auc.mean(),'strong_rate_w':np.average(g.kept_strong_rate,weights=g.n_keep),'danger_rate_w':np.average(g.danger_rate,weights=g.n_keep),'net10_bps_w':np.average(g.net10_bps,weights=g.n_keep)})).round(4).to_string())
print('OUTPUTS=',OUT1,OUT2)
