from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
ROOT=Path(__file__).resolve().parents[2];SYMS=['NEARUSDT','SOLUSDT','DOGEUSDT','LINKUSDT','AVAXUSDT'];TP=.004;SL=.015;H=15;FEE=.001

def build(sym):
 d=pd.read_csv(ROOT/f'data/offline_cache/{sym}_1m_360d.csv');x=d.copy();x['_g']=x.open_time.astype('int64')//300000
 a=x.groupby('_g',sort=True).agg(open_time=('open_time','first'),open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('volume','sum'),close_time=('close_time','last'),taker_buy_base_volume=('taker_buy_base_volume','sum')).reset_index(drop=True)
 o=a.open.astype(float);h=a.high.astype(float);l=a.low.astype(float);c=a.close.astype(float);v=a.volume.astype(float);tb=a.taker_buy_base_volume.astype(float);r1=c.pct_change();f=pd.DataFrame({'ts':a.close_time.astype('int64')})
 f['ret1']=r1;f['ret2']=c.pct_change(2);f['ret3']=c.pct_change(3);f['body']=(c-o)/o;f['range']=(h-l)/c;f['close_loc']=(c-l)/(h-l).replace(0,np.nan);e5=c.ewm(span=5,adjust=False).mean();e20=c.ewm(span=20,adjust=False).mean();f['e5e20']=e5/e20-1;f['e20_slope3']=e20/e20.shift(3)-1;pc=c.shift(1);tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1);f['atr14']=tr.rolling(14).mean()/c;f['vol_z20']=(v-v.rolling(20).mean())/v.rolling(20).std();buy=tb/v.replace(0,np.nan);f['buy_ratio']=buy;f['imbalance']=2*buy-1;f['up_frac3']=(r1>0).astype(float).rolling(3).mean();f['ret1_mean3']=r1.rolling(3).mean();f['ret1_accel']=r1-r1.shift(1);f['imb_mean3']=f.imbalance.rolling(3).mean();f=f.replace([np.inf,-np.inf],np.nan).dropna().reset_index(drop=True)
 ot=d.open_time.to_numpy(np.int64);oo=d.open.to_numpy(float);hh=d.high.to_numpy(float);ll=d.low.to_numpy(float);cc=d.close.to_numpy(float);u=[];w=[]
 for t in f.ts:
  j=int(np.searchsorted(ot,int(t),side='right'))
  if j+H>len(d):u.append(np.nan);w.append(0);continue
  e=oo[j];out=None;win=0
  for k in range(j,j+H):
   if hh[k]>=e*(1+SL):out=-SL;break
   if ll[k]<=e*(1-TP):out=TP;win=1;break
  if out is None:out=-(cc[j+H-1]/e-1)
  u.append(out-FEE);w.append(win)
 f['utility']=u;f['win']=w;return f.dropna().reset_index(drop=True)
rows=[]
for sym in SYMS:
 d=build(sym);feat=[c for c in d if c not in ['ts','utility','win']];X=d[feat].to_numpy('float32');y=d.utility.to_numpy();win=d.win.to_numpy();edges=np.linspace(0,len(d),5,dtype=int)
 for fold in range(1,4):
  tr=np.arange(edges[0],edges[fold]);te=np.arange(edges[fold],edges[fold+1]);kw=dict(max_iter=80,max_leaf_nodes=15,l2_regularization=2.,learning_rate=.06,random_state=1100+fold)
  rg=HistGradientBoostingRegressor(**kw).fit(X[tr],y[tr]);cl=HistGradientBoostingClassifier(**kw).fit(X[tr],(y[tr]>0).astype(int));prt=rg.predict(X[tr]);ppt=cl.predict_proba(X[tr])[:,1];pr=rg.predict(X[te]);pp=cl.predict_proba(X[te])[:,1]
  def z(v,ref):
   sd=np.std(ref);return (v-np.mean(ref))/(sd if sd>1e-9 else 1)
  best=None
  for a in [0,.25,.5,.75,1.]:
   st=a*z(prt,prt)+(1-a)*z(ppt,ppt)
   for frac in [.005,.01,.02,.05]:
    n=max(150,int(len(tr)*frac));sel=np.argsort(st)[-n:];val=y[tr][sel].mean()
    if best is None or val>best[0]:best=(val,a,frac)
  _,a,frac=best;score=a*z(pr,prt)+(1-a)*z(pp,ppt);n=max(1,int(len(te)*frac));sel=np.argsort(score)[-n:];v=y[te][sel]
  rows.append(dict(symbol=sym,fold=fold+1,n=n,blend=a,top_frac=frac,net_bps=v.mean()*1e4,win=(v>0).mean(),tp_rate=win[te][sel].mean(),base_bps=y[te].mean()*1e4))
out=pd.DataFrame(rows);out.to_csv(ROOT/'research/results/MULTICOIN_SHORT_5M_ECON_WF.csv',index=False);print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'));print('\nAGG')
for s,g in out.groupby('symbol'):
 print(s,'n',g.n.sum(),'net',np.average(g.net_bps,weights=g.n),'pos',int((g.net_bps>0).sum()),'/3','worst',g.net_bps.min(),'tp',np.average(g.tp_rate,weights=g.n))
