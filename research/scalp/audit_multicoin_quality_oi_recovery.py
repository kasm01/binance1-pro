#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'; D=ROOT/'data/offline_cache'
COINS=['SOL','LINK','AVAX','DOGE']; TP0=.0025; SL0=.0050; FEE0=.0008; H0=10
TP=.0020; SL=.015; H=720
FOLDS=[(.50,.625,.75),(.625,.75,.8333),(.70,.8333,.9166),(.75,.9166,1.0)]
BANDS=[(.60,.80),(.70,.80),(.70,.90),(.60,.90),(.80,.90),(.80,1.0),(.70,1.0),(.60,1.0)]

def agg_tf(d1,mins):
    ms=mins*60000; z=d1.copy(); z['_b']=(z.open_time.astype('int64')//ms)*ms
    a=z.groupby('_b',sort=True).agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('volume','sum'),taker_buy_base_volume=('taker_buy_base_volume','sum'),close_time=('close_time','last')).reset_index(drop=True)
    return a

def feats(df,p):
    o=df.open.astype(float); h=df.high.astype(float); l=df.low.astype(float); c=df.close.astype(float); v=df.volume.astype(float); tb=df.taker_buy_base_volume.astype(float)
    x=pd.DataFrame({'close_time':df.close_time.astype('int64')}); r1=c.pct_change()
    x[p+'_ret1']=r1; x[p+'_ret2']=c.pct_change(2); x[p+'_ret3']=c.pct_change(3); x[p+'_body']=(c-o)/o
    x[p+'_range']=(h-l)/c; x[p+'_close_loc']=(c-l)/(h-l).replace(0,np.nan)
    e5=c.ewm(span=5,adjust=False).mean(); e20=c.ewm(span=20,adjust=False).mean(); x[p+'_e5e20']=e5/e20-1; x[p+'_e20_slope3']=e20/e20.shift(3)-1
    pc=c.shift(); tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1); x[p+'_atr14']=tr.rolling(14).mean()/c
    x[p+'_vol_z20']=(v-v.rolling(20).mean())/v.rolling(20).std().replace(0,np.nan); buy=tb/v.replace(0,np.nan)
    x[p+'_buy_ratio']=buy; x[p+'_imbalance']=2*buy-1; x[p+'_up_frac3']=(r1>0).astype(float).rolling(3).mean(); x[p+'_ret1_mean3']=r1.rolling(3).mean(); x[p+'_ret1_accel']=r1-r1.shift(1); x[p+'_imb_mean3']=x[p+'_imbalance'].rolling(3).mean()
    return x.replace([np.inf,-np.inf],np.nan)

def mdl(seed):
    return HistGradientBoostingClassifier(learning_rate=.05,max_iter=200,max_leaf_nodes=15,min_samples_leaf=150,l2_regularization=5,early_stopping=False,random_state=seed)

def cooldown(z,mins=30):
    if z.empty:return z
    z=z.sort_values('entry_open_time'); keep=[]; last=-10**30; gap=mins*60000
    for i,t in zip(z.index,z.entry_open_time.astype('int64')):
        if t-last>=gap: keep.append(i); last=t
    return z.loc[keep]

def stats(z):
    if z.empty:return dict(n=0,tp=np.nan,sl=np.nan,gross=np.nan,taker10=np.nan,mixed=np.nan,dur=np.nan)
    return dict(n=len(z),tp=(z.state=='TP').mean(),sl=(z.state=='SL').mean(),gross=z.gross.mean()*1e4,taker10=z.net_taker10.mean()*1e4,mixed=z.net_mixed.mean()*1e4,dur=z.dur.mean())

