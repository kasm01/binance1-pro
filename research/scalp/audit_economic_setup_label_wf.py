from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path('/home/kasm920/binance1-pro')
D=pd.read_csv(ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz')
K=pd.read_csv(ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv')
# Normalize timestamps
for c in ['open_time','close_time']:
    K[c]=pd.to_numeric(K[c],errors='coerce')
for c in ['open','high','low','close']:
    K[c]=pd.to_numeric(K[c],errors='coerce')
# entry_open_time in dataset is ms-compatible; inspect scale and normalize to int ms
et=pd.to_numeric(D['entry_open_time'],errors='coerce').astype('int64').to_numpy()
ot=pd.to_numeric(K['open_time'],errors='coerce').astype('int64').to_numpy()
# handle seconds if needed
if np.nanmedian(et) < 1e12: et=et*1000
if np.nanmedian(ot) < 1e12: ot=ot*1000
idx=np.searchsorted(ot,et)
valid=(idx>=0)&(idx<len(K))&(ot[np.minimum(idx,len(K)-1)]==et)
print('rows',len(D),'aligned',int(valid.sum()))
# causal feature columns only
fcols=[c for c in D.columns if c.startswith(('m5_','m3_','m15_'))]
X=D[fcols].replace([np.inf,-np.inf],np.nan).fillna(0).to_numpy(float)
# chronological folds identical broad expanding-WF spirit
n=len(D); cuts=[int(n*x) for x in (.50,.625,.75,.875,1.0)]
configs=[]
for horizon in (10,15):
  for sl in (.50,.75,1.00,1.50):
    configs.append((horizon,.20,sl))
fee_pct=.10 # 10 bps = 0.10 percentage points
rows=[]
for horizon,tp,sl in configs:
  realized=np.full(n,np.nan); outcome=np.full(n,'BAD',dtype=object)
  for i in np.where(valid)[0]:
    j=idx[i]; end=min(j+horizon,len(K))
    if end<=j: continue
    p=float(D.iloc[i]['entry_price'])
    hi=K['high'].iloc[j:end].to_numpy(float)/p-1.0
    lo=K['low'].iloc[j:end].to_numpy(float)/p-1.0
    cl=K['close'].iloc[j:end].to_numpy(float)/p-1.0
    tp_hit=np.where(hi>=tp/100.0)[0]
    sl_hit=np.where(lo<=-sl/100.0)[0]
    itp=int(tp_hit[0]) if len(tp_hit) else 10**9
    isl=int(sl_hit[0]) if len(sl_hit) else 10**9
    # conservative same-candle ambiguity => SL first
    if isl<=itp and isl<10**9:
      gross=-sl
      outcome[i]='SL'
    elif itp<isl and itp<10**9:
      gross=tp
      outcome[i]='TP'
    else:
      gross=float(cl[-1]*100.0)
      outcome[i]='TIME'
    realized[i]=gross-fee_pct
  y=(realized>0).astype(int)
  mask=np.isfinite(realized)&valid
  aucs=[]; fold_stats=[]
  for fold in range(1,5):
    tr_end=cuts[fold-1]; te_start=tr_end; te_end=cuts[fold]
    tr=np.arange(0,max(0,tr_end-3)); te=np.arange(te_start,te_end)
    tr=tr[mask[tr]]; te=te[mask[te]]
    if len(tr)<1000 or len(te)<100: continue
    m=HistGradientBoostingClassifier(max_iter=120,max_leaf_nodes=15,learning_rate=.05,l2_regularization=1.0,random_state=42)
    m.fit(X[tr],y[tr]); p=m.predict_proba(X[te])[:,1]
    auc=roc_auc_score(y[te],p) if len(np.unique(y[te]))>1 else .5
    aucs.append(auc)
    q=np.quantile(p,.80); sel=te[p>=q]
    pnl=float(np.nanmean(realized[sel])); base=float(np.nanmean(realized[te]))
    fold_stats.append((fold,len(sel),pnl,base,float(np.mean(y[sel]))))
  if not fold_stats: continue
  sel_n=sum(x[1] for x in fold_stats); wp=sum(x[1]*x[2] for x in fold_stats)/sel_n
  wb=sum(x[1]*x[3] for x in fold_stats)/sel_n
  pos=sum(x[2]>0 for x in fold_stats); worst=min(x[2] for x in fold_stats)
  allidx=np.where(mask)[0]
  rows.append({'horizon_min':horizon,'tp_pct':tp,'sl_pct':sl,'base_positive_rate':float(y[allidx].mean()),'mean_auc':float(np.mean(aucs)),'min_auc':float(np.min(aucs)),'sel_n':sel_n,'sel_net_bps':wp*100,'base_net_bps':wb*100,'delta_bps':(wp-wb)*100,'pos_folds':pos,'worst_fold_bps':worst*100})
out=pd.DataFrame(rows).sort_values(['sel_net_bps','mean_auc'],ascending=False)
out.to_csv(ROOT/'research/results/NEAR_ECON_SETUP_LABEL_WF.csv',index=False)
print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
print('OUTPUT',ROOT/'research/results/NEAR_ECON_SETUP_LABEL_WF.csv')
