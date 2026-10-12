from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'
D=R/'NEAR_STRONG_SIGNAL_DATASET.csv.gz'; D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
P=R/'BINANCE_NEAR_PREMIUM_5M_360d.csv.gz'; F=R/'BINANCE_NEAR_FUNDING_360d.csv.gz'; O=R/'OKX_NEAR_OI_4H_360d.csv.gz'
OUT=R/'NEAR_DERIVATIVES_CONTEXT_WF.csv'
df=pd.read_csv(D); d1=pd.read_csv(D1); pre=pd.read_csv(P); fund=pd.read_csv(F); oi=pd.read_csv(O)
# derivative features, all known at/behind feature close
pre=pre.sort_values('close_time').copy(); pc=pre['close'].astype(float)
pre['premium_close']=pc; pre['premium_d1']=pc.diff(); pre['premium_d3']=pc-pc.shift(3); pre['premium_mean3']=pc.rolling(3).mean(); pre['premium_mean12']=pc.rolling(12).mean();
mu=pc.rolling(48).mean(); sd=pc.rolling(48).std(); pre['premium_z48']=(pc-mu)/sd.replace(0,np.nan); pre['premium_range']=pre['high'].astype(float)-pre['low'].astype(float)
pcols=['close_time','premium_close','premium_d1','premium_d3','premium_mean3','premium_mean12','premium_z48','premium_range']
df=pd.merge_asof(df.sort_values('feature_close_time'),pre[pcols].sort_values('close_time'),left_on='feature_close_time',right_on='close_time',direction='backward').drop(columns=['close_time'])
fund=fund.sort_values('fundingTime').copy(); fund['fundingRate']=fund['fundingRate'].astype(float); fund['funding_d1']=fund.fundingRate.diff(); fund['funding_mean3']=fund.fundingRate.rolling(3).mean(); fund['funding_abs']=fund.fundingRate.abs()
df=pd.merge_asof(df.sort_values('feature_close_time'),fund[['fundingTime','fundingRate','funding_d1','funding_mean3','funding_abs']],left_on='feature_close_time',right_on='fundingTime',direction='backward').drop(columns=['fundingTime'])
oi=oi.sort_values('ts').copy(); oi['oi_contracts']=oi.oi_contracts.astype(float); oi['okx_oi_ret1']=oi.oi_contracts.pct_change(); oi['okx_oi_ret2']=oi.oi_contracts.pct_change(2); oi['okx_oi_ret3']=oi.oi_contracts.pct_change(3); oi['okx_oi_abs1']=oi.okx_oi_ret1.abs(); oi['okx_oi_up']=(oi.okx_oi_ret1>0).astype(float)
df=pd.merge_asof(df.sort_values('feature_close_time'),oi[['ts','okx_oi_ret1','okx_oi_ret2','okx_oi_ret3','okx_oi_abs1','okx_oi_up']],left_on='feature_close_time',right_on='ts',direction='backward').drop(columns=['ts'])
# restrict to true overlap and non-na
base=[c for c in df.columns if c.startswith('m5_')]
prem=['premium_close','premium_d1','premium_d3','premium_mean3','premium_mean12','premium_z48','premium_range']
fundc=['fundingRate','funding_d1','funding_mean3','funding_abs']; oic=['okx_oi_ret1','okx_oi_ret2','okx_oi_ret3','okx_oi_abs1','okx_oi_up']
need=base+prem+fundc+oic
df=df.replace([np.inf,-np.inf],np.nan).dropna(subset=need).reset_index(drop=True)
print('overlap',len(df),'from',df.feature_close_time.min(),'to',df.feature_close_time.max(),flush=True)
# exact economic utility: TP20bps, SL100bps, 30m, 10bps RT
ot=d1.open_time.to_numpy(np.int64); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
idx=np.searchsorted(ot,df.entry_open_time.to_numpy(np.int64)); entry=df.entry_price.to_numpy(float); H=30; TP=.002; SL=.01; FEE=.001
y=np.full(len(df),np.nan); stop=np.zeros(len(df),int); tp=np.zeros(len(df),int)
for j,(ii,e) in enumerate(zip(idx,entry)):
    if ii+H>len(d1):continue
    out=None
    for k in range(ii,ii+H):
        sh=l[k]<=e*(1-SL); th=h[k]>=e*(1+TP)
        if sh:out=-SL;stop[j]=1;break
        if th:out=TP;tp[j]=1;break
    if out is None:out=c[ii+H-1]/e-1
    y[j]=out-FEE
ok=np.isfinite(y); df=df.loc[ok].reset_index(drop=True); y=y[ok]; stop=stop[ok]; tp=tp[ok]
groups={'M5':base,'M5_PREM':base+prem,'M5_PREM_FUND':base+prem+fundc,'M5_ALL':base+prem+fundc+oic}
edges=np.linspace(0,len(df),5,dtype=int); rows=[]
for name,cols in groups.items():
 X=df[cols].astype('float32').to_numpy()
 for fold in range(1,4):
  tr=np.arange(0,edges[fold]); te=np.arange(edges[fold],edges[fold+1])
  cfg=dict(max_iter=70,max_leaf_nodes=15,l2_regularization=2.0,learning_rate=.06,random_state=700+fold)
  rg=HistGradientBoostingRegressor(**cfg).fit(X[tr],y[tr]); cl=HistGradientBoostingClassifier(**cfg).fit(X[tr],(y[tr]>0).astype(int)); dg=HistGradientBoostingClassifier(**cfg).fit(X[tr],stop[tr])
  prt=rg.predict(X[tr]); ppt=cl.predict_proba(X[tr])[:,1]; pr=rg.predict(X[te]); pp=cl.predict_proba(X[te])[:,1]; pdg=dg.predict_proba(X[te])[:,1]
  def zn(v,mu,sd):return (v-mu)/(sd if sd>1e-9 else 1)
  sr=zn(pr,prt.mean(),prt.std()); sp=zn(pp,ppt.mean(),ppt.std()); score=.5*sr+.5*sp
  k=max(1,int(len(te)*.005)); sel=np.argsort(score)[-k:]
  auc=roc_auc_score((y[te]>0).astype(int),pp); daug=roc_auc_score(stop[te],pdg)
  rows.append(dict(model=name,fold=fold+1,n=len(sel),utility_auc=auc,danger_auc=daug,net_bps=np.mean(y[te][sel])*1e4,base_bps=np.mean(y[te])*1e4,win=np.mean(y[te][sel]>0),tp_rate=np.mean(tp[te][sel]),stop_rate=np.mean(stop[te][sel]),danger_pred=np.mean(pdg[sel])))
out=pd.DataFrame(rows); out.to_csv(OUT,index=False)
print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'),flush=True)
print('\nAGG',flush=True)
for n,g in out.groupby('model'):
 print(n,'n',g.n.sum(),'net',np.average(g.net_bps,weights=g.n),'pos',int((g.net_bps>0).sum()),'/3','worst',g.net_bps.min(),'util_auc',g.utility_auc.mean(),'danger_auc',g.danger_auc.mean(),'stop',np.average(g.stop_rate,weights=g.n),flush=True)
print('OUT',OUT,flush=True)
