from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier

ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'research/results/NEAR_STRONG_SIGNAL_DATASET.csv.gz'
D1=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results/NEAR_5M_TOP1_MAKER_EXEC_WF.csv'

df=pd.read_csv(D).replace([np.inf,-np.inf],np.nan).dropna().reset_index(drop=True)
d1=pd.read_csv(D1)
feat=[c for c in df.columns if c.startswith('m5_')]
X=df[feat].astype('float32').to_numpy()
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
entry_t=df.entry_open_time.to_numpy(np.int64); entry=df.entry_price.to_numpy(float)
idx=np.searchsorted(ot,entry_t)
TP=.002; SL=.010; H=15
TAKER=.0005; MAKER=.0002

# Baseline target used to train/select setup model: current taker+taker 10 bps.
y=np.full(len(df),np.nan); w=np.zeros(len(df),int)
for j,(ii,e) in enumerate(zip(idx,entry)):
    if ii<0 or ii+H>len(d1) or e<=0: continue
    out=None
    for k in range(ii,ii+H):
        if l[k] <= e*(1-SL): out=-SL; break
        if h[k] >= e*(1+TP): out=TP; w[j]=1; break
    if out is None: out=c[ii+H-1]/e-1
    y[j]=out-2*TAKER

# Exit after a known entry. Conservative: same candle can stop after a limit fill,
# but same-candle TP is not credited because high may have occurred before fill.
def eval_after_entry(start_idx, end_idx, px, entry_fee, tp_fee, other_exit_fee, skip_tp_first_candle=False):
    for k in range(start_idx,end_idx):
        if l[k] <= px*(1-SL):
            return -SL-entry_fee-other_exit_fee,'SL',k
        if not (skip_tp_first_candle and k==start_idx) and h[k] >= px*(1+TP):
            return TP-entry_fee-tp_fee,'TP',k
    # timeout at final close
    return c[end_idx-1]/px-1-entry_fee-other_exit_fee,'TIMEOUT',end_idx-1

def sim(ii, mode, off_bps=0, wait=0, tp_maker=False):
    end=ii+H
    tpfee=MAKER if tp_maker else TAKER
    if mode=='TAKER':
        return eval_after_entry(ii,end,o[ii],TAKER,tpfee,TAKER,False)+(0,False,False)
    limit=o[ii]*(1-off_bps/1e4)
    fill=None
    for s in range(wait):
        k=ii+s
        if l[k] <= limit:
            fill=k; break
    if fill is not None:
        ret,reason,k=eval_after_entry(fill,end,limit,MAKER,tpfee,TAKER,True)
        delta=(o[ii]/limit-1)*1e4
        return ret,reason,k,delta,True,False
    fb=ii+wait
    if fb>=end:
        return np.nan,'MISS',fb,np.nan,False,True
    ret,reason,k=eval_after_entry(fb,end,o[fb],TAKER,tpfee,TAKER,False)
    delta=(o[ii]/o[fb]-1)*1e4
    return ret,reason,k,delta,False,True

edges=np.linspace(0,len(df),5,dtype=int)
selected=[]
for fold in range(1,4):
    tr=np.arange(0,edges[fold]); te=np.arange(edges[fold],edges[fold+1])
    tr=tr[np.isfinite(y[tr])]; te=te[np.isfinite(y[te])]
    common=dict(max_iter=120,max_leaf_nodes=15,l2_regularization=2.0,learning_rate=.06,random_state=400+fold)
    rg=HistGradientBoostingRegressor(**common).fit(X[tr],y[tr])
    cl=HistGradientBoostingClassifier(**common).fit(X[tr],(y[tr]>0).astype(int))
    pr=rg.predict(X[te]); pp=cl.predict_proba(X[te])[:,1]
    prt=rg.predict(X[tr]); ppt=cl.predict_proba(X[tr])[:,1]
    def z(v):
        s=np.std(v); return (v-np.mean(v))/(s if s>1e-9 else 1)
    best=None
    for a in [0,.25,.5,.75,1.0]:
        st=a*z(prt)+(1-a)*z(ppt)
        for f in [.01,.02,.05,.10,.20]:
            kk=max(250,int(len(tr)*f)); s=np.argsort(st)[-kk:]; val=float(np.mean(y[tr][s]))
            if best is None or val>best[0]: best=(val,a,f)
    _,a,f=best
    sr=(pr-np.mean(prt))/(np.std(prt) if np.std(prt)>1e-9 else 1)
    sp=(pp-np.mean(ppt))/(np.std(ppt) if np.std(ppt)>1e-9 else 1)
    score=a*sr+(1-a)*sp
    kk=max(1,int(len(te)*f)); loc=np.argsort(score)[-kk:]
    selected += [(fold+1,int(te[q])) for q in loc]

scenarios=[('TAKER_NOW', 'TAKER',0,0,False),
           ('MKR1_W1_TP_T', 'MAKER',1,1,False),('MKR2_W1_TP_T','MAKER',2,1,False),('MKR3_W1_TP_T','MAKER',3,1,False),
           ('MKR1_W2_TP_T', 'MAKER',1,2,False),('MKR2_W2_TP_T','MAKER',2,2,False),('MKR3_W2_TP_T','MAKER',3,2,False),
           ('MKR1_W3_TP_T', 'MAKER',1,3,False),('MKR2_W3_TP_T','MAKER',2,3,False),('MKR3_W3_TP_T','MAKER',3,3,False),
           ('MKR1_W1_TP_M', 'MAKER',1,1,True), ('MKR2_W1_TP_M','MAKER',2,1,True), ('MKR3_W1_TP_M','MAKER',3,1,True),
           ('MKR1_W2_TP_M', 'MAKER',1,2,True), ('MKR2_W2_TP_M','MAKER',2,2,True), ('MKR3_W2_TP_M','MAKER',3,2,True)]
rows=[]
for name,mode,off,wait,tpm in scenarios:
    vals=[]; folds=[]; fills=0; fbs=0; reasons=[]; deltas=[]
    for fold,j in selected:
        ii=int(idx[j])
        ret,reason,k,delta,filled,fb=sim(ii,mode,off,wait,tpm)
        if not np.isfinite(ret): continue
        vals.append(ret); folds.append(fold); fills+=int(filled); fbs+=int(fb); reasons.append(reason); deltas.append(delta)
    a=np.asarray(vals); ff=np.asarray(folds); rr=np.asarray(reasons)
    foldmeans=[a[ff==q].mean()*1e4 for q in sorted(set(ff))]
    rows.append(dict(scenario=name,n=len(a),maker_fill_pct=100*fills/max(1,len(a)),fallback_pct=100*fbs/max(1,len(a)),
                     entry_delta_bps=float(np.nanmean(deltas)),tp_pct=100*np.mean(rr=='TP'),sl_pct=100*np.mean(rr=='SL'),timeout_pct=100*np.mean(rr=='TIMEOUT'),
                     net_bps=float(a.mean()*1e4),positive_folds=sum(x>0 for x in foldmeans),worst_fold_bps=min(foldmeans),
                     fold2_bps=foldmeans[0],fold3_bps=foldmeans[1],fold4_bps=foldmeans[2]))
out=pd.DataFrame(rows).sort_values('net_bps',ascending=False)
out.to_csv(OUT,index=False)
print(out.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
print('OUT',OUT)
