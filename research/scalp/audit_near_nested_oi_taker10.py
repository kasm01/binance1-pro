#!/usr/bin/env python3
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]; R=ROOT/'research/results'; D=ROOT/'data/offline_cache'
ds=pd.read_csv(R/'NEAR_DUAL_GATE_CANDIDATES.csv.gz'); d1=pd.read_csv(D/'NEARUSDT_1m_360d.csv'); oi=pd.read_csv(R/'OKX_NEAR_OI_4H_360d.csv.gz')
ot=d1.open_time.to_numpy(np.int64); o=d1.open.to_numpy(float); h=d1.high.to_numpy(float); l=d1.low.to_numpy(float); c=d1.close.to_numpy(float)
ds['entry_idx']=np.searchsorted(ot,ds.entry_open_time.to_numpy(np.int64),side='left'); oi['t']=pd.to_datetime(oi.ts,unit='ms',utc=True); oi=oi.sort_values('t'); oi['oi_ret1']=oi.oi_contracts.astype(float).pct_change()
left=pd.DataFrame({'rid':np.arange(len(ds)),'t':pd.to_datetime(ds.entry_open_time,unit='ms',utc=True)}).sort_values('t'); mm=pd.merge_asof(left,oi[['t','oi_ret1']],on='t',direction='backward').sort_values('rid'); ds['oi_ret1']=mm.oi_ret1.to_numpy()
TP=.002; SL=.015; H=720; BANDS=[(.60,.80),(.70,.80),(.70,.90),(.60,.90),(.80,.90),(.80,1.),(.70,1.),(.60,1.)]
rows=[]
for i,r in ds.iterrows():
 j=int(r.entry_idx)
 if j<4 or j+H>=len(o) or not np.isfinite(r.oi_ret1):continue
 r3=c[j-1]/c[j-4]-1; r1=c[j-1]/c[j-2]-1
 if not(((r3<=-.003) or (r1<=-.002)) and ((c[j-1]/l[j-1]-1)<.001)):continue
 e=o[j]; st='UNRES';dur=H;gross=c[j+H-1]/e-1
 for k in range(H):
  jj=j+k
  if l[jj]/e-1<=-SL:st='SL';dur=k+1;gross=-SL;break
  if h[jj]/e-1>=TP:st='TP';dur=k+1;gross=TP;break
 rg=('PXUP_' if r3>0 else 'PXDN_')+('OIUP' if r.oi_ret1>=0 else 'OIDN'); rows.append((i,st,dur,gross,gross-.001,gross-(.0004 if st=='TP' else .0007),rg))
e=pd.DataFrame(rows,columns=['ri','state','dur','gross','net_taker10','net_mixed','regime']).set_index('ri'); ds=ds.join(e); valid=ds.state.notna()
def cool(z):
 z=z.sort_values('entry_open_time'); keep=[];last=-10**30
 for i,t in zip(z.index,z.entry_open_time.astype('int64')):
  if t-last>=1800000:keep.append(i);last=t
 return z.loc[keep]
out=[]
for tf in [2,3,4]:
 tr=ds[(ds.gate_fold<tf)&valid];te=ds[(ds.gate_fold==tf)&valid]; ch=[]
 for lo,hi in BANDS:
  qlo,qhi=tr.gate_quality.quantile([lo,hi]);z=tr[(tr.gate_quality>=qlo)&(tr.gate_quality<=qhi)]
  if len(z)>=12:ch.append((z.net_taker10.mean(),len(z),lo,hi,qlo,qhi))
 ch.sort(reverse=True);_,ntr,lo,hi,qlo,qhi=ch[0];trb=tr[(tr.gate_quality>=qlo)&(tr.gate_quality<=qhi)];teb=te[(te.gate_quality>=qlo)&(te.gate_quality<=qhi)]
 regs=[(z.net_taker10.mean(),len(z),rg) for rg,z in trb.groupby('regime') if len(z)>=5];regs.sort(reverse=True);rg=regs[0][2];ter=cool(teb[teb.regime.eq(rg)])
 out.append(dict(fold=tf,band=f'{lo:.2f}-{hi:.2f}',regime=rg,n=len(ter),tp=(ter.state=='TP').mean() if len(ter) else np.nan,taker10=ter.net_taker10.mean()*1e4 if len(ter) else np.nan,mixed=ter.net_mixed.mean()*1e4 if len(ter) else np.nan))
x=pd.DataFrame(out);print(x.round(4).to_string(index=False));z=x[x.n>0];print('WEIGHTED n',int(z.n.sum()),'tp',np.average(z.tp,weights=z.n),'taker10',np.average(z.taker10,weights=z.n),'mixed',np.average(z.mixed,weights=z.n))
