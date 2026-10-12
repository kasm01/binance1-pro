from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
ROOT=Path(__file__).resolve().parents[2]
SYMS=['NEARUSDT','SOLUSDT','DOGEUSDT','LINKUSDT','AVAXUSDT']
TP=.002; SL=.010; H=15; FEE=.001

def pct_rank(train, test):
    s=np.sort(np.asarray(train,float)); return np.searchsorted(s,np.asarray(test,float),side='right')/max(1,len(s))

def make_ds(sym):
    d=pd.read_csv(ROOT/f'data/offline_cache/{sym}_1m_360d.csv')
    # exact Binance-aligned 5m bars from 1m
    g=(d.open_time.astype('int64')//300000).to_numpy(); x=d.copy(); x['_g']=g
    a=x.groupby('_g',sort=True).agg(open_time=('open_time','first'),open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('volume','sum'),close_time=('close_time','last'),taker_buy_base_volume=('taker_buy_base_volume','sum')).reset_index(drop=True)
    o=a.open.astype(float); h=a.high.astype(float); l=a.low.astype(float); c=a.close.astype(float); v=a.volume.astype(float); tb=a.taker_buy_base_volume.astype(float)
    r1=c.pct_change(); f=pd.DataFrame({'ts':a.close_time.astype('int64')})
    f['ret1']=r1; f['ret2']=c.pct_change(2); f['ret3']=c.pct_change(3); f['body']=(c-o)/o; f['range']=(h-l)/c
    f['close_loc']=(c-l)/(h-l).replace(0,np.nan); e5=c.ewm(span=5,adjust=False).mean(); e20=c.ewm(span=20,adjust=False).mean(); f['e5e20']=e5/e20-1; f['e20_slope3']=e20/e20.shift(3)-1
    pc=c.shift(1); tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1); f['atr14']=tr.rolling(14).mean()/c
    f['vol_z20']=(v-v.rolling(20).mean())/v.rolling(20).std(); buy=tb/v.replace(0,np.nan); f['buy_ratio']=buy; f['imbalance']=2*buy-1
    f['up_frac3']=(r1>0).astype(float).rolling(3).mean(); f['ret1_mean3']=r1.rolling(3).mean(); f['ret1_accel']=r1-r1.shift(1); f['imb_mean3']=f.imbalance.rolling(3).mean()
    f=f.replace([np.inf,-np.inf],np.nan).dropna().reset_index(drop=True)
    ot=d.open_time.to_numpy(np.int64); oo=d.open.to_numpy(float); hh=d.high.to_numpy(float); ll=d.low.to_numpy(float); cc=d.close.to_numpy(float)
    rows=[]
    for _,r in f.iterrows():
        j=int(np.searchsorted(ot,int(r.ts),side='right'))
        if j+H>len(d): continue
        e=float(oo[j]); out=None; follow=0; danger=0
        for k in range(j,j+H):
            if ll[k]<=e*(1-SL): out=-SL; danger=1; break
            if hh[k]>=e*(1+TP): out=TP; follow=1; break
        if out is None: out=float(cc[j+H-1]/e-1)
        q=r.to_dict(); q.update(sym=sym, utility=out-FEE, follow=follow, danger=danger)
        rows.append(q)
    return pd.DataFrame(rows)

