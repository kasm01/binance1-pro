#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[2]
IN=ROOT/'research/results/NEAR_RECOVERY_FOLD4_FAILURE.csv'
OUT=ROOT/'research/results/NEAR_RECOVERY_CRASH_GUARD_NESTED.csv'
z=pd.read_csv(IN)
# State-dependent fees for intended execution: BNB maker entry + maker TP, taker emergency SL.
WIN=.0020-.00018-.00018
LOSS=-.0150-.00018-.00045
z['net']=np.where(z.state.eq('TP'),WIN,np.where(z.state.eq('SL'),LOSS,z.ret-.0009))
rows=[]
for test_fold in [2,3,4]:
    cal=z[z.fold<test_fold].copy(); test=z[z.fold==test_fold].copy()
    if len(cal)<20 or len(test)==0: continue
    # Causal thresholds learned from prior folds only; broad quartiles, no test peeking.
    th={
      'range20':cal.range20.quantile(.75),
      'm15_atr':cal.m15_atr.quantile(.75),
      'm3_ret1':cal.m3_ret1.quantile(.25),
      'm15_ret1':cal.m15_ret1.quantile(.25),
      'm3_buy':cal.m3_buy.quantile(.25),
      'm15_volz':cal.m15_volz.quantile(.75),
    }
    def score(df):
        return ((df.range20>=th['range20']).astype(int)+
                (df.m15_atr>=th['m15_atr']).astype(int)+
                (df.m3_ret1<=th['m3_ret1']).astype(int)+
                (df.m15_ret1<=th['m15_ret1']).astype(int)+
                (df.m3_buy<=th['m3_buy']).astype(int)+
                (df.m15_volz>=th['m15_volz']).astype(int))
    cs=score(cal); ts=score(test)
    for k in [2,3,4]:
        keep_cal=cs<k; keep_test=ts<k
        for label,df,keep in [('CAL',cal,keep_cal),('TEST',test,keep_test)]:
            q=df[keep]
            vals=q.net.to_numpy(float)
            pos=vals[vals>0].sum(); neg=-vals[vals<0].sum(); pf=pos/neg if neg>0 else np.inf
            skipped=df[~keep]
            rows.append(dict(test_fold=test_fold,stage=label,guard=f'SCORE_GE{k}_SKIP',n_total=len(df),n_keep=len(q),keep_pct=100*len(q)/len(df),sl_total=int((df.state=='SL').sum()),sl_kept=int((q.state=='SL').sum()),sl_caught=int((skipped.state=='SL').sum()),tp_caught=int((skipped.state=='TP').sum()),net_bps=vals.mean()*1e4 if len(vals) else np.nan,pf=pf))
res=pd.DataFrame(rows)
print('===== NESTED CRASH GUARD: TP20 / SL150 / BNB MAKER-MAKER WIN, MAKER-TAKER LOSS =====')
print(res.round(4).to_string(index=False))
print('\n===== TEST AGGREGATES =====')
test=res[res.stage.eq('TEST')]
for guard,g in test.groupby('guard'):
    # aggregate by reconstructing weighted means and counts
    n=g.n_keep.sum(); weighted=np.average(g.net_bps,weights=g.n_keep) if n else np.nan
    print(guard,'keep_n=',int(n),'weighted_net_bps=',round(weighted,4),'SL_caught=',int(g.sl_caught.sum()),'TP_caught=',int(g.tp_caught.sum()),'positive_folds=',int((g.net_bps>0).sum()),'/',len(g))
res.to_csv(OUT,index=False)
print('OUTPUT=',OUT)
