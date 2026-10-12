#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'
CAND=R/'NEAR_DUAL_GATE_CANDIDATES.csv.gz'; O3=R/'OKX_NEAR_3m_360d.csv.gz'; O5=R/'OKX_NEAR_5m_360d.csv.gz'; FUND=R/'OKX_NEAR_FUNDING.csv.gz'
OUT=R/'NEAR_OKX_EXTERNAL_CONTEXT_WF.csv'; FEATOUT=R/'NEAR_OKX_EXTERNAL_FEATURE_SEPARATION.csv'

def make_okx(path,prefix,mins):
    x=pd.read_csv(path).sort_values('ts').copy()
    c=x.close.astype(float); o=x.open.astype(float); h=x.high.astype(float); l=x.low.astype(float); v=x.volCcyQuote.astype(float)
    x[f'{prefix}_ret1']=c.pct_change(1); x[f'{prefix}_ret2']=c.pct_change(2); x[f'{prefix}_ret3']=c.pct_change(3)
    x[f'{prefix}_body']=c/o-1; x[f'{prefix}_range']=h/l-1
    den=(h-l).replace(0,np.nan); x[f'{prefix}_close_loc']=(c-l)/den
    tr=pd.concat([(h-l).abs(),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    x[f'{prefix}_atr14']=tr.rolling(14,min_periods=5).mean()/c
    vm=v.rolling(20,min_periods=8); x[f'{prefix}_vol_z20']=(v-vm.mean())/(vm.std(ddof=0)+1e-12)
    x[f'{prefix}_slope3']=c.pct_change(3)/3
    x[f'{prefix}_accel']=x[f'{prefix}_ret1']-x[f'{prefix}_ret1'].shift(1)
    x['okx_close_time']=x.ts.astype('int64')+mins*60_000-1
    keep=['okx_close_time']+[c for c in x.columns if c.startswith(prefix+'_')]
    return x[keep].sort_values('okx_close_time')

df=pd.read_csv(CAND).sort_values('feature_close_time').copy()
strong=(df.mfe_5m_pct>=0.20)&(df.mae_5m_pct>=-0.15)&(df.time_to_mfe_5m<=3)
danger=(df.mae_10m_pct<=-0.50)|(df.net_10m_pct<=-0.30)
use=strong|danger; d=df.loc[use].copy(); d['y']=strong[use].astype(int).to_numpy()
for path,pfx,mins in [(O3,'okx3',3),(O5,'okx5',5)]:
    if path.exists():
        ox=make_okx(path,pfx,mins)
        d=pd.merge_asof(d.sort_values('feature_close_time'),ox,left_on='feature_close_time',right_on='okx_close_time',direction='backward')
# Cross-exchange relations against Binance technical features already present
for tf in ['3','5']:
    op=f'okx{tf}'; bp=f'm{tf}'
    for k in ['ret1','ret2','ret3','body','range','close_loc','atr14','vol_z20']:
        a=f'{bp}_{k}'; b=f'{op}_{k}'
        if a in d and b in d:
            d[f'x{tf}_{k}_diff']=d[a]-d[b]
    if f'{op}_ret1' in d:
        d[f'x{tf}_sign_agree1']=(np.sign(d[f'{bp}_ret1'])==np.sign(d[f'{op}_ret1'])).astype(float)
        d[f'x{tf}_ret1_absdiff']=(d[f'{bp}_ret1']-d[f'{op}_ret1']).abs()
    if f'{op}_ret3' in d:
        d[f'x{tf}_sign_agree3']=(np.sign(d[f'{bp}_ret3'])==np.sign(d[f'{op}_ret3'])).astype(float)
        d[f'x{tf}_ret3_absdiff']=(d[f'{bp}_ret3']-d[f'{op}_ret3']).abs()
# Funding is sparse (~100d); merge causally and retain availability flag
if FUND.exists():
    fu=pd.read_csv(FUND).sort_values('fundingTime').copy(); fu['fundingTime']=pd.to_numeric(fu.fundingTime)
    fu['okx_funding_rate']=pd.to_numeric(fu.fundingRate,errors='coerce'); fu['okx_funding_delta']=fu.okx_funding_rate.diff(); fu['okx_funding_abs']=fu.okx_funding_rate.abs()
    fu=fu[['fundingTime','okx_funding_rate','okx_funding_delta','okx_funding_abs']]
    d=pd.merge_asof(d.sort_values('feature_close_time'),fu,left_on='feature_close_time',right_on='fundingTime',direction='backward')
    d['okx_funding_available']=d.okx_funding_rate.notna().astype(float)
    d['okx_funding_age_h']=(d.feature_close_time-d.fundingTime)/3_600_000

tech=[c for c in d.columns if c.startswith(('m5_','m3_','m15_')) and c not in ['mfe_5m_pct','mae_5m_pct','mfe_3m_pct','mae_3m_pct','mfe_10m_pct','mae_10m_pct']]
ext=[c for c in d.columns if c.startswith(('okx3_','okx5_','x3_','x5_'))]
fund=[c for c in d.columns if c.startswith('okx_funding_')]
# exclude any accidental future/label fields (none expected)
for arr in [tech,ext,fund]:
    arr[:]=[c for c in arr if not any(z in c for z in ['mfe','mae','net_','time_to_'])]
print('LABELED',len(d),'STRONG_RATE',round(d.y.mean(),4),'TECH',len(tech),'EXT',len(ext),'FUND',len(fund))
print('EXT coverage',round(d[ext].notna().all(axis=1).mean(),4) if ext else 0,'FUND coverage',round(d.okx_funding_available.mean(),4) if 'okx_funding_available' in d else 0)
# Univariate external separation
rows=[]
for c in ext+fund:
    z=d[['y','gate_fold',c]].dropna()
    if len(z)<100 or z.y.nunique()<2: continue
    try: auc=roc_auc_score(z.y,z[c]); aa=max(auc,1-auc)
    except: aa=np.nan
    med1=z.loc[z.y.eq(1),c].median(); med0=z.loc[z.y.eq(0),c].median(); mad=np.nanmedian(np.abs(z[c]-np.nanmedian(z[c])))+1e-12
    signs=[]
    for f in sorted(z.gate_fold.unique()):
        q=z[z.gate_fold.eq(f)]
        if q.y.nunique()<2: continue
        signs.append(np.sign(q.loc[q.y.eq(1),c].median()-q.loc[q.y.eq(0),c].median()))
    cons=max(sum(s>0 for s in signs),sum(s<0 for s in signs))/max(1,len(signs))
    rows.append((c,len(z),med1,med0,(med1-med0)/(1.4826*mad),aa,cons))
fr=pd.DataFrame(rows,columns=['feature','n','strong_median','danger_median','robust_effect','auc_abs','fold_sign_consistency']).sort_values('auc_abs',ascending=False)
fr.to_csv(FEATOUT,index=False)
print('\nTOP EXTERNAL SEPARATORS'); print(fr.head(20).round(5).to_string(index=False))

def wf_eval(name,features,require_funding=False):
    z=d.copy()
    if require_funding: z=z[z.okx_funding_available.eq(1)].copy()
    X=z[features].replace([np.inf,-np.inf],np.nan).fillna(0.0)
    out=[]
    for tf in [2,3,4]:
        tr=z.gate_fold<tf; te=z.gate_fold.eq(tf)
        if tr.sum()<80 or te.sum()<20 or z.loc[tr,'y'].nunique()<2 or z.loc[te,'y'].nunique()<2: continue
        m=HistGradientBoostingClassifier(max_depth=3,learning_rate=.04,max_iter=180,l2_regularization=3.0,random_state=42)
        m.fit(X.loc[tr],z.loc[tr,'y']); ptr=m.predict_proba(X.loc[tr])[:,1]; pte=m.predict_proba(X.loc[te])[:,1]
        auc=roc_auc_score(z.loc[te,'y'],pte); cut=np.quantile(ptr,.80); sel=pte>=cut
        test=z.loc[te].copy(); kept=test.iloc[np.flatnonzero(sel)]
        out.append(dict(model=name,test_fold=tf,n_train=int(tr.sum()),n_test=int(te.sum()),auc=auc,base_strong_rate=test.y.mean(),n_top20=len(kept),top20_strong_rate=kept.y.mean() if len(kept) else np.nan,top20_danger_rate=1-kept.y.mean() if len(kept) else np.nan,top20_net10_bps=kept.net_10m_pct.mean()*100 if len(kept) else np.nan))
    return out
wf=[]
wf+=wf_eval('TECH',tech)
if ext: wf+=wf_eval('OKX_EXT',ext); wf+=wf_eval('TECH_PLUS_OKX',tech+ext)
if fund and 'okx_funding_available' in d:
    wf+=wf_eval('TECH_PLUS_OKX_FUND_OVERLAP',tech+ext+fund,require_funding=True)
w=pd.DataFrame(wf); w.to_csv(OUT,index=False)
print('\nWALK FORWARD'); print(w.round(4).to_string(index=False))
if len(w):
    print('\nAGG'); print(w.groupby('model').apply(lambda g: pd.Series({'folds':len(g),'mean_auc':g.auc.mean(),'w_top20_strong':np.average(g.top20_strong_rate,weights=g.n_top20),'w_top20_net10_bps':np.average(g.top20_net10_bps,weights=g.n_top20)})).round(4).to_string())
print('OUTPUT',OUT,FEATOUT)
