from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path(__file__).resolve().parents[2]
D=pd.read_csv(ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz').sort_values('feature_close_time')
R=pd.read_csv(ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv')
o=R.open.astype(float); h=R.high.astype(float); l=R.low.astype(float); c=R.close.astype(float); v=R.volume.astype(float); tb=R.taker_buy_base_volume.astype(float)
r=c.pct_change(); buy=tb/v.replace(0,np.nan); imb=2*buy-1
F=pd.DataFrame({'close_time':R.close_time.astype('int64'),'m1x_ret1':r,'m1x_ret3':c.pct_change(3),'m1x_body':(c-o)/o.replace(0,np.nan),'m1x_range':(h-l)/c.replace(0,np.nan),'m1x_close_loc':(c-l)/(h-l).replace(0,np.nan),'m1x_buy_ratio':buy,'m1x_imbalance':imb,'m1x_up_frac3':(r>0).astype(float).rolling(3).mean(),'m1x_ret1_mean3':r.rolling(3).mean(),'m1x_ret1_accel':r-r.shift(1),'m1x_imb_mean3':imb.rolling(3).mean()})
D=pd.merge_asof(D,F.sort_values('close_time'),left_on='feature_close_time',right_on='close_time',direction='backward').dropna().reset_index(drop=True)
strong=(D.mfe_5m_pct>=.20)&(D.mae_5m_pct>=-.15)&(D.time_to_mfe_5m<=3); danger=(D.mae_10m_pct<=-.50)|(D.net_10m_pct<=-.30); mask=strong^danger
D=D.loc[mask].reset_index(drop=True); yS=strong[mask].astype(int).to_numpy(); yD=danger[mask].astype(int).to_numpy()
m5=[x for x in D if x.startswith('m5_')]; m3=[x for x in D if x.startswith('m3_')]; m1=[x for x in D if x.startswith('m1x_')]
def X(cols): return D[cols].replace([np.inf,-np.inf],np.nan).fillna(0).to_numpy()
X5,X3,X1,X31=X(m5),X(m3),X(m1),X(m3+m1); n=len(D); cuts=[.5,.625,.75,.875,1.0]; rows=[]
def auc(y,p): return roc_auc_score(y,p) if len(np.unique(y))>1 else np.nan
for fi in range(1,4):
 tr_end=int(n*cuts[fi]); te=np.arange(tr_end,int(n*cuts[fi+1])); tr=np.arange(0,tr_end-3)
 s1=HistGradientBoostingClassifier(max_iter=70,max_leaf_nodes=15,learning_rate=.06,l2_regularization=.5,random_state=42).fit(X5[tr],yS[tr])
 ptr=s1.predict_proba(X5[tr])[:,1]; pte=s1.predict_proba(X5[te])[:,1]; t5=np.quantile(ptr,.80); trs=tr[ptr>=t5]; tes=te[pte>=t5]
 rec={'fold':fi+1,'n5':len(tes),'base_strong':yS[tes].mean(),'base_danger':yD[tes].mean(),'m5_auc':auc(yS[te],pte)}
 for tag,XX in [('M3',X3),('M1',X1),('M3M1',X31)]:
  f=HistGradientBoostingClassifier(max_iter=70,max_leaf_nodes=15,learning_rate=.06,l2_regularization=.7,random_state=43).fit(XX[trs],yS[trs]); g=HistGradientBoostingClassifier(max_iter=70,max_leaf_nodes=15,learning_rate=.06,l2_regularization=.7,random_state=44).fit(XX[trs],yD[trs])
  pftr=f.predict_proba(XX[trs])[:,1]; pdtr=g.predict_proba(XX[trs])[:,1]; pf=f.predict_proba(XX[tes])[:,1]; pdg=g.predict_proba(XX[tes])[:,1]; qtr=pftr-pdtr; q=pf-pdg; tq=np.quantile(qtr,.80); ch=tes[q>=tq]
  rec.update({f'{tag}_auc':auc(yS[tes],pf),f'{tag}_n':len(ch),f'{tag}_strong':yS[ch].mean() if len(ch) else np.nan,f'{tag}_danger':yD[ch].mean() if len(ch) else np.nan})
 rows.append(rec)
out=pd.DataFrame(rows); out.to_csv(ROOT/'research/results/NEAR_5M_SETUP_1M_SNIPER_WF.csv',index=False); print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
for tag in ['M3','M1','M3M1']:
 print(tag,'n',out[f'{tag}_n'].sum(),'strong',np.average(out[f'{tag}_strong'],weights=out[f'{tag}_n']),'danger',np.average(out[f'{tag}_danger'],weights=out[f'{tag}_n']),'auc',out[f'{tag}_auc'].mean())
