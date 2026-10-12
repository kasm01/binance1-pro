#!/usr/bin/env python3
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'
df=pd.read_csv(R/'NEAR_DUAL_GATE_CANDIDATES.csv.gz').sort_values('feature_close_time')
strong=(df.mfe_5m_pct>=.20)&(df.mae_5m_pct>=-.15)&(df.time_to_mfe_5m<=3)
danger=(df.mae_10m_pct<=-.50)|(df.net_10m_pct<=-.30)
d=df.loc[strong|danger].copy(); d['y']=strong[strong|danger].astype(int).to_numpy()

def oi_features(path,pfx):
    x=pd.read_csv(path).sort_values('ts').copy(); x.ts=pd.to_numeric(x.ts)
    oi=pd.to_numeric(x.oi_usd,errors='coerce').replace(0,np.nan)
    x[f'{pfx}_ret1']=oi.pct_change(1); x[f'{pfx}_ret2']=oi.pct_change(2); x[f'{pfx}_ret3']=oi.pct_change(3); x[f'{pfx}_ret6']=oi.pct_change(6)
    x[f'{pfx}_logdiff1']=np.log(oi).diff(1); x[f'{pfx}_logdiff3']=np.log(oi).diff(3)
    rm=oi.rolling(20,min_periods=8); x[f'{pfx}_z20']=(oi-rm.mean())/(rm.std(ddof=0)+1e-12)
    x[f'{pfx}_accel']=x[f'{pfx}_ret1']-x[f'{pfx}_ret1'].shift(1)
    return x[['ts']+[c for c in x if c.startswith(pfx+'_')]].sort_values('ts')
for fn,pfx in [('OKX_NEAR_OI_4H_360d.csv.gz','oi4h'),('OKX_NEAR_OI_1D_360d.csv.gz','oi1d')]:
    x=oi_features(R/fn,pfx)
    d=pd.merge_asof(d.sort_values('feature_close_time'),x,left_on='feature_close_time',right_on='ts',direction='backward').drop(columns=['ts'])
# add existing OKX price feature file by rebuilding basic price features
for fn,pfx,mins in [('OKX_NEAR_3m_360d.csv.gz','okx3',3),('OKX_NEAR_5m_360d.csv.gz','okx5',5)]:
    x=pd.read_csv(R/fn).sort_values('ts').copy(); c=x.close.astype(float); o=x.open.astype(float); h=x.high.astype(float); l=x.low.astype(float)
    x[f'{pfx}_ret1']=c.pct_change(); x[f'{pfx}_ret3']=c.pct_change(3); x[f'{pfx}_range']=h/l-1
    tr=pd.concat([(h-l).abs(),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1); x[f'{pfx}_atr14']=tr.rolling(14,min_periods=5).mean()/c
    x['ct']=x.ts.astype('int64')+mins*60000-1
    d=pd.merge_asof(d.sort_values('feature_close_time'),x[['ct']+[c for c in x if c.startswith(pfx+'_')]].sort_values('ct'),left_on='feature_close_time',right_on='ct',direction='backward').drop(columns=['ct'])
# cross exchange deltas
for tf in ['3','5']:
    for k in ['ret1','ret3','range','atr14']:
        a=f'm{tf}_{k}'; b=f'okx{tf}_{k}'
        if a in d and b in d:d[f'x{tf}_{k}_diff']=d[a]-d[b]
tech=[c for c in d if c.startswith(('m3_','m5_','m15_')) and not any(z in c for z in ['mfe','mae','net_','time_to_'])]
price=[c for c in d if c.startswith(('okx3_','okx5_','x3_','x5_'))]
oi=[c for c in d if c.startswith(('oi4h_','oi1d_'))]
print('N',len(d),'strong',round(d.y.mean(),4),'tech',len(tech),'price',len(price),'oi',len(oi),'oi coverage',round(d[oi].notna().all(axis=1).mean(),4))
# univariate OI separation
for c in oi:
    z=d[['y',c]].dropna(); auc=roc_auc_score(z.y,z[c]); aa=max(auc,1-auc)
    print('UNI',c,'n',len(z),'auc_abs',round(aa,4),'strong_med',round(z.loc[z.y.eq(1),c].median(),6),'danger_med',round(z.loc[z.y.eq(0),c].median(),6))

def run(name,feats):
    z=d.copy(); X=z[feats].replace([np.inf,-np.inf],np.nan).fillna(0.0); rows=[]
    for tf in [2,3,4]:
        tr=z.gate_fold<tf; te=z.gate_fold.eq(tf)
        if tr.sum()<80 or te.sum()<20:continue
        m=HistGradientBoostingClassifier(max_depth=3,learning_rate=.04,max_iter=180,l2_regularization=3,random_state=42)
        m.fit(X.loc[tr],z.loc[tr,'y']); ptr=m.predict_proba(X.loc[tr])[:,1]; pte=m.predict_proba(X.loc[te])[:,1]
        auc=roc_auc_score(z.loc[te,'y'],pte); cut=np.quantile(ptr,.8); keep=pte>=cut; zz=z.loc[te].iloc[np.flatnonzero(keep)]
        rows.append(dict(model=name,fold=tf,n_test=int(te.sum()),auc=auc,n_keep=len(zz),strong_rate=zz.y.mean() if len(zz) else np.nan,net10_bps=zz.net_10m_pct.mean()*100 if len(zz) else np.nan))
    return rows
rows=[]
for name,feats in [('TECH',tech),('OI_ONLY',oi),('PRICE_ONLY',price),('TECH_OI',tech+oi),('TECH_PRICE',tech+price),('TECH_PRICE_OI',tech+price+oi)]:rows+=run(name,feats)
w=pd.DataFrame(rows); out=R/'NEAR_OKX_OI_CONTEXT_WF.csv'; w.to_csv(out,index=False)
print('\nWF');print(w.round(4).to_string(index=False))
print('\nAGG');print(w.groupby('model').apply(lambda g:pd.Series({'mean_auc':g.auc.mean(),'w_strong':np.average(g.strong_rate,weights=g.n_keep),'w_net10':np.average(g.net10_bps,weights=g.n_keep)})).round(4).sort_values('mean_auc',ascending=False).to_string())
print('OUTPUT',out)
