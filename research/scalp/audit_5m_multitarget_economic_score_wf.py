from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score
ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz'
OUT=ROOT/'research/results/NEAR_5M_MULTITARGET_ECON_WF.csv'
df=pd.read_csv(D).replace([np.inf,-np.inf],np.nan).dropna().reset_index(drop=True)
feat=[c for c in df.columns if c.startswith('m5_') and c not in ['m5']]
X=df[feat].astype('float32').to_numpy()
# Targets: future 10m in percentage points, e.g. 0.20 = +0.20%
mfe=df['mfe_10m_pct'].to_numpy(float); mae=df['mae_10m_pct'].to_numpy(float); net=df['net_10m_pct'].to_numpy(float)
time_mfe=df['time_to_mfe_10m'].to_numpy(float)
follow=((mfe>=0.20)&(mae>=-0.50)&(time_mfe<=5)).astype(int)
danger=((mae<=-0.75)|(net<=-0.30)).astype(int)
# chronological 4 folds; folds 2-4 tested using all past folds
edges=np.linspace(0,len(df),5,dtype=int)
rows=[]
for fold in range(1,4):
    tr=np.arange(0,edges[fold]); te=np.arange(edges[fold],edges[fold+1])
    if len(np.unique(follow[tr]))<2 or len(np.unique(danger[tr]))<2: continue
    common=dict(max_iter=110,max_leaf_nodes=15,l2_regularization=2.0,learning_rate=0.06,random_state=100+fold)
    mf=HistGradientBoostingClassifier(**common).fit(X[tr],follow[tr])
    md=HistGradientBoostingClassifier(**common).fit(X[tr],danger[tr])
    rm=HistGradientBoostingRegressor(**common).fit(X[tr],mfe[tr])
    ra=HistGradientBoostingRegressor(**common).fit(X[tr],-mae[tr]) # positive adverse magnitude
    pf=mf.predict_proba(X[te])[:,1]; pdg=md.predict_proba(X[te])[:,1]
    pmfe=np.maximum(0,rm.predict(X[te])); pmae=np.maximum(0,ra.predict(X[te]))
    # standardize each component ONLY from train predictions for scale-neutral combination
    pft=mf.predict_proba(X[tr])[:,1]; pdt=md.predict_proba(X[tr])[:,1]
    pmfet=np.maximum(0,rm.predict(X[tr])); pmaet=np.maximum(0,ra.predict(X[tr]))
    def z(v, ref):
        s=np.std(ref); return (v-np.mean(ref))/(s if s>1e-9 else 1.0)
    zf=z(pf,pft); zd=z(pdg,pdt); zm=z(pmfe,pmfet); za=z(pmae,pmaet)
    # candidate score families; weights calibrated by choosing best on TRAIN only
    train_comps=np.column_stack([z(pft,pft), -z(pdt,pdt), z(pmfet,pmfet), -z(pmaet,pmaet)])
    test_comps=np.column_stack([zf,-zd,zm,-za])
    weight_grid=[
      (1,1,0,0),(1,1,0.5,0.5),(1,1,1,1),(1.5,1,1,1.5),(1,1.5,1,1.5),
      (0.5,1.5,1,2),(1,2,1,2),(1,2,0.5,2),(1.5,2,1,2)
    ]
    top_fracs=[0.02,0.05,0.10,0.20]
    # economic proxy = future 10m close - 10 bps RT fee = pct-points*100 bps -10
    econ_tr=net[tr]*100.0-10.0; econ_te=net[te]*100.0-10.0
    # choose (weights, top_frac) by best TRAIN mean, require >=300 train rows
    best=None
    for w in weight_grid:
      s=train_comps@np.array(w,float)
      for frac in top_fracs:
        k=max(300,int(len(tr)*frac)); idx=np.argsort(s)[-k:]
        val=float(np.mean(econ_tr[idx]))
        cand=(val,w,frac)
        if best is None or cand[0]>best[0]: best=cand
    _,wsel,fsel=best
    score=test_comps@np.array(wsel,float); k=max(1,int(len(te)*fsel)); idx=np.argsort(score)[-k:]
    aucf=roc_auc_score(follow[te],pf); aucd=roc_auc_score(danger[te],pdg)
    rows.append(dict(fold=fold+1,n_test=len(te),n_sel=len(idx),top_frac=fsel,weights=str(wsel),
                     follow_auc=aucf,danger_auc=aucd,
                     sel_follow=float(follow[te][idx].mean()),sel_danger=float(danger[te][idx].mean()),
                     sel_mfe=float(mfe[te][idx].mean()),sel_mae=float(mae[te][idx].mean()),
                     sel_net_bps=float(np.mean(econ_te[idx])),base_net_bps=float(np.mean(econ_te)),
                     delta_bps=float(np.mean(econ_te[idx])-np.mean(econ_te))))
out=pd.DataFrame(rows); out.to_csv(OUT,index=False)
print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
if len(out):
    n=out.n_sel.sum(); print('\nWEIGHTED sel_net_bps',np.average(out.sel_net_bps,weights=out.n_sel),'delta',np.average(out.delta_bps,weights=out.n_sel),'pos_folds',int((out.sel_net_bps>0).sum()),'worst',out.sel_net_bps.min())
print('OUT',OUT)
