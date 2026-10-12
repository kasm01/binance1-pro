from pathlib import Path
import sys, random, math
import numpy as np, pandas as pd
ROOT=Path('/home/kasm920/binance1-pro')
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import research.scalp.simulate_long1_near_mtf as sim
K=pd.read_csv(ROOT/'research/data/NEARUSDT_1m_1month.csv')
for c in ('open','high','low','close','volume'): K[c]=pd.to_numeric(K[c],errors='coerce')
T=pd.read_csv(ROOT/'research/results/LONG1_NEAR_STRONG_RECOVERY_GATE_TRADES.csv')
U=T[T.policy.eq('STRONG_0516')].drop_duplicates(['seed','entry_i']).copy()
MIN_BODY=.18; MAX_RET=.45; REJ=.70; MIN_Q=.55; MAX_PROG=.52

def nodes(r):
    o,h,l,c=[float(r[k]) for k in ('open','high','low','close')]
    return [(0,o),(.25,l),(.75,h),(1,c)] if c>=o else [(0,o),(.25,h),(.75,l),(1,c)]
def interp(ns,q):
    for (t0,p0),(t1,p1) in zip(ns[:-1],ns[1:]):
        if t0<=q<=t1:
            z=(q-t0)/(t1-t0) if t1>t0 else 0
            return p0+(p1-p0)*z
    return ns[-1][1]
def conf(row,q):
    ns=nodes(row); o=float(row.open); px=interp(ns,q); vals=[o]
    for t,p in ns[1:]:
        if t<=q: vals.append(p)
    vals.append(px); hi=max(vals); lo=min(vals); cr=hi-lo
    if cr<=0:return 'pending'
    body=abs(px-o)/cr; direction=px>=o; reversal=max(0,hi-px); span=max(0,hi-o); retr=min(1,reversal/span) if span>0 else 0
    loc=(px-lo)/cr; bq=min(1,body/max(MIN_BODY,1e-9)); rq=max(0,1-retr); qual=.30*(1 if direction else 0)+.25*bq+.25*rq+.20*max(0,min(1,loc))
    if span<=0:return 'pending'
    if retr>=REJ:return 'block'
    if (not direction or retr>=MAX_RET or body<MIN_BODY or qual<MIN_Q):return 'pending'
    return 'open'

def find_entry(i,q0,soft_block=False):
    row=K.iloc[int(i)]; step=5/60
    q=q0
    while q<=MAX_PROG+1e-12:
        a=conf(row,q)
        if a=='open': return q, interp(nodes(row),q), 'ready'
        if a=='block' and not soft_block:return None,None,'blocked'
        q=math.ceil((q*60+1e-9)/5)*5/60
        if q<=q0+1e-12:q+=step
    return None,None,'expired'

def simulate_after(i,q,ep,bal):
    qty=(bal*sim.BAL_PCT)/ep; notion=bal*sim.BAL_PCT; best_roi=0; best_pnl=0; last_best=int(K.iloc[i].open_time+q*60000); armed=False
    entry_ms=last_best
    for j in range(int(i),len(K)):
        row=K.iloc[j]; open_ms=int(row.open_time); start_q=q if j==i else 0
        for qq,px in sim.samples(row,start_q):
            now=open_ms+int(qq*60000); pnl=(px-ep)/ep; roi=pnl*sim.LEV
            if pnl>best_pnl:best_pnl=pnl;last_best=now
            if roi>best_roi:best_roi=roi
            if best_roi>=sim.ROI_TP:armed=True
            reason=None
            if roi<=sim.ROI_STOP: reason='roi_hard_stop_lifecycle'
            elif armed and roi<=best_roi-sim.ROI_GB: reason='fixed_roi_giveback'
            elif px<=ep*(1-sim.SL): reason='sl_hit'
            elif px>=ep*(1+sim.TP): reason='tp_hit'
            elif (now-last_best)/1000>=sim.STALL: reason='stall_exit'
            if reason:
                exnot=qty*px; gross=(px-ep)*qty; fees=(notion+exnot)*sim.FEE; net=gross-fees
                return net,fees,reason,(now-entry_ms)/1000
    return 0,0,'eod',0

def run(mode):
    rows=[]
    for seed in sorted(U.seed.unique()):
        bal=sim.START_EQUITY; last_close=-10**30
        S=U[U.seed.eq(seed)].sort_values('entry_i')
        for _,x in S.iterrows():
            i=int(x.entry_i); q0=float(x.entry_progress); open_ms=int(K.iloc[i].open_time)
            if open_ms < last_close+int(sim.COOLDOWN*1000): continue
            q,ep,status=find_entry(i,q0,soft_block=(mode=='soft_block'))
            if q is None:
                rows.append({'mode':mode,'seed':seed,'entry_i':i,'status':status,'entered':0,'net':0,'fees':0,'delay_sec':np.nan,'balance':bal}); continue
            net,fees,reason,dur=simulate_after(i,q,ep,bal); bal+=net; last_close=open_ms+int(q*60000+dur*1000)
            rows.append({'mode':mode,'seed':seed,'entry_i':i,'status':'entered','entered':1,'net':net,'fees':fees,'delay_sec':(q-q0)*60,'reason':reason,'balance':bal})
    R=pd.DataFrame(rows)
    summ=[]
    for seed,g in R.groupby('seed'):
        final=float(g.balance.iloc[-1]) if len(g) else sim.START_EQUITY; ent=g[g.entered.eq(1)]
        summ.append({'mode':mode,'seed':seed,'final':final,'return_pct':(final/sim.START_EQUITY-1)*100,'entered':len(ent),'win_rate':100*(ent.net>0).mean() if len(ent) else 0,'fees':ent.fees.sum(),'avg_delay':ent.delay_sec.mean() if len(ent) else np.nan})
    S=pd.DataFrame(summ)
    print(mode,{'mean_return':S.return_pct.mean(),'median':S.return_pct.median(),'min':S.return_pct.min(),'max':S.return_pct.max(),'mean_entered':S.entered.mean(),'mean_win':S.win_rate.mean(),'fees':S.fees.mean(),'avg_delay_sec':S.avg_delay.mean(),'status_counts':R.status.value_counts().to_dict()},flush=True)
    return R,S

A=[];B=[]
for mode in ('current_block','soft_block'):
    r,s=run(mode);A.append(r);B.append(s)
pd.concat(A).to_csv(ROOT/'research/results/LONG1_NEAR_ENTRY_CONFIRM_REVALIDATION_TRADES.csv',index=False)
pd.concat(B).to_csv(ROOT/'research/results/LONG1_NEAR_ENTRY_CONFIRM_REVALIDATION_SEEDS.csv',index=False)