allrows=[]
for coin in COINS:
    print('\n====',coin,'====',flush=True)
    d1=pd.read_csv(D/f'{coin}USDT_1m_360d.csv'); d3=pd.read_csv(D/f'{coin}USDT_3m_360d.csv'); d5=agg_tf(d1,5); d15=agg_tf(d1,15)
    base=feats(d5,'m5').sort_values('close_time'); base=pd.merge_asof(base,feats(d3,'m3').sort_values('close_time'),on='close_time',direction='backward'); base=pd.merge_asof(base,feats(d15,'m15').sort_values('close_time'),on='close_time',direction='backward'); base=base.dropna().reset_index(drop=True)
    feat=[c for c in base if c!='close_time']; ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
    idx=np.searchsorted(ot,base.close_time.to_numpy(np.int64),side='right'); good=idx+H0<=len(d1); base=base.loc[good].reset_index(drop=True); idx=idx[good]
    follow=np.zeros(len(base),int); danger=np.zeros(len(base),int); econ=np.zeros(len(base),float)
    for i,j in enumerate(idx):
        e=o[j]; st=0
        for k in range(H0):
            jj=j+k
            if l[jj]/e-1<=-SL0: danger[i]=1; econ[i]=-SL0-FEE0; st=1; break
            if h[jj]/e-1>=TP0: follow[i]=1; econ[i]=TP0-FEE0; st=1; break
        if not st:econ[i]=c[j+H0-1]/e-1-FEE0
    X=base[feat].to_numpy(float); n=len(base); parts=[]
    for f,(trf,vaf,tef) in enumerate(FOLDS,1):
        tr=int(n*trf); va=int(n*vaf); te=int(n*tef); fit=max(tr-3,1); mf=mdl(42); md=mdl(43); mf.fit(X[:fit],follow[:fit]); md.fit(X[:fit],danger[:fit])
        qv=mf.predict_proba(X[tr:va])[:,1]-md.predict_proba(X[tr:va])[:,1]; qt=mf.predict_proba(X[va:te])[:,1]-md.predict_proba(X[va:te])[:,1]
        best=None
        for q in [.60,.70,.80,.90]:
            cut=np.quantile(qv,q); keep=qv>=cut
            if keep.sum()<40:continue
            m=econ[tr:va][keep].mean()
            if best is None or m>best[0]:best=(m,cut,q)
        if best is None:continue
        keep=qt>=best[1]; ids=np.arange(va,te)[keep]; z=base.iloc[ids].copy(); z['entry_open_time']=ot[np.searchsorted(ot,z.close_time.to_numpy(np.int64),side='right')]; z['gate_fold']=f; z['gate_quality']=qt[keep]; parts.append(z)
    cand=pd.concat(parts,ignore_index=True).sort_values('close_time')
    oi=pd.read_csv(R/f'OKX_{coin}_OI_4H_360d.csv.gz').sort_values('ts'); oi['oi_ret1']=oi.oi_contracts.astype(float).pct_change(); oi['t']=pd.to_datetime(oi.ts,unit='ms',utc=True)
    left=pd.DataFrame({'rid':np.arange(len(cand)),'t':pd.to_datetime(cand.entry_open_time,unit='ms',utc=True)}).sort_values('t'); mm=pd.merge_asof(left,oi[['t','oi_ret1']],on='t',direction='backward').sort_values('rid'); cand['oi_ret1']=mm.oi_ret1.to_numpy()
    eind=np.searchsorted(ot,cand.entry_open_time.to_numpy(np.int64),side='left'); rec=[]
    for ii,(ri,j) in enumerate(zip(cand.index,eind)):
        if j<4 or j+H>=len(o) or not np.isfinite(cand.at[ri,'oi_ret1']):continue
        r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1; deep=(r3<=-.003) or (r1<=-.002); lowrec=(c[j-1]/l[j-1]-1)<.001
        if not(deep and lowrec):continue
        e=o[j]; st='UNRES'; dur=H; gross=c[j+H-1]/e-1
        for k in range(H):
            jj=j+k
            if l[jj]/e-1<=-SL:st='SL';dur=k+1;gross=-SL;break
            if h[jj]/e-1>=TP:st='TP';dur=k+1;gross=TP;break
        fee_mixed=.0004 if st=='TP' else .0007; rg=('PXUP_' if r3>0 else 'PXDN_')+('OIUP' if cand.at[ri,'oi_ret1']>=0 else 'OIDN')
        rec.append((ri,st,dur,gross,gross-.0010,gross-fee_mixed,rg))
    e=pd.DataFrame(rec,columns=['ri','state','dur','gross','net_taker10','net_mixed','regime']).set_index('ri'); cand=cand.join(e); valid=cand.state.notna()
    print('candidates',len(cand),'recovery_valid',int(valid.sum()),'oi_range',pd.to_datetime(oi.ts.min(),unit='ms',utc=True),pd.to_datetime(oi.ts.max(),unit='ms',utc=True),flush=True)
    for tf in [2,3,4]:
        tr=cand[(cand.gate_fold<tf)&valid].copy(); te=cand[(cand.gate_fold==tf)&valid].copy()
        if len(tr)<20 or len(te)<3:continue
        choices=[]
        for lo,hi in BANDS:
            qlo,qhi=tr.gate_quality.quantile([lo,hi]); z=tr[(tr.gate_quality>=qlo)&(tr.gate_quality<=qhi)]
            if len(z)>=12:choices.append((z.net_taker10.mean(),len(z),lo,hi,qlo,qhi))
        if not choices:continue
        choices.sort(reverse=True); _,ntr,lo,hi,qlo,qhi=choices[0]; trb=tr[(tr.gate_quality>=qlo)&(tr.gate_quality<=qhi)]; teb=te[(te.gate_quality>=qlo)&(te.gate_quality<=qhi)]
        regs=[(z.net_taker10.mean(),len(z),rg) for rg,z in trb.groupby('regime') if len(z)>=5]; regs.sort(reverse=True); bestreg=regs[0][2] if regs else 'NONE'; ter=teb[teb.regime.eq(bestreg)] if bestreg!='NONE' else teb.iloc[:0]; terc=cooldown(ter,30)
        sb=stats(teb); sr=stats(ter); sc=stats(terc)
        allrows.append(dict(coin=coin,test_fold=tf,band=f'{lo:.2f}-{hi:.2f}',train_band_n=ntr,best_regime=bestreg,test_band_n=sb['n'],test_band_tp=sb['tp'],test_band_taker10=sb['taker10'],test_reg_n=sr['n'],test_reg_tp=sr['tp'],test_reg_taker10=sr['taker10'],test_reg_mixed=sr['mixed'],cool30_n=sc['n'],cool30_tp=sc['tp'],cool30_taker10=sc['taker10'],cool30_mixed=sc['mixed'],cool30_dur=sc['dur']))
        print('fold',tf,'band',f'{lo:.2f}-{hi:.2f}','reg',bestreg,'test',sc,flush=True)
out=pd.DataFrame(allrows); path=R/'MULTICOIN_NESTED_QUALITY_OKX_OI_RECOVERY.csv'; out.to_csv(path,index=False)
print('\n===== SUMMARY =====')
print(out.round(4).to_string(index=False))
if not out.empty:
    for coin,z in out.groupby('coin'):
        zz=z[z.cool30_n>0]; print(coin,'n',int(zz.cool30_n.sum()),'tp',round(np.average(zz.cool30_tp,weights=zz.cool30_n),4),'taker10',round(np.average(zz.cool30_taker10,weights=zz.cool30_n),4),'mixed',round(np.average(zz.cool30_mixed,weights=zz.cool30_n),4),'regimes',zz.best_regime.value_counts().to_dict())
print('OUTPUT',path)
