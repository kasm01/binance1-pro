from pathlib import Path
import sys, pandas as pd, numpy as np
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import research.scalp.simulate_long1_near_mtf as sim
import research.scalp.test_long1_near_dynamic_gate as dg
CUTOFF=dg.CUTOFF_MS
POLICIES={
 'STATIC_0525':0,
 'RECOVERY_A':1,
 'RECOVERY_B':2,
 'RECOVERY_C':3,
}
def prep(a):
 a=dg.add_regime(a.copy())
 a['close_loc']=(a.close-a.low)/(a.high-a.low).replace(0,np.nan)
 a['lower_wick']=(a[['open','close']].min(axis=1)-a.low)/a.open
 a['range_pct']=(a.high-a.low)/a.open
 a['lower_wick_frac']=a.lower_wick/a.range_pct.replace(0,np.nan)
 return a

def gate(row,mode):
 if mode==0:return .525,'static'
 ar=float(row.atr_rank) if np.isfinite(row.atr_rank) else .5
 loc=float(row.close_loc) if np.isfinite(row.close_loc) else 0
 wf=float(row.lower_wick_frac) if np.isfinite(row.lower_wick_frac) else 0
 # only relax in elevated volatility; otherwise preserve quality
 if ar < .60:return .525,'base'
 if mode==1:
  if loc>=.30 or wf>=.30:return .515,'strong_recovery'
  if loc>=.12 or wf>=.12:return .519,'recovery'
  return .525,'knife'
 if mode==2:
  if loc>=.25 or wf>=.25:return .516,'strong_recovery'
  if loc>=.10 or wf>=.10:return .520,'recovery'
  return .525,'knife'
 if mode==3:
  if loc>=.35 or wf>=.35:return .515,'strong_recovery'
  if loc>=.15 or wf>=.15:return .518,'recovery'
  return .523,'knife'
 return .525,'base'

def dd(t):
 if t.empty:return 0.0
 e=np.r_[sim.START_EQUITY,t.balance_after.to_numpy(float)]; p=np.maximum.accumulate(e)
 return float((e/p-1).min()*100)

def main():
 df=pd.read_csv(sim.DATA)
 for c in ('open','high','low','close','volume'):df[c]=pd.to_numeric(df[c],errors='coerce')
 old=sim.REQ_SCORE; sim.REQ_SCORE=0
 _,p,a,m=sim.build_decisions(df); sim.REQ_SCORE=old
 p=p[sim.WARMUP_3M_BARS:]; a=prep(a.iloc[sim.WARMUP_3M_BARS:].reset_index(drop=True))
 opens=df.open_time.to_numpy(np.int64)
 allrows=[]; alltr=[]
 for name,mode in POLICIES.items():
  ev={};meta={};types={}
  for r,s in zip(a.itertuples(index=False),p):
   if int(r.close_time)<CUTOFF:continue
   thr,kind=gate(r,mode);types[kind]=types.get(kind,0)+1
   if not np.isfinite(s) or float(s)<thr:continue
   j=int(np.searchsorted(opens,int(r.close_time)+1,'left'))
   if j<len(df):ev[j]=max(float(s),ev.get(j,-np.inf));meta[j]=(thr,kind,float(r.atr_rank),float(r.close_loc),float(r.lower_wick_frac))
  rr=[]
  for seed in sim.SEEDS:
   t,b=sim.run(df,ev,seed)
   if len(t):
    t=t.copy();t['policy']=name;t['gate_thr']=t.entry_i.map(lambda x:meta[int(x)][0]);t['gate_kind']=t.entry_i.map(lambda x:meta[int(x)][1]);alltr.append(t)
   w=int((t.net_pnl_usdt>0).sum()) if len(t) else 0
   row={'policy':name,'seed':seed,'candidates':len(ev),'trades':len(t),'ret':(b/sim.START_EQUITY-1)*100,'win':100*w/len(t) if len(t) else 0,'fees':float(t.fees_usdt.sum()) if len(t) else 0,'exp':float(t.net_pnl_usdt.mean()) if len(t) else 0,'dd':dd(t)}
   rr.append(row);allrows.append(row)
  z=pd.DataFrame(rr);print('POLICY',name,{'candidates':len(ev),'mean_trades':z.trades.mean(),'mean_return':z.ret.mean(),'median_return':z.ret.median(),'min_return':z.ret.min(),'max_return':z.ret.max(),'mean_win':z.win.mean(),'fees':z.fees.mean(),'expectancy':z.exp.mean(),'worst_dd':z.dd.min(),'bar_types':types},flush=True)
 pd.DataFrame(allrows).to_csv(ROOT/'research/results/LONG1_NEAR_RECOVERY_GATE_SEEDS.csv',index=False)
 if alltr:
  td=pd.concat(alltr,ignore_index=True);td.to_csv(ROOT/'research/results/LONG1_NEAR_RECOVERY_GATE_TRADES.csv',index=False)
  print('\nPNL BY KIND\n',td.groupby(['policy','gate_kind']).net_pnl_usdt.agg(['count','sum','mean']).to_string())
if __name__=='__main__':main()
