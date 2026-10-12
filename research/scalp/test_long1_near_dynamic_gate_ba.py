from pathlib import Path
import sys, os, logging
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.load_env import load_environment_variables
import research.scalp.simulate_long1_near_mtf as sim

load_environment_variables()
CUTOFF_MS=int(pd.Timestamp('2026-09-14 19:38:38',tz='UTC').timestamp()*1000)
PROFILES={
 
 
 'DYN_BALANCED':{'quiet':.525,'normal_aligned':.522,'normal_unaligned':.525,'active_aligned':.520,'active_unaligned':.523,'chaos':.527},
 'DYN_AGGRESSIVE':{'quiet':.524,'normal_aligned':.521,'normal_unaligned':.524,'active_aligned':.520,'active_unaligned':.522,'chaos':.526},
}

def add_regime(a):
    a=a.copy()
    c=pd.to_numeric(a.close,errors='coerce')
    h=pd.to_numeric(a.high,errors='coerce'); l=pd.to_numeric(a.low,errors='coerce')
    prev=c.shift(1)
    tr=pd.concat([(h-l).abs(),(h-prev).abs(),(l-prev).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    a['atr_pct']=atr/c.replace(0,np.nan)
    a['atr_rank']=a['atr_pct'].rolling(240,min_periods=80).apply(lambda x: float(np.mean(x[:-1] <= x[-1])) if len(x)>1 else np.nan, raw=True)
    a['ema7']=c.ewm(span=7,adjust=False).mean(); a['ema25']=c.ewm(span=25,adjust=False).mean()
    a['mom3']=c/c.shift(3)-1.0
    spread=(a.ema7-a.ema25)/c.replace(0,np.nan)
    a['aligned']=(a.ema7>a.ema25) & (a.mom3>0) & (spread>0)
    return a

def dyn_thr(row, profile):
    if profile is None: return .525, 'static'
    r=float(row.atr_rank) if np.isfinite(row.atr_rank) else .5
    al=bool(row.aligned)
    if r < .30: return profile['quiet'],'quiet'
    if r < .60: return profile['normal_aligned' if al else 'normal_unaligned'], 'normal_aligned' if al else 'normal_unaligned'
    if r < .85: return profile['active_aligned' if al else 'active_unaligned'], 'active_aligned' if al else 'active_unaligned'
    return profile['chaos'],'chaos'

def max_dd(t):
    if t.empty:return 0.0
    eq=np.r_[sim.START_EQUITY,t.balance_after.to_numpy(float)]; pk=np.maximum.accumulate(eq)
    return float((eq/pk-1).min()*100)

def main():
    df=pd.read_csv(sim.DATA)
    for c in ('open','high','low','close','volume'): df[c]=pd.to_numeric(df[c],errors='coerce')
    old=sim.REQ_SCORE; sim.REQ_SCORE=0.0
    _,p,agg,model=sim.build_decisions(df)
    sim.REQ_SCORE=old
    p=p[sim.WARMUP_3M_BARS:]; agg=agg.iloc[sim.WARMUP_3M_BARS:].reset_index(drop=True)
    agg=add_regime(agg)
    opens=df.open_time.to_numpy(np.int64)
    out=[]; alltr=[]
    print('MODEL_META_SYMBOL',(getattr(model,'meta',None) or getattr(model,'model_meta',{}) or {}).get('symbol'))
    print('OOS_CUTOFF',pd.to_datetime(CUTOFF_MS,unit='ms',utc=True))
    for name,prof in PROFILES.items():
        events={}; meta={}; counts={}
        for r,score in zip(agg.itertuples(index=False),p):
            if int(r.close_time) < CUTOFF_MS: continue
            thr,reg=dyn_thr(r,prof); counts[reg]=counts.get(reg,0)+1
            if not np.isfinite(score) or float(score)<thr: continue
            j=int(np.searchsorted(opens,int(r.close_time)+1,side='left'))
            if j<len(df):
                events[j]=max(float(score),events.get(j,-np.inf)); meta[j]=(thr,reg,float(r.atr_rank) if np.isfinite(r.atr_rank) else np.nan,bool(r.aligned))
        rows=[]
        for seed in sim.SEEDS:
            t,b=sim.run(df,events,seed)
            if not t.empty:
                t=t.copy(); t['profile']=name
                t['gate_threshold']=t.entry_i.map(lambda i: meta.get(int(i),(np.nan,'',np.nan,False))[0])
                t['regime']=t.entry_i.map(lambda i: meta.get(int(i),(np.nan,'',np.nan,False))[1])
                t['atr_rank']=t.entry_i.map(lambda i: meta.get(int(i),(np.nan,'',np.nan,False))[2])
                t['trend_aligned']=t.entry_i.map(lambda i: meta.get(int(i),(np.nan,'',np.nan,False))[3])
                alltr.append(t)
            w=(t.net_pnl_usdt>0).sum() if len(t) else 0
            rows.append({'profile':name,'seed':seed,'candidates':len(events),'trades':len(t),'return_pct':(b/sim.START_EQUITY-1)*100,'win_rate':100*w/len(t) if len(t) else 0,'fees':float(t.fees_usdt.sum()) if len(t) else 0,'expectancy':float(t.net_pnl_usdt.mean()) if len(t) else 0,'max_dd_pct':max_dd(t)})
            out.append(rows[-1])
        s=pd.DataFrame(rows)
        print('PROFILE',name,{'candidates':len(events),'mean_trades':float(s.trades.mean()),'mean_return_pct':float(s.return_pct.mean()),'median_return_pct':float(s.return_pct.median()),'min_return_pct':float(s.return_pct.min()),'max_return_pct':float(s.return_pct.max()),'mean_win_rate':float(s.win_rate.mean()),'mean_fees':float(s.fees.mean()),'mean_expectancy':float(s.expectancy.mean()),'worst_dd_pct':float(s.max_dd_pct.min()),'regime_bars':counts},flush=True)
    pd.DataFrame(out).to_csv(ROOT/'research/results/LONG1_NEAR_DYNAMIC_GATE_SEEDS.csv',index=False)
    if alltr:
        td=pd.concat(alltr,ignore_index=True); td.to_csv(ROOT/'research/results/LONG1_NEAR_DYNAMIC_GATE_TRADES.csv',index=False)
        g=td.groupby(['profile','regime']).agg(n=('net_pnl_usdt','size'),net=('net_pnl_usdt','sum'),avg=('net_pnl_usdt','mean'),wins=('net_pnl_usdt',lambda x:int((x>0).sum()))).reset_index()
        print('\nREGIME_PNL\n'+g.to_string(index=False))
if __name__=='__main__': main()
