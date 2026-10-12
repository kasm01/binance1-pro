#!/usr/bin/env python3
import importlib.util, pathlib, pandas as pd, numpy as np
p=pathlib.Path('/home/kasm920/binance1-pro/research/scalp/audit_nested_execution_wf.py')
spec=importlib.util.spec_from_file_location('nw2',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
bands=[(.5,.6),(.6,.7),(.7,.8),(.8,.9),(.9,1.0),(.6,.8),(.7,.9)]
sc=('MKR3_W1',3,1)
rows=[]
for bnb in [False,True]:
    for lo,hi in bands:
        for tf in [2,3,4]:
            cal=m.ds[m.ds.gate_fold<tf]; test=m.ds[m.ds.gate_fold==tf]
            qlo=float(cal.gate_quality.quantile(lo)); qhi=float(cal.gate_quality.quantile(hi)) if hi<1 else float('inf')
            sub=m.select_subset(test,qlo,qhi); r=m.run_subset(sub,sc,bnb)
            rows.append(dict(bnb=bnb,band=f'{int(lo*100)}-{int(hi*100)}',fold=tf,n=r['n'],net=r['net'],pf=r['pf']))
r=pd.DataFrame(rows)
print('===== CAUSAL QUALITY BANDS / FIXED MKR3_W1 =====')
for bnb,g in r.groupby('bnb'):
    out=[]
    for band,s in g.groupby('band',sort=False):
        s=s[s.n>0]
        if len(s)==0: continue
        out.append(dict(band=band,n=int(s.n.sum()),weighted_net_bps=np.average(s.net,weights=s.n),positive_folds=int((s.net>0).sum()),folds=len(s),worst_fold_bps=s.net.min(),mean_pf=s.pf.replace(np.inf,np.nan).mean()))
    print('\nBNB=',bnb)
    print(pd.DataFrame(out).sort_values('weighted_net_bps',ascending=False).round(4).to_string(index=False))