all_ds={s:make_ds(s) for s in SYMS}; common_lo=max(x.ts.min() for x in all_ds.values()); common_hi=min(x.ts.max() for x in all_ds.values())
for s in SYMS: all_ds[s]=all_ds[s][all_ds[s].ts.between(common_lo,common_hi)].reset_index(drop=True)
print('ROWS', {s:len(d) for s,d in all_ds.items()})
edges=np.linspace(common_lo,common_hi,5,dtype=np.int64); feats=[c for c in all_ds[SYMS[0]].columns if c not in ['ts','sym','utility','follow','danger']]
variants=[('UTIL95',.95,1.0,1.0,1),('COMP75',.75,1.0,1.0,1),('COMP80',.80,1.0,1.0,1),('DANGER40',.70,.40,1.0,1),('DANGER30',.70,.30,1.0,1),('DANGER20',.70,.20,1.0,1),('ABSTAIN75',.70,.30,.75,1),('ABSTAIN50',.70,.30,.50,1),('DANGER30_TOP2',.70,.30,1.0,2)]
rows=[]
for fold in range(1,4):
    preds=[]
    for sym in SYMS:
        d=all_ds[sym]; tr=d[d.ts<edges[fold]]; te=d[(d.ts>=edges[fold])&(d.ts<edges[fold+1])]
        Xtr=tr[feats].to_numpy('float32'); Xte=te[feats].to_numpy('float32')
        ens=[]
        for seed in [101,202]:
            kw=dict(max_iter=40,max_leaf_nodes=15,l2_regularization=2.0,learning_rate=.06,random_state=seed+fold)
            rg=HistGradientBoostingRegressor(**kw).fit(Xtr,tr.utility); fc=HistGradientBoostingClassifier(**kw).fit(Xtr,tr.follow); dc=HistGradientBoostingClassifier(**kw).fit(Xtr,tr.danger)
            ens.append((rg.predict(Xte),fc.predict_proba(Xte)[:,1],dc.predict_proba(Xte)[:,1],rg.predict(Xtr),fc.predict_proba(Xtr)[:,1],dc.predict_proba(Xtr)[:,1]))
        u=np.mean([z[0] for z in ens],axis=0); pF=np.mean([z[1] for z in ens],axis=0); pD=np.mean([z[2] for z in ens],axis=0)
        ut=np.mean([z[3] for z in ens],axis=0); ft=np.mean([z[4] for z in ens],axis=0); dt=np.mean([z[5] for z in ens],axis=0)
        unc=np.std(np.column_stack([z[0] for z in ens]),axis=1); unct=np.std(np.column_stack([z[3] for z in ens]),axis=1)
        ur=pct_rank(ut,u); fr=pct_rank(ft,pF); dr=pct_rank(dt,pD); qr=pct_rank(unct,unc); comp=.5*ur+.3*fr+.2*(1-dr)
        z=te[['ts','sym','utility','follow','danger']].copy(); z['util_rank']=ur; z['danger_rank']=dr; z['unc_rank']=qr; z['comp']=comp; preds.append(z)
    p=pd.concat(preds,ignore_index=True)
    for name,scoreq,dq,uq,topk in variants:
        scorecol='util_rank' if name.startswith('UTIL') else 'comp'; eligible=p[(p[scorecol]>=scoreq)&(p.danger_rank<=dq)&(p.unc_rank<=uq)].copy()
        if len(eligible): sel=eligible.sort_values(['ts',scorecol],ascending=[True,False]).groupby('ts').head(topk)
        else: sel=eligible
        rows.append(dict(fold=fold+1,variant=name,n=len(sel),net_bps=sel.utility.mean()*1e4 if len(sel) else np.nan,win_rate=(sel.utility>0).mean() if len(sel) else np.nan,tp_rate=sel.follow.mean() if len(sel) else np.nan,danger_rate=sel.danger.mean() if len(sel) else np.nan,unique_ts=sel.ts.nunique(),coins=sel.sym.nunique()))
out=pd.DataFrame(rows); out.to_csv(ROOT/'research/results/MULTICOIN_DANGER_ABSTAIN_RANK_WF.csv',index=False)
print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
print('\nAGG')
for v,g in out.groupby('variant'):
    gg=g.dropna(subset=['net_bps']); print(v,'n',int(gg.n.sum()),'net',np.average(gg.net_bps,weights=gg.n) if gg.n.sum() else np.nan,'pos',int((gg.net_bps>0).sum()),'/3','worst',gg.net_bps.min() if len(gg) else np.nan,'danger',np.average(gg.danger_rate,weights=gg.n) if gg.n.sum() else np.nan)
